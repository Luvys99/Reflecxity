# 학습 파이프라인: 녹음 합치기 → UVR → preprocess → extract → train → index → 결과 확인 → 자동 피치
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (학습 워커 → Redis)
import os
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor

import torch
import librosa
import numpy as np
import soundfile as sf
from fastapi import HTTPException

from auto_pitch import save_auto_pitch
from command import run_command

executor = ThreadPoolExecutor()

# 학습 기본값 (요청에 값이 없으면 이 값으로 학습한다)
DEFAULT_SAMPLE_RATE = "40000"
DEFAULT_CPU_CORES = 4

# 학습 횟수 (녹음 전체를 몇 번 훑나). 2는 결과가 거의 기계음이었고, 10부터 녹음 주인이 듣기에 괜찮았고 20·30은 10과 차이가 거의 없었다 (#65)
TRAIN_EPOCHS = 10


# 학습 전 준비: 이전 학습의 실패 표시(logs/{uuid}/fail)를 지우고, 녹음 폴더와 녹음 파일 목록을 돌려준다
# 녹음 폴더가 없으면 FileNotFoundError
def prepare_training(user_uuid):
    dataset_path = os.path.join("user", user_uuid, "raw")
    fail_file_path = os.path.join(".", "logs", user_uuid, "fail")
    if os.path.exists(fail_file_path):
        os.remove(fail_file_path)
    voice_file_names = [
        f for f in os.listdir(dataset_path) if f.endswith(".m4a") or f.endswith(".ogg") or f.endswith(".wav")
    ]
    return dataset_path, voice_file_names

# 백그라운드 작업 함수 생성
async def combine_audio(user_uuid, dataset_path, voice_file_names):
    sample_rate = 22050
    combined_audio = []
    try:
        if len(voice_file_names) != 1:
            for file_name in voice_file_names:
                # librosa.load를 비동기적으로 실행 (익명 함수를 사용하여 sr 인수 전달)
                audio = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    lambda: librosa.load(os.path.join(dataset_path, file_name), sr=sample_rate)
                )
                combined_audio.append(audio[0])
            combined_audio = np.concatenate(combined_audio)
            voice_file = os.path.join(dataset_path, "combined.wav")

            # sf.write를 비동기적으로 실행
            await asyncio.get_event_loop().run_in_executor(
                executor, sf.write, voice_file, combined_audio, sample_rate
            )

            for i in range(len(voice_file_names)):
                os.remove(os.path.join(dataset_path, voice_file_names[i]))
            print(f"[Model {user_uuid}] 음성 파일 병합 완료")
            return voice_file
        else:
            print("오디오 파일이 하나만 존재합니다. 기존 방식으로 처리됩니다.")
            return os.path.join(dataset_path, voice_file_names[0])
    except Exception as e:
        print(f"[Model {user_uuid}] 음성 파일 병합 중 오류 발생: {e}")

# 비동기 모델 생성 작업 (모델 서버에서 비동기 처리)
async def train_voice_model(user_uuid, dataset_path, sample_rate, cpu_cores, voice_file_names):
    # --- 0. 음성 통합 시스템 실행 ---
    voice_file = await combine_audio(user_uuid, dataset_path, voice_file_names)
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
    separated_voice_files = [
        f for f in os.listdir(dataset_path) if f.endswith(".ogg")
    ]
    if not separated_voice_files:
        await run_command(uvr_command, user_uuid, "uvr")  # 비동기 실행
        original_voice_files = [
        f for f in os.listdir(dataset_path) if f.endswith(".wav") or f.endswith(".m4a")
        ]
        original_voice_path = os.path.join(dataset_path, original_voice_files[0])
        os.remove(original_voice_path)
        print("노이즈 제거 음성 파일 존재")
    else:
        print("노이즈 제거 음성 파일 없음 혹은 이미 UVR처리 종료됨")

    # --- 2. Preprocess 실행 ---
    preprocess_command = [
        sys.executable,
        "rvc_cli.py",
        "preprocess",
        "--model_name", user_uuid,
        "--dataset_path", dataset_path,
        "--sample_rate", sample_rate,
        "--cpu_cores", str(cpu_cores)
    ]
    await run_command(preprocess_command, user_uuid, "preprocess")  # 비동기 실행

    # --- 3. Extract 실행 ---
    extract_command = [
        sys.executable,
        "rvc_cli.py",
        "extract",
        "--model_name", user_uuid,
        "--rvc_version", "v2",
        "--sample_rate", sample_rate,
        "--gpu", "0" if torch.cuda.is_available() else "-",  # CUDA가 없으면(Mac 등) CPU로 추출
        "--cpu_cores", str(cpu_cores),
        "--pitch_guidance", "True",
        "--f0_method", "rmvpe"
    ]
    await run_command(extract_command, user_uuid, "extract")  # 비동기 실행

    sliced_audio_dir = os.path.join(".", "logs", user_uuid, "sliced_audios_16k")
    sliced_audio_files = os.listdir(sliced_audio_dir)
    if len(sliced_audio_files) <= 10:
        # 파일이 10개 이하일 경우 500 에러 반환 및 fail 파일 생성
        fail_file_path = os.path.join(".", "logs", user_uuid, "fail")
        with open(fail_file_path, "w") as f:
            f.write("모델 생성 실패: sliced_audios_16k 폴더에 파일이 10개 이하입니다.")
        raise HTTPException(status_code=500, detail="모델 생성 실패: sliced_audios_16k 폴더에 파일이 10개 이하입니다.")
    # --- 4. Train 실행 ---
    train_command = [
        sys.executable,
        "rvc_cli.py",
        "train",
        "--model_name", user_uuid,
        "--rvc_version", "v2",
        "--sample_rate", sample_rate,
        "--total_epoch", str(TRAIN_EPOCHS),
        "--pitch_guidance", "True",
        "--save_every_epoch", str(TRAIN_EPOCHS),  # 마지막 epoch에만 모델 파일(.pth)을 만든다
        "--save_only_latest", "True",
        "--pretrained", "True"
    ]
    #"--gpu", "0"  # GPU 사용 시 설정
    await run_command(train_command, user_uuid, "train")  # 비동기 실행

    # 학습 결과 확인: 모델(.pth)이나 인덱스(added_*.index)가 없으면 학습 실패로 본다
    model_dir = os.path.join(".", "logs", user_uuid)
    pth_files = [
        f for f in os.listdir(model_dir) if f.endswith(".pth") and f"_{TRAIN_EPOCHS}e_" in f
    ]
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

    # --- 5. 자동 피치 ---
    # 녹음 높이를 재서 TTS 피치를 저장한다 (#59). 실패해도 학습은 성공으로 둔다 (TTS는 기본 피치를 쓴다)
    try:
        voice_f0_hz, pitch = await asyncio.get_event_loop().run_in_executor(executor, save_auto_pitch, user_uuid, dataset_path)
        if pitch is None:
            print(f"[Model {user_uuid}] 자동 피치: 녹음 높이를 잴 수 없어 기본 피치를 쓴다")
        else:
            print(f"[Model {user_uuid}] 자동 피치: 녹음 {voice_f0_hz:.0f}Hz → 피치 {pitch:+d}")
    except Exception as e:
        print(f"[Model {user_uuid}] 자동 피치 실패, 기본 피치를 쓴다: {e}")
