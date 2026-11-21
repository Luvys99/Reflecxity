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
from fastapi import FastAPI, HTTPException, File, UploadFile, Path
from typing import Optional
from command import run_command_async

from pydub import AudioSegment
import asyncio  # asyncio를 임포트
import time
from concurrent.futures import ThreadPoolExecutor
from scipy.spatial.distance import cdist  # DTW를 위한 라이브러리 추가 

executor = ThreadPoolExecutor()

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

# 사용자 삭제 기능 추가 (폴더 존재 여부 판단 개선)
@app.delete(
    "/user/{user_uuid}",
    tags=["사용자"],
    summary="사용자 폴더 삭제",
    description="`user/{user_uuid}/`(녹음)와 `logs/{user_uuid}/`(학습 결과, 모델)를 지운다.",
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
