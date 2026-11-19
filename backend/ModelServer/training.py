# 학습 파이프라인: 녹음 합치기 → UVR → preprocess → extract → train → index → pitch.txt
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (main.py의 run_training → status.json)
import os
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor

import torch
import librosa
import numpy as np
import soundfile as sf
from fastapi import HTTPException

from command import run_command_async

executor = ThreadPoolExecutor()

# 백그라운드 작업 함수 생성
async def combine_audio(model_name, dataset_path, voice_file_name):
    sr = 22050
    combined_audio = []
    try:
        if len(voice_file_name) != 1:
            for file_name in voice_file_name:
                # librosa.load를 비동기적으로 실행 (익명 함수를 사용하여 sr 인수 전달)
                audio = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    lambda: librosa.load(os.path.join(dataset_path, file_name), sr=sr)
                )
                combined_audio.append(audio[0])
            combined_audio = np.concatenate(combined_audio)
            voice_file = os.path.join(dataset_path, "combined.wav")

            # sf.write를 비동기적으로 실행
            await asyncio.get_event_loop().run_in_executor(
                executor, sf.write, voice_file, combined_audio, sr
            )

            for i in range(len(voice_file_name)):
                os.remove(os.path.join(dataset_path, voice_file_name[i]))
            print(f"[Model {model_name}] 음성 파일 병합 완료")
            return voice_file
        else:
            print("오디오 파일이 하나만 존재합니다. 기존 방식으로 처리됩니다.")
            return os.path.join(dataset_path, voice_file_name[0])
    except Exception as e:
        print(f"[Model {model_name}] 음성 파일 병합 중 오류 발생: {e}")

# 비동기 모델 생성 작업 (모델 서버에서 비동기 처리)
async def create_model_async(model_name, dataset_path, sample_rate, cpu_cores, voice_file_name):
    # --- 0. 음성 통합 시스템 실행 ---
    
    sr = 40000
    combined_audio = []
    voice_file = await combine_audio(model_name, dataset_path, voice_file_name)
    # --- 1. Uvr 실행 ---
    print(voice_file)
    uvr_command = [
        sys.executable,
        "uvr_cli.py",
        "--audio_file", voice_file,
        "--model_filename", "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
        "--output_format", "OGG",
        "--output_dir", dataset_path,
        "--sample_rate", sample_rate,
        "--vr_batch_size", "4",
        "--vr_window_size", "320",
        "--model_file_dir", "uvrmodel",
        "--single_stem", "Vocals",
        "--mdx_segment_size", "512",
        "--mdxc_segment_size", "512",
        "--demucs_segment_size", "100",
        "--mdx_enable_denoise"
    ]
    voice_file_check = [
        f for f in os.listdir(dataset_path) if f.endswith(".ogg")
    ]
    if not voice_file_check:
        await run_command_async(uvr_command, model_name, "uvr")  # 비동기 실행
        remove_voice_file = [
        f for f in os.listdir(dataset_path) if f.endswith(".wav") or f.endswith(".m4a")
        ]
        remove_voice_file = os.path.join(dataset_path, remove_voice_file[0])
        os.remove(remove_voice_file)
        print("노이즈 제거 음성 파일 존재")
    else:
        print("노이즈 제거 음성 파일 없음 혹은 이미 UVR처리 종료됨")

    # --- 2. Preprocess 실행 ---
    preprocess_command = [
        sys.executable,
        "rvc_cli.py",
        "preprocess",
        "--model_name", model_name,
        "--dataset_path", dataset_path,
        "--sample_rate", sample_rate,
        "--cpu_cores", str(cpu_cores)
    ]
    await run_command_async(preprocess_command, model_name, "preprocess")  # 비동기 실행

    # --- 3. Extract 실행 ---
    extract_command = [
        sys.executable,
        "rvc_cli.py",
        "extract",
        "--model_name", model_name,
        "--rvc_version", "v2",
        "--sample_rate", sample_rate,
        "--gpu", "0" if torch.cuda.is_available() else "-",  # CUDA가 없으면(Mac 등) CPU로 추출
        "--cpu_cores", str(cpu_cores),
        "--pitch_guidance", "True",
        "--f0_method", "rmvpe"
    ]
    await run_command_async(extract_command, model_name, "extract")  # 비동기 실행

    sliced_audio_dir = os.path.join(".", "logs", model_name, "sliced_audios_16k")
    sliced_audio_files = os.listdir(sliced_audio_dir)
    if len(sliced_audio_files) <= 10:
        # 파일이 10개 이하일 경우 500 에러 반환 및 fail 파일 생성
        fail_file_path = os.path.join(".", "logs", model_name, "fail")
        with open(fail_file_path, "w") as f:
            f.write("모델 생성 실패: sliced_audios_16k 폴더에 파일이 10개 이하입니다.")
        raise HTTPException(status_code=500, detail="모델 생성 실패: sliced_audios_16k 폴더에 파일이 10개 이하입니다.")
    # --- 4. Train 실행 ---
    train_command = [
        sys.executable,
        "rvc_cli.py",
        "train",
        "--model_name", model_name,
        "--rvc_version", "v2",
        "--sample_rate", sample_rate,
        "--total_epoch", "2",
        "--pitch_guidance", "True",
        "--save_every_epoch", "2",
        "--save_only_latest", "True",
        "--pretrained", "True"
    ]
    #"--gpu", "0"  # GPU 사용 시 설정
    await run_command_async(train_command, model_name, "train")  # 비동기 실행

            # 모델 파일 경로 찾기

    model_dir = os.path.join(
        ".", "logs", model_name
    )  # os.path.join 사용
    pth_files = [
        f for f in os.listdir(model_dir) if f.endswith(".pth") and "_2e_" in f  
    ]  # model_name 포함된 파일만 추가
    index_files = [
        f
        for f in os.listdir(model_dir)
        if f.startswith("added_") and f.endswith(".index")
    ]

    if not pth_files:
        raise FileNotFoundError(f"No .pth file found in {model_dir}")
    if not index_files:
        raise FileNotFoundError(
            f"No 'added_*.index' file found in {model_dir}"
        )

    pth_path = os.path.join(
        model_dir, pth_files[0]
    )  # os.path.join 사용
    index_path = os.path.join(
        model_dir, index_files[0]
    )  # os.path.join 사용

    # --- 5. autopitch 실행 ---
    '''
    pitch_command = [
        sys.executable,
        "rvc_cli.py",
        "infer",
        "--input_path", "pitchtest/temp.ogg",  # 테스트 음성 파일 경로
        "--output_path", f"logs/{model_name}/after.ogg",  # 출력 음성 파일 경로
        "--pth_path", pth_path,
        "--index_path", index_path,
        "--f0_method", "rmvpe",
        "--export_format", "WAV",
        "--pitch", "0"  # 초기 피치 값 설정
    ]
    await run_command_async(pitch_command, model_name, "autopitch")  # 비동기 실행
    # --- 6. 피치 최적화 ---

    print(f"[Model {model_name}] autopitch 단계 시작...")
    best_pitch = await find_optimal_pitch(dataset_path, f"logs/{model_name}/after.wav", model_name, pth_path, index_path)
    print(f"최적의 피치 값: {best_pitch}")
    '''
    
    # --- 7. 피치 값 저장 ---
    best_pitch = 0
    with open(os.path.join(".", "logs", model_name, "pitch.txt"), "w") as f:
        f.write(f"{best_pitch}")
    print(f"[Model {model_name}] autopitch 단계 완료.")
