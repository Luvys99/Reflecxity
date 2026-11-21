import logging
import os
import configparser
from typing import List, Optional
import time
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import requests
from dotenv import load_dotenv

from db_manager import DBManager
from utils import is_allowed_file, generate_uuid
from train_queue import (
    connect_redis, create_group_if_missing, enqueue_train_job, find_train_job,
    count_jobs_ahead, measure_working_ms, count_train_jobs_by_status,
)
from tts_queue import enqueue_tts_job, wait_for_tts_result

# 로그 설정: 시간과 함께 출력
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 설정 파일 불러오기
config = configparser.ConfigParser()
config.read('config.ini')

# 컴퓨터마다 다른 값(DB 계정, Model Server 주소)은 환경 변수로 받는다
# .env 파일이 있으면 그 값을 환경 변수로 읽는다 (.env는 git에 올리지 않음, 예시는 .env.example)
load_dotenv()

def get_setting(env_name, section, key):
    """환경 변수가 있으면 그 값을, 없으면 config.ini 값을 쓴다"""
    value = os.environ.get(env_name) or config.get(section, key, fallback=None)
    if not value:
        raise RuntimeError(f"설정 {env_name}이(가) 없습니다. .env 또는 환경 변수에 넣어 주세요 (.env.example 참고)")
    return value

# DB 정보
DB_CONFIG = {
    "host": get_setting('DB_HOST', 'DATABASE', 'host'),
    "user": get_setting('DB_USER', 'DATABASE', 'user'),
    "password": get_setting('DB_PASSWORD', 'DATABASE', 'password'),
    "database": get_setting('DB_NAME', 'DATABASE', 'database'),
}

# Model Server 주소 (.env 값이 있으면 config.ini 값을 덮어쓴다)
config['MODEL_SERVER']['api_url'] = get_setting('MODEL_SERVER_URL', 'MODEL_SERVER', 'api_url')

# 녹음으로 받는 형식. 학습(ModelServer training.prepare_training)이 녹음으로 읽는 형식과 같게 둔다 (#60)
ALLOWED_EXTENSIONS = {"m4a", "ogg", "wav"}

# Redis 연결은 서버의 이벤트 루프 안에서 만든다 (아래 startup). 비동기 연결은 처음 쓰인 루프에 묶인다
redis_client = None
redis_binary_client = None  # TTS 결과(음성 bytes)용

db_manager = DBManager(DB_CONFIG)
db_manager.create_table()

# Swagger(/docs)에서 Execute 결과 아래에 걸린 시간을 표시한다 (#15)
app = FastAPI(swagger_ui_parameters={"displayRequestDuration": True})

@app.on_event("startup")
async def connect_redis_queues():
    global redis_client, redis_binary_client
    redis_client = connect_redis()
    redis_binary_client = connect_redis(decode_responses=False)
    await create_group_if_missing(redis_client)

origins = config.get('CORS', 'origins').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_SERVER_API_URL = config.get('MODEL_SERVER', 'api_url')
DEFAULT_PITCH = int(config.get('TTS', 'default_pitch'))
# 학습 시간 초과 (초). 워커가 작업을 꺼낸 뒤 이 시간이 지나도 안 끝나면 실패로 응답한다 (워커가 죽고 다시 안 켜진 경우)
# 기본 10분: 10분 녹음 학습이 약 4분 10초, 재시도 1번까지 하면 약 8~9분 (Windows RTX 3060). 원래 값은 6시간이었다 (#11, #42)
MODEL_GENERATION_TIMEOUT_SECONDS = int(os.environ.get("MODEL_GENERATION_TIMEOUT", 600))
# TTS 결과를 기다리는 최대 시간 (초). 워커 시도 3번 × 약 15~20초에 여유를 둔 값 (#38)
TTS_WAIT_SECONDS = int(os.environ.get("TTS_WAIT_SECONDS", 90))

