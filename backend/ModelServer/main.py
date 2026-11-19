import os

# torch와 faiss가 각자 OpenMP를 들고 와서 Mac에서 RVC 변환이 멈추는 문제를 피한다.
# torch를 import하기 전에 설정해야 하고, 서버가 실행하는 하위 프로세스(rvc_cli.py 등)도 이 값을 물려받는다.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys
import torch
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
from command import run_command_async
from training import create_model_async, prepare_training, DEFAULT_SAMPLE_RATE, DEFAULT_CPU_CORES
from tts import find_model_files, synthesize_voice

from pydub import AudioSegment
import asyncio  # asyncio를 임포트
import time
from fastapi.background import BackgroundTasks
from concurrent.futures import ThreadPoolExecutor
from scipy.spatial.distance import cdist  # DTW를 위한 라이브러리 추가 

executor = ThreadPoolExecutor()
status_manager = StatusManager()

app = FastAPI()

@app.get(
    "/online",
    tags=["상태"],
    summary="서버 상태 확인",
    description="서버가 떠 있으면 `{\"status\": \"online\"}`.",
)
async def check_online():
    return {"status": "online"}

# 파일 저장 기능 추가
@app.post(
    "/user/{user_uuid}/upload",
    tags=["녹음 파일"],
    summary="녹음 업로드",
    description="`user/{user_uuid}/raw/`에 그대로 저장한다.",
)
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
@app.get(
    "/user/{user_uuid}/files",
    tags=["녹음 파일"],
    summary="업로드한 파일 목록",
    description="`user/{user_uuid}/raw/`의 파일 이름 목록.",
)
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
@app.delete(
    "/user/{user_uuid}/raw/{filename}",
    tags=["녹음 파일"],
    summary="업로드한 파일 삭제",
    description="`user/{user_uuid}/raw/{filename}`을 지운다.",
)
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
@app.get(
    "/user/{user_uuid}/raw/{filename}",
    tags=["녹음 파일"],
    summary="파일 받기",
    description="주소에 `raw`가 있지만 실제로는 `user/{user_uuid}/{filename}`(raw 폴더가 아님)을 내려준다. TTS 결과 `convert.wav`를 받을 때 쓴다.",
)
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
@app.delete(
    "/user/{user_uuid}",
    tags=["사용자"],
    summary="사용자 폴더 삭제",
    description="`user/{user_uuid}/`(녹음, TTS 결과)와 `logs/{user_uuid}/`(학습 결과, 모델)를 지운다.",
)
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
@app.get(
    "/user/{user_uuid}/modelcheck",
    tags=["학습"],
    summary="학습 완료 확인",
    description="학습 상태(`user/{user_uuid}/status.json`의 `train`)가 `fail`이거나 `logs/{user_uuid}/fail` 파일이 있으면 \"모델 생성 실패\", `pitch.txt`가 있으면 \"모델 파일 존재\", 그 외는 \"모델 파일 없음\"(진행 중). 실패 원인은 `GET /user/{user_uuid}/status`의 `train_error`.",
)
def check_model_files(user_uuid: str):
    # 학습 상태가 fail이면 실패 (run_training이 어떤 에러든 기록한다)
    # UVR 단계에서 실패하면 logs 폴더가 아직 없으므로, 폴더를 읽기 전에 맨 앞에서 본다
    if status_manager.get_status(user_uuid).get("train") == "fail":
        return {"message": "모델 생성 실패"}
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



# 모델 생성 요청 처리 함수 (비동기 처리 추가)
@app.post(
    "/models",
    tags=["학습"],
    summary="학습 시작",
    description="백그라운드로 학습 파이프라인을 실행하고 바로 응답한다: 녹음 합치기 → UVR(잡음 제거, `raw/`에 .ogg가 있으면 건너뜀) → preprocess(자르기) → extract(음높이·음색) → train(2 epoch) → index → pitch 찾기(`pitch.txt`). 각 단계는 `rvc_cli.py` / `uvr_cli.py`를 하위 프로세스로 실행한다.",
)
async def create_model(background_tasks_model: BackgroundTasks, model_data: dict = Body(...)):  # 인수 순서 변경
    try:
        # 요청 데이터에서 필요한 정보 추출 (model_name 제외)
        user_uuid = model_data.get("user_uuid")
        sample_rate = model_data.get("sample_rate", DEFAULT_SAMPLE_RATE)
        cpu_cores = model_data.get("cpu_cores", DEFAULT_CPU_CORES)
        # 입력값 검증
        if not user_uuid:
            raise ValueError("user_uuid is required")

        dataset_path, voice_file_name = prepare_training(user_uuid)

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

        # 응답하기 전에 상태를 progress로 바꾼다 (이전 학습의 fail이 남아 있으면 Main이 바로 실패로 읽기 때문)
        status_manager.update_status(user_uuid=model_name, task="train", value="progress")
        status_manager.update_status(user_uuid=model_name, task="train_error", value="")

        # 모델 생성 작업을 백그라운드에서 실행
        background_tasks_model.add_task(run_training, model_name, dataset_path, sample_rate, cpu_cores, voice_file_name)

        # 즉시 응답 반환
        return {
            "message": "모델 생성 작업이 백그라운드에서 실행 중입니다.",
            "model_id": model_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"모델 생성 중 오류 발생: {e}")

# 학습을 실행하고 결과(성공 / 실패 + 원인)를 상태 파일에 남긴다
# create_model_async 안의 어느 단계에서 에러가 나도 여기서 잡아 fail로 기록한다 (#11)
async def run_training(model_name, dataset_path, sample_rate, cpu_cores, voice_file_name):
    try:
        await create_model_async(model_name, dataset_path, sample_rate, cpu_cores, voice_file_name)
        status_manager.update_status(user_uuid=model_name, task="train", value="success")
    except Exception as e:
        reason = e.detail if isinstance(e, HTTPException) else f"{type(e).__name__}: {e}"
        print(f"[Model {model_name}] 학습 실패: {reason}")
        status_manager.update_status(user_uuid=model_name, task="train", value="fail")
        status_manager.update_status(user_uuid=model_name, task="train_error", value=reason)





# 상태 확인 api
@app.get(
    "/user/{user_uuid}/status",
    tags=["TTS"],
    summary="TTS 상태",
    description="`user/{user_uuid}/status.json` (`status.py`). `tts`: idle / progress / success / fail. `train`: progress / success / fail, `train_error`: 학습 실패 원인.",
)
def get_user_status(user_uuid: str):
    status = status_manager.get_status(user_uuid)
    return status

# TTS 실행 함수
@app.post(
    "/tts",
    tags=["TTS"],
    summary="TTS (텍스트 → 내 목소리)",
    description="상태를 progress로 바꾸고 백그라운드로 실행한 뒤 바로 응답한다: edge-tts로 영어 기계 음성(`temptts/{user_uuid}_{무작위}.ogg`, 요청마다 따로, 끝나면 지움) → 학습한 모델(.pth, .index)로 RVC 변환 → `user/{user_uuid}/convert.wav`. 끝나면 success, 에러면 fail.",
)
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

        pth_path, index_path = find_model_files(user_uuid)
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
        await synthesize_voice(user_uuid, tts_text, pitch, pth_path, index_path)

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
            sys.executable,
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
