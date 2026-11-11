import os
import uuid
import subprocess
import librosa
import numpy as np
import shutil
import soundfile as sf
from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Path
from fastapi.responses import FileResponse
from typing import Optional
from status import StatusManager  # status.py 임포트

from pydub import AudioSegment
import asyncio  # asyncio를 임포트
from fastapi.background import BackgroundTasks
from concurrent.futures import ThreadPoolExecutor
from scipy.spatial.distance import cdist  # DTW를 위한 라이브러리 추가 

executor = ThreadPoolExecutor()
status_manager = StatusManager()

app = FastAPI()

@app.get("/online")
async def check_online():
    return {"status": "online"}

# 파일 저장 기능 추가
@app.post("/user/{user_uuid}/upload")
async def upload_file(user_uuid: str, file: UploadFile = File(...)):
    try:
        # 파일 저장 (user_uuid 폴더에 저장)
        user_folder = os.path.join(".", "user", user_uuid, "raw")
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        return {"message": "파일 업로드 성공", "file_path": file_path}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 중 오류 발생: {e}")

# 파일 검색 기능 추가
@app.get("/user/{user_uuid}/files")
def get_user_files(user_uuid: str):
    try:
        user_folder = os.path.join(".", "user", user_uuid, "raw")
        files = [
            f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))
        ]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 중 오류 발생: {e}")

# 파일 삭제 기능 추가
@app.delete("/user/{user_uuid}/raw/{filename}")
async def delete_file(user_uuid: str, filename: str):
    try:
        file_path = os.path.join(".", "user", user_uuid, "raw", filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"message": "파일 삭제 성공"}
        else:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없음")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 삭제 중 오류 발생: {e}")

# 파일 다운로드 기능 추가 
@app.get("/user/{user_uuid}/raw/{filename}")
async def download_file(user_uuid: str, filename: str):
    try:
        file_path = os.path.join(".", "user", user_uuid, filename)
        if os.path.exists(file_path):
            return FileResponse(
                file_path,
                media_type="audio/wav",  # 파일 타입 명시
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        else:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없음")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 다운로드 중 오류 발생: {e}")

# 사용자 삭제 기능 추가 (폴더 존재 여부 판단 개선)
@app.delete("/user/{user_uuid}")
def delete_user(user_uuid: str):
    try:
        # 사용자 폴더 경로
        user_path = os.path.join(".", "user", user_uuid)
        user_model_path = os.path.join(".", "logs", user_uuid)

        # 폴더 존재 여부를 확인하여 삭제
        if os.path.exists(user_path) or os.path.exists(user_model_path):
            if os.path.exists(user_path):
                print(f"폴더 {user_path} 존재. 삭제를 시도합니다.")
                # 폴더 삭제
                shutil.rmtree(user_path)
                print(f"폴더 {user_path} 삭제 성공.")

            if os.path.exists(user_model_path):
                print(f"폴더 {user_model_path} 존재. 삭제를 시도합니다.")
                # 폴더 삭제
                shutil.rmtree(user_model_path)
                print(f"폴더 {user_model_path} 삭제 성공.")

            return {"message": "사용자 및 파일 삭제 성공"}
        else:
            # 둘 다 없을 경우 에러 발생시키지 않고 메시지 반환
            print(f"폴더 {user_path}와 {user_model_path}가 존재하지 않음.")
            return {"message": "사용자를 찾을 수 없습니다."}

    except Exception as e:
        print(f"사용자 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 삭제 중 오류 발생: {e}")