# 요청별 로깅 미들웨어
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f"요청 시작: {request.method} {request.url}")
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logging.info(f"요청 종료: {request.method} {request.url} - 처리 시간: {process_time:.4f}초")
    return response


@app.get(
    "/",
    tags=["상태"],
    summary="기본 응답",
    description="서버가 떠 있는지 가장 간단히 확인한다.",
)
def read_root():
    return {"message": "파일 업로드 및 관리 시스템 API"}

@app.post(
    "/user",
    tags=["사용자"],
    summary="사용자 생성",
    description="UUID를 발급하고 DB `users` 테이블에 저장한다. 로그인이 없어서 이 UUID가 사용자 신분증 역할을 한다. Model Server는 부르지 않는다.",
)
def create_user():
    user_uuid = generate_uuid()
    db_manager.save_user_metadata(user_uuid)
    saved_user = db_manager.get_user_by_uuid(user_uuid)
    
    if saved_user:
        logging.info(f"사용자 생성 성공: {user_uuid}")
        return {"uuid": user_uuid, "message": "사용자 생성 및 저장 성공"}
    else:
        logging.error(f"사용자 생성 실패: {user_uuid}")
        raise HTTPException(status_code=500, detail="사용자 정보 저장 오류")

@app.delete(
    "/user/{user_uuid}",
    tags=["사용자"],
    summary="사용자 삭제",
    description="Model Server의 `DELETE /user/{user_uuid}`로 녹음·모델 폴더를 지운 뒤 DB에서 사용자를 지운다.",
)
def delete_user(user_uuid: str):
    try:
        response = requests.delete(f"{MODEL_SERVER_API_URL}/user/{user_uuid}", timeout=10)
        response.raise_for_status()
        db_manager.delete_user_metadata(user_uuid)
        logging.info(f"사용자 삭제 성공: {user_uuid}")
        return {"message": "사용자 삭제 성공"}

    except requests.exceptions.RequestException as e:
        logging.error(f"사용자 삭제 中 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 삭제 中 오류 발생: {e}")

@app.post(
    "/user/{user_uuid}/upload",
    tags=["녹음 파일"],
    summary="녹음 업로드",
    description="확장자를 검사하고(m4a, ogg, wav만, 그 밖은 400) Model Server의 `POST /user/{user_uuid}/upload`로 그대로 전달한다. 파일은 Model Server 디스크에만 저장되고 DB에는 기록하지 않는다.",
)
async def upload_file(user_uuid: str, file: UploadFile = File(...)):
    if not is_allowed_file(file.filename, ALLOWED_EXTENSIONS):
        logging.warning(f"허용되지 않은 파일 형식: {file.filename}")
        raise HTTPException(status_code=400, detail="허용되지 않은 파일 형식")

    try:
        response = requests.post(
            f"{MODEL_SERVER_API_URL}/user/{user_uuid}/upload", 
            files={"file": (file.filename, file.file, "audio/ogg")} 
        )
        response.raise_for_status()
        logging.info(f"파일 업로드 성공: {file.filename}")
        return {"message": "파일 업로드 성공", "file_path": response.json()["file_path"]}

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 업로드 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 업로드 중 오류 발생: {e}")


@app.get(
    "/user/{user_uuid}/files",
    tags=["녹음 파일"],
    summary="업로드한 파일 목록",
    description="Model Server의 `GET /user/{user_uuid}/files` 결과를 그대로 돌려준다.",
)
def get_user_files(user_uuid: str):
    try:
        response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/files", timeout=10)
        response.raise_for_status()
        logging.info(f"파일 목록 조회 성공: {user_uuid}")
        return response.json()

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 목록 조회 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 중 오류 발생: {e}")