# 모델 파일 존재 확인 API 추가
@app.get("/user/{user_uuid}/modelcheck")
def check_model_files(user_uuid: str):
    try:
        model_dir = os.path.join(".", "logs", user_uuid)
        pitch = [f for f in os.listdir(model_dir) if "pitch.txt" in f]
        fail_file_path = os.path.join(model_dir, "fail")
        '''
        pth_files = [
            f for f in os.listdir(model_dir) if f.endswith(".pth") and user_uuid in f
        ]
        index_files = [
            f
            for f in os.listdir(model_dir)
            if f.startswith("added_") and f.endswith(".index")
        ]
        '''
        # fail 파일 존재 여부 확인
        if os.path.exists(fail_file_path):
            return {"message": "모델 생성 실패"}
        if pitch:
            return {"message": "모델 파일 존재"}
        else:
            return {"message": "모델 파일 없음"}
    
    except FileNotFoundError:
        return {"message": "모델 파일 없음"}  # 모델 폴더가 없을 경우 예외 처리
        #raise HTTPException(status_code=500, detail=f"모델 파일 확인 중 오류 발생: {e}")
    except Exception as e:
        # 예외 발생 시 에러 메시지 반환 (오류 메시지 출력)
        print(f"모델 파일 확인 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"모델 파일 확인 중 오류 발생: {e}") 

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


# 모델 생성 요청 처리 함수 (비동기 처리 추가)
@app.post("/models")
async def create_model(background_tasks_model: BackgroundTasks, model_data: dict = Body(...)):  # 인수 순서 변경
    try:
        # 요청 데이터에서 필요한 정보 추출 (model_name 제외)
        user_uuid = model_data.get("user_uuid")
        dataset_path = os.path.join("user", user_uuid, "raw")
        sample_rate = model_data.get("sample_rate", "40000")
        cpu_cores = model_data.get("cpu_cores", 4)
        fail_file_path = os.path.join(".", "logs", user_uuid, "fail")
        # 입력값 검증
        if not user_uuid:
            raise ValueError("user_uuid is required")
        
        # fail_file_path가 존재할 경우에만 삭제
        if os.path.exists(fail_file_path):
            os.remove(fail_file_path)
        print("test")
        # 모델 이름을 user_uuid 사용
        
        voice_file_name = [
            f for f in os.listdir(dataset_path) if f.endswith(".m4a") or f.endswith(".ogg") or f.endswith(".wav") 
        ]

        if voice_file_name:
            # voice_file_name에서 첫 번째 파일을 선택
            voice_file = os.path.join(dataset_path, voice_file_name[0])
            print("음성 파일 존재")
        else:
            print("음성 파일 없음")

        
        model_name = user_uuid
        model_id = model_name
       

        #for file_path in file_paths:
        #    audio, _ = librosa.load(file_path, sr=sr)
        # --- m4a 파일을 ogg 파일로 변환 ---
        '''for filename in os.listdir(dataset_path):
            if filename.endswith(".m4a"):
                m4a_file = os.path.join(dataset_path, filename)
                ogg_file = os.path.join(dataset_path, filename[:-4] + ".ogg")  # 확장자 변경
                convert_m4a_to_ogg(m4a_file, ogg_file)
                print(f"Converted {filename} to ogg format.")
                # 기존 m4a 파일 삭제
                os.remove(m4a_file)  # 기존 m4a 파일 삭제
                print(f"Removed {filename}")'''

        # 모델 생성 작업을 백그라운드에서 실행
        background_tasks_model.add_task(create_model_async, model_name, dataset_path, sample_rate, cpu_cores, voice_file_name)

        # 즉시 응답 반환
        return {
            "message": "모델 생성 작업이 백그라운드에서 실행 중입니다.",
            "model_id": model_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"모델 생성 중 오류 발생: {e}")

# 비동기 모델 생성 작업 (모델 서버에서 비동기 처리)
async def create_model_async(model_name, dataset_path, sample_rate, cpu_cores, voice_file_name):
    # --- 0. 음성 통합 시스템 실행 ---
    
    sr = 40000
    combined_audio = []
    voice_file = await combine_audio(model_name, dataset_path, voice_file_name)
    # --- 1. Uvr 실행 ---
    print(voice_file)
    uvr_command = [
        "env\\python.exe",
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
        "env\\python.exe",
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
        "env\\python.exe",
        "rvc_cli.py",
        "extract",
        "--model_name", model_name,
        "--rvc_version", "v2",
        "--sample_rate", sample_rate,
        "--gpu", "0",
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
        "env\\python.exe",
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
        "env\\python.exe",
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


# 모델 명령어 실행 함수 (비동기 처리)

async def run_command_async(command, model_id, step_name):
    process = None
    try:
        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 시작...")

        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        async def print_stdout_logs():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                print(f"[Model {model_id}] {line.decode('utf-8', errors='ignore').strip()}")

        async def print_stderr_logs():
            while True:
                err_line = await process.stderr.read(1024)
                if not err_line:
                    break
                print(f"[Model {model_id}] LOG: {err_line.decode('utf-8', errors='ignore').strip()}")

        stdout_task = asyncio.create_task(print_stdout_logs())
        stderr_task = asyncio.create_task(print_stderr_logs())

        await process.wait()

        await stdout_task
        await stderr_task

        if process.returncode != 0:
            raise RuntimeError(
                f"{step_name} 단계 실행 중 오류 발생: 프로세스 종료 코드 {process.returncode}"
            )

        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 완료")

    except Exception as e:
        print(f"[Model {model_id}] {step_name} 단계 실행 중 오류 발생: {e}")
        if process and process.returncode is None:
            process.kill()  # 프로세스 강제 종료
            await process.wait()  # 프로세스가 완전히 종료될 때까지 대기
        raise e


# 상태 확인 api
@app.get("/user/{user_uuid}/status")
def get_user_status(user_uuid: str):
    status = status_manager.get_status(user_uuid)
    return status

# TTS 실행 함수
@app.post("/tts")
async def synthesize_tts(background_tasks_tts: BackgroundTasks, tts_data: dict = Body(...)):
    try:
        user_uuid = tts_data.get("user_uuid")
        status_manager.update_status(user_uuid=user_uuid, task="tts", value="progress") # TTS 작업 시작 시 "progress" 상태로 변경
        tts_text = tts_data.get("tts_text")
        pitch = tts_data.get("pitch")  # 기본값 설정

        # 입력값 검증
        if not user_uuid:
            raise ValueError("user_uuid is required")
        if not tts_text:
            raise ValueError("tts_text is required")

        # 모델 파일 경로 찾기
        model_dir = os.path.join(
            ".", "logs", user_uuid
        )  # os.path.join 사용

        pth_files = [
            f for f in os.listdir(model_dir) if f.endswith(".pth") and user_uuid in f  
        
        ]  # user_uuid가 포함된 파일만 추가

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
        status_manager.update_status(user_uuid=user_uuid, task="tts", value="progress")
        print("testing")
        background_tasks_tts.add_task(synthesize_tts_async, pth_path, index_path, tts_text, user_uuid, pitch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"TTS 합성 중 오류 발생: {e}"
        )

async def synthesize_tts_async(pth_path, index_path, tts_text, user_uuid, pitch):
    try:
        # TTS 명령어 실행
        tts_command = [
            "env\\python",
            "rvc_cli.py",
            "tts",
            "--tts_text",
            tts_text,
            "--tts_voice",
            "en-US-AndrewMultilingualNeural",
            "--output_tts_path",
            os.path.join(".", "temptts", "temp.ogg"),  # os.path.join 사용
            "--output_rvc_path",
            os.path.join(
                ".", "user", user_uuid, "convert.wav"
            ),  # os.path.join 사용
            "--pth_path",
            pth_path,
            "--index_path",
            index_path,
            "--export_format",
            "WAV",
            "--pitch",
            str(pitch)
        ]
        '''
        # pitch.txt 파일에서 피치 값 읽기
        pitch_file_path = os.path.join(".", "logs", user_uuid, "pitch.txt")
        if os.path.exists(pitch_file_path):
            with open(pitch_file_path, "r") as f:
                pitch = int(f.read())  # 읽은 피치 값을 정수형으로 변환
            print(f"pitch.txt에서 피치 값 {pitch}를 읽었습니다.")
            tts_command.extend(["--pitch", str(pitch)])  # tts_command에 pitch 값 추가
        else:
            print(f"pitch.txt 파일이 존재하지 않습니다. 기본 피치 값을 사용합니다.")
        '''
        await run_command_async(tts_command, user_uuid, "TTS")        

        # convert.m4a 파일 경로
        output_m4a_path = os.path.join(
            ".", "user", user_uuid, "convert.wav"
        )  # os.path.join 사용

        # 파일 존재 확인
        if not os.path.exists(output_m4a_path):
            raise HTTPException(
                status_code=500, detail="TTS wav 파일을 찾을 수 없습니다."
            )

        status_manager.update_status(user_uuid=user_uuid, task="tts", value="success")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        status_manager.update_status(user_uuid=user_uuid, task="tts", value="fail")  # TTS 실패 시 "fail" 상태로 변경
        raise HTTPException(
            status_code=500, detail=f"TTS 합성 중 오류 발생: {e}"
        )


def convert_m4a_to_ogg(m4a_file: str, ogg_file: str):
    try:
        audio = AudioSegment.from_file(m4a_file, format="m4a")
        # Opus 코덱으로 ogg 파일로 변환
        audio.export(ogg_file, format="ogg", codec="libopus")  # libopus 코덱 사용
        print(f"Converted {m4a_file} to Opus (ogg) format.")
    except Exception as e:
        print(f"Error converting m4a to ogg: {e}")

async def run_internal_code():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, blocking_task)

# 명령어 실행 함수 (Python 3.9 버전에 맞게 수정)
'''
async def run_command(command, model_id, step_name):
    try:
        print(step_name)
        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 시작...?")
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # 실시간 로그 출력
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                print(f"[Model {model_id}] {output.strip()}")

        # stderr에서도 오류가 발생하는지 확인
        stderr = process.stderr.read()
        if process.returncode != 0:
            raise RuntimeError(
                f"{step_name} 단계 실행 중 오류 발생: {stderr.strip()}"
            )
        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 완료.")
    except Exception as e:
        print(f"[Model {model_id}] {step_name} 단계 실행 중 오류 발생: {e}")
        raise e
'''
async def find_optimal_pitch(dataset_path, target_file, model_name, pth_path, index_path):
    """
    target_file과 dataset_path 아래의 ogg 파일들과의 유사도를 비교하여 가장 유사한 피치 값을 반환합니다.
    """
    original_ogg_files = [
        f for f in os.listdir(dataset_path) if f.endswith(".ogg")
    ]
    if not original_ogg_files:
        return 0  # 오리지널 ogg 파일이 없는 경우 기본 값 0 반환

    best_pitch = 0
    highest_similarity = -999999999
    originall_audio, originall_audio_sr = await asyncio.get_event_loop().run_in_executor(
        executor, lambda: librosa.load(os.path.join(dataset_path, original_ogg_files[0]))
    )

    # 음성이 있는 구간만 추출
    samples = int(20 * originall_audio_sr)
    originall_audio = originall_audio[:samples]
    #print(f"샘플링 확인 :{originall_audio_sr}")

    # librosa.feature.mfcc를 비동기적으로 실행
    mfccs2 = await asyncio.get_event_loop().run_in_executor(
        executor,
        lambda: librosa.feature.mfcc(y=originall_audio, sr=originall_audio_sr, n_mfcc=100, n_fft=int(originall_audio_sr*0.025), hop_length=int(originall_audio_sr*0.01))
    )
    # -5부터 5까지의 범위에서 피치 값을 비교
    for i in range(0, 24):  # 피치 값 범위 설정
        print(f"피치 비교중 {i}")
        pitch_command = [
            "env\\python.exe",
            "rvc_cli.py",
            "infer",
            "--input_path", "pitchtest/temp.ogg", 
            "--output_path", f"logs/{model_name}/after.wav", 
            "--pth_path", pth_path,
            "--index_path", index_path,
            "--f0_method", "rmvpe",
            "--export_format", "WAV",
            "--pitch", str(i) 
        ]
        await run_command_async(pitch_command, model_name, "autopitch")

        original_ogg_path = os.path.join(dataset_path, original_ogg_files[0])
        similarity = await calculate_audio_similarity(
            f"logs/{model_name}/after.wav", mfccs2, originall_audio_sr
        )
        print(similarity)
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_pitch = i
            print(f"현재 best 피치값 {best_pitch}")
    
    best_pitch = best_pitch - 6
    print(f"최종 best 피치값 {best_pitch}")
    return best_pitch


async def calculate_audio_similarity_mfcc_dtw(file1, mfccs2, originall_audio_sr):
    """
    두 오디오 파일의 MFCC를 추출하고 DTW를 사용하여 유사도를 계산합니다.
    """
    # MFCC 추출
    y1, sr1 = librosa.load(file1)

    # 샘플링 레이트가 다르면 조정
    if sr1 != originall_audio_sr:
        y1 = librosa.resample(y1, sr1, originall_audio_sr)

    # 음성이 있는 구간만 추출
    seconds = 20
    samples = int(seconds * originall_audio_sr)
    y1 = y1[:samples]
    mfccs1 = librosa.feature.mfcc(y=y1, sr=originall_audio_sr, n_mfcc=100, n_fft=int(originall_audio_sr*0.025), hop_length=int(originall_audio_sr*0.01))

    # DTW를 사용하여 유사도 계산
    # DTW 알고리즘은 라이브러리에 따라 다를 수 있습니다.
    # 여기서는 scipy.spatial.distance.cdist를 사용합니다.
    dtw_distance = cdist(mfccs1.T, mfccs2.T, metric="euclidean")
    # DTW 거리의 평균을 유사도로 계산 (낮은 거리는 높은 유사도)
    similarity = 1 / (np.mean(dtw_distance) + 1)  # 거리 값을 역으로 곱하여 유사도 반환

    return similarity

async def calculate_audio_similarity(file1, mfccs2, originall_audio_sr):
    """
    두 오디오 파일의 MFCC를 추출하고 DTW를 사용하여 유사도를 계산합니다.
    """
    # librosa.load를 비동기적으로 실행
    y1, sr1 = await asyncio.get_event_loop().run_in_executor(
        executor, lambda: librosa.load(file1)
    )

    # 샘플링 레이트가 다르면 조정
    if sr1 != originall_audio_sr:
        y1 = await asyncio.get_event_loop().run_in_executor(
            executor, lambda: librosa.resample(y1, sr1, originall_audio_sr)
        )

    # 음성이 있는 구간만 추출
    seconds = 20
    samples = int(seconds * originall_audio_sr)
    y1 = y1[:samples]

    # librosa.feature.mfcc를 비동기적으로 실행
    mfccs1 = await asyncio.get_event_loop().run_in_executor(
        executor,
        lambda: librosa.feature.mfcc(y=y1, sr=originall_audio_sr, n_mfcc=100, n_fft=int(originall_audio_sr*0.025), hop_length=int(originall_audio_sr*0.01))
    )

    # MFCC 코사인 유사도 계산 (비동기 처리 추가)
    similarity = await asyncio.get_event_loop().run_in_executor(
        executor,
        lambda: mfccs1.dot(mfccs2.T) / (np.linalg.norm(mfccs1) * np.linalg.norm(mfccs2))
    )

    
    return np.mean(similarity)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=48000)