@app.delete(
    "/user/{user_uuid}/raw/{filename}",
    tags=["녹음 파일"],
    summary="업로드한 파일 삭제",
    description="Model Server의 `DELETE /user/{user_uuid}/raw/{filename}`을 부른다.",
)
async def delete_file(user_uuid: str, filename: str):
    try:
        response = requests.delete(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/raw/{filename}", timeout=10)
        response.raise_for_status()
        logging.info(f"파일 삭제 성공: {filename}")
        return {"message": "파일 삭제 성공"}

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 삭제 중 오류 발생: {e}")


@app.get(
    "/user/{user_uuid}/modelcheck",
    tags=["학습"],
    summary="학습 완료 확인",
    description="작업 정보(Redis `job:{id}`)의 상태로 답한다. success → \"모델 파일 존재\", fail → 500, 대기·진행 중(또는 학습 요청 없음) → \"모델 파일 없음\". 워커가 꺼낸 뒤 `MODEL_GENERATION_TIMEOUT`(기본 10분)이 지나도 안 끝나면 500 (#42).",
)
async def check_model(user_uuid: str):
    job = await find_train_job(redis_client, user_uuid)
    if job is None or job["status"] == "queued":
        return {"message": "모델 파일 없음"}
    if job["status"] == "success":
        logging.info(f"모델 생성 완료: {user_uuid}")
        return {"message": "모델 파일 존재"}
    if job["status"] == "fail":
        logging.error(f"모델 생성 실패: {user_uuid}: {job.get('error', '')}")
        raise HTTPException(status_code=500, detail="모델 생성 실패")

    # progress: 워커가 너무 오래 쥐고 있으면 (죽고 다시 안 켜짐) 실패로 응답한다. 작업 정보는 바꾸지 않는다
    elapsed_ms = await measure_working_ms(redis_client, job)
    if elapsed_ms is not None and elapsed_ms >= MODEL_GENERATION_TIMEOUT_SECONDS * 1000:
        logging.error(f"모델 생성 시간 초과: {user_uuid}: {elapsed_ms / 1000:.0f}초")
        raise HTTPException(status_code=500, detail="모델 생성 시간 초과")
    return {"message": "모델 파일 없음"}


@app.post(
    "/user/{user_uuid}/models",
    tags=["학습"],
    summary="학습 요청 (대기열에 추가)",
    description="Redis에 작업 정보(`job:{id}`, queued)를 만들고 `stream:train`에 넣는다. Windows의 학습 워커가 꺼내 학습한다. 같은 사용자의 학습이 대기·진행 중이면 다시 넣지 않는다 (#42).",
)
async def create_user_model(user_uuid: str):
    job_id = await enqueue_train_job(redis_client, user_uuid)
    if job_id is None:
        logging.warning(f"모델 생성 중이거나 대기열에 있음: {user_uuid}")
        return {"message": "이미 모델 생성 요청이 진행 중이거나 대기열에 있습니다."}

    logging.info(f"모델 생성 요청이 대기열에 추가됨: {user_uuid} (작업 {job_id})")
    return {"message": "모델 생성 요청이 대기열에 추가되었습니다.", "model_id": user_uuid}


@app.post(
    "/user/{user_uuid}/tts",
    tags=["TTS"],
    summary="TTS (텍스트 → 내 목소리)",
    description="Redis에 TTS 작업(`job:{id}`)을 넣고 `stream:tts`에 번호를 넣는다. Windows의 TTS 워커가 끝 신호(`job:{id}:done`)를 줄 때까지 `BLPOP`으로 기다렸다가(최대 `TTS_WAIT_SECONDS`, 기본 90초) 결과 음성(`job:{id}:result`)을 내려준다. 빈 문장·학습이 끝나지 않은 사용자는 400, 워커 실패는 500, 시간 초과는 504. pitch를 안 보내면 학습 때 잰 자동 피치, 그것도 없으면 `config.ini`의 기본값(3) (워커가 고른다, #59).",
)
async def synthesize_tts(user_uuid: str, tts_text: str = Form(...), pitch: Optional[int] = Form(None)):
    # 입구 검사: 다시 해도 같은 요청은 큐에 넣지 않는다
    if not tts_text.strip():
        raise HTTPException(status_code=400, detail="문장이 비어 있습니다.")
    train_job = await find_train_job(redis_client, user_uuid)
    if train_job is None or train_job["status"] != "success":
        raise HTTPException(status_code=400, detail="학습이 끝난 모델이 없습니다.")

    job_id = await enqueue_tts_job(redis_client, user_uuid, tts_text, pitch, DEFAULT_PITCH)
    status, audio = await wait_for_tts_result(redis_binary_client, job_id, TTS_WAIT_SECONDS)

    # 실패면 결과를 받으러 가지 않는다 (예전에는 이전 문장의 음성이 나갔다, #38)
    if status == "timeout":
        logging.error(f"TTS 시간 초과: {user_uuid} (작업 {job_id})")
        raise HTTPException(status_code=504, detail="TTS 시간 초과")
    if status != "success" or audio is None:
        error = await redis_client.hget(f"job:{job_id}", "error")
        logging.error(f"TTS 실패: {user_uuid} (작업 {job_id}): {error}")
        raise HTTPException(status_code=500, detail=f"TTS 실패: {error}")

    logging.info(f"TTS 생성 성공: {user_uuid} (작업 {job_id})")
    return Response(content=audio, media_type="audio/wav", headers={"Content-Disposition": f"attachment; filename={user_uuid}.wav"})


# 대기열 상태 조회 엔드포인트
@app.get(
    "/queue_status",
    tags=["학습"],
    summary="전체 대기열 크기",
    description="학습 작업 중 대기(`queue_size`)와 진행(`active_tasks`) 수 (Redis 기준, #42).",
)
async def get_queue_status():
    counts = await count_train_jobs_by_status(redis_client)
    logging.info(f"대기열 크기: {counts['queued']}, 진행 중: {counts['progress']}")
    return {"queue_size": counts["queued"], "active_tasks": counts["progress"]}

# 사용자 대기열 정보 조회 엔드포인트
@app.get(
    "/user/{user_uuid}/queue",
    tags=["학습"],
    summary="내 대기열 위치",
    description="학습이 대기·진행 중이면 위치를 돌려준다: 내 앞에 끝나지 않은 작업 수 + 1 (진행 중이면 1). 앱은 1을 \"생성 중\", 2 이상을 \"대기 순번 (위치 - 1)번\"으로 보여 준다. 끝났거나 요청이 없으면 \"대기열에 추가되지 않았습니다\" (#42).",
)
async def get_user_queue_info(user_uuid: str):
    job = await find_train_job(redis_client, user_uuid)
    if job is None or job["status"] not in ("queued", "progress"):
        return {"status": "대기열에 추가되지 않았습니다."}

    position = await count_jobs_ahead(redis_client, job) + 1
    logging.info(f"사용자 {user_uuid}는 대기열에 있습니다. 위치: {position}")
    return {"status": "대기열에 있습니다.", "position": position}

# 서버 온라인 상태 확인 엔드포인트
@app.get(
    "/online",
    tags=["상태"],
    summary="서버 상태 확인 (Model Server 포함)",
    description="Model Server의 `GET /online`까지 불러서 `model_server`에 연결 여부를 돌려준다.",
)
async def check_online():
    logging.info("서버 온라인 상태 확인 요청")
    try:
        # 모델 서버 확인
        response = requests.get(f"{MODEL_SERVER_API_URL}/online", timeout=10)
        response.raise_for_status()  # 오류 발생 시 예외 발생
        logging.info("모델 서버 온라인 상태 확인 성공")
        return {"status": "online", "model_server": True}

    except requests.exceptions.RequestException as e:
        logging.error(f"모델 서버 연결 오류: {e}")
        return {"status": "online", "model_server": False}
        # 모델 서버 연결 오류인 경우 모델 서버 상태를 False로 반환

if __name__ == "__main__":
    import uvicorn
    logging.info("서버 시작")
    uvicorn.run(app, host="0.0.0.0", port=28300)
