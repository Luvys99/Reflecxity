import logging
import os
import configparser
from typing import List, Optional
import time
import hmac
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

from db_manager import DBManager
from utils import is_allowed_file, generate_uuid
from train_queue import (
    connect_redis, create_group_if_missing, enqueue_train_job, find_train_job,
    count_jobs_ahead, measure_working_ms, count_train_jobs_by_status,
)
from tts_queue import enqueue_tts_job, wait_for_tts_result
from translation_limit import reserve_translation_chars, release_translation_chars
from rate_limit import client_ip, count_request

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

# 앱 전용 문구 (#103). 있으면 헤더 X-App-Key가 같은 요청만 받는다. 없으면(개발) 검사하지 않는다
# 앱(APK)을 풀면 보이는 값이라 자물쇠가 아니라 주소를 찔러 보는 봇을 막는 용도다
APP_KEY = os.environ.get("APP_KEY")
app_key_header = APIKeyHeader(name="X-App-Key", auto_error=False)


def check_app_key(app_key: Optional[str] = Depends(app_key_header)):
    if APP_KEY and not (app_key and hmac.compare_digest(app_key, APP_KEY)):
        raise HTTPException(status_code=401, detail="앱 키가 없거나 다릅니다.")


# 공개할 때는 API 목록(Swagger, OpenAPI)을 끈다 (#103). 기본은 켜짐 (개발)
DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "true").lower() != "false"

# Swagger(/docs)에서 Execute 결과 아래에 걸린 시간을 표시한다 (#15)
app = FastAPI(
    swagger_ui_parameters={"displayRequestDuration": True},
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
    dependencies=[Depends(check_app_key)],
)

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
# Google 번역 키. 앱(APK)에 넣으면 누구나 꺼내 쓸 수 있어서 서버에만 둔다 (#102). 없으면 번역 요청에 503
GOOGLE_TRANSLATE_API_KEY = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
# 번역 하루 글자 수 상한. 넘으면 429 (#105). 문장 하나가 20~50자라 기본 2만 자면 하루 수백 문장
TRANSLATE_DAILY_CHAR_LIMIT = int(os.environ.get("TRANSLATE_DAILY_CHAR_LIMIT", 20000))

# 요청 수 제한 (#103): 기능 → (횟수, 구간 초). 정상 사용보다 넉넉하게, 반복 낭비는 막게. .env로 횟수를 바꾼다
RATE_LIMITS = {
    "create_user": (int(os.environ.get("RATE_LIMIT_CREATE_USER_PER_HOUR", 5)), 3600),  # IP별. 정상은 1번
    "upload": (int(os.environ.get("RATE_LIMIT_UPLOAD_PER_HOUR", 30)), 3600),  # 사용자별. 정상은 녹음 몇 개
    "training": (int(os.environ.get("RATE_LIMIT_TRAINING_PER_HOUR", 3)), 3600),  # IP별. 한 번에 GPU 몇 분
    "tts": (int(os.environ.get("RATE_LIMIT_TTS_PER_MINUTE", 10)), 60),  # 사용자별. 한 번에 GPU 약 3초
    "translation": (int(os.environ.get("RATE_LIMIT_TRANSLATION_PER_MINUTE", 30)), 60),  # IP별
}


def rate_limit(name, by_user=False):
    """기능별 요청 수 제한. by_user면 주소의 user_uuid, 아니면 IP로 센다. 넘으면 429 + Retry-After"""
    async def check(request: Request):
        limit, window_seconds = RATE_LIMITS[name]
        who = request.path_params["user_uuid"] if by_user else client_ip(request)
        retry_after = await count_request(redis_client, name, who, limit, window_seconds)
        if retry_after is not None:
            logging.warning(f"요청 수 제한: {name} {who}")
            raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요.", headers={"Retry-After": str(retry_after)})
    return Depends(check)

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
    "/users",
    tags=["사용자"],
    summary="사용자 생성",
    description="UUID를 발급하고 DB `users` 테이블에 저장한다. 로그인이 없어서 이 UUID가 사용자 신분증 역할을 한다. Model Server는 부르지 않는다.",
    dependencies=[rate_limit("create_user")],
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
    "/users/{user_uuid}",
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
        logging.error(f"사용자 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 삭제 중 오류 발생: {e}")

@app.post(
    "/users/{user_uuid}/recordings",
    tags=["녹음 파일"],
    summary="녹음 업로드",
    description="확장자를 검사하고(m4a, ogg, wav만, 그 밖은 400) Model Server의 `POST /user/{user_uuid}/upload`로 그대로 전달한다. 파일은 Model Server 디스크에만 저장되고 DB에는 기록하지 않는다.",
    dependencies=[rate_limit("upload", by_user=True)],
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
    "/users/{user_uuid}/recordings",
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
    "/users/{user_uuid}/recordings/{filename}",
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


async def read_training_status(user_uuid):
    """사용자의 학습 상태 하나로 답한다 (#63). 앱은 문장 대신 status 값을 보고 판단한다"""
    job = await find_train_job(redis_client, user_uuid)
    if job is None:
        return {"status": "none"}
    if job["status"] == "success":
        return {"status": "success"}
    if job["status"] == "fail":
        logging.error(f"모델 생성 실패: {user_uuid}: {job.get('error', '')}")
        return {"status": "fail", "error": "모델 생성 실패"}

    # 대기·진행 중: 내 앞에 끝나지 않은 작업 수 + 1 (진행 중이면 1)
    position = await count_jobs_ahead(redis_client, job) + 1
    if job["status"] == "queued":
        return {"status": "queued", "position": position}

    # progress: 워커가 너무 오래 쥐고 있으면 (죽고 다시 안 켜짐) 실패로 응답한다. 작업 정보는 바꾸지 않는다
    elapsed_ms = await measure_working_ms(redis_client, job)
    if elapsed_ms is not None and elapsed_ms >= MODEL_GENERATION_TIMEOUT_SECONDS * 1000:
        logging.error(f"모델 생성 시간 초과: {user_uuid}: {elapsed_ms / 1000:.0f}초")
        return {"status": "fail", "error": "모델 생성 시간 초과"}
    response = {"status": "progress", "position": position}
    # 학습을 시작한 지 지난 시간: 앱이 남은 시간을 보여 준다 (#89)
    if elapsed_ms is not None:
        response["elapsed_seconds"] = elapsed_ms // 1000
    return response


@app.post(
    "/users/{user_uuid}/training",
    tags=["학습"],
    summary="학습 요청 (대기열에 추가)",
    description="Redis에 작업 정보(`job:{id}`, queued)를 만들고 `stream:train`에 넣는다. Windows의 학습 워커가 꺼내 학습한다. 같은 사용자의 학습이 대기·진행 중이면 다시 넣지 않는다 (#42). 어느 쪽이든 `GET /users/{user_uuid}/training`과 같은 모양으로 지금 상태를 돌려준다 (#63).",
    dependencies=[rate_limit("training")],
)
async def request_training(user_uuid: str):
    job_id = await enqueue_train_job(redis_client, user_uuid)
    if job_id is None:
        logging.warning(f"모델 생성 중이거나 대기열에 있음: {user_uuid}")
    else:
        logging.info(f"모델 생성 요청이 대기열에 추가됨: {user_uuid} (작업 {job_id})")
    return await read_training_status(user_uuid)


@app.get(
    "/users/{user_uuid}/training",
    tags=["학습"],
    summary="학습 상태",
    description="""작업 정보(Redis `job:{id}`)로 학습 상태를 답한다 (#63).
- `none`: 학습 요청이 없음
- `queued`: 대기 중. `position`은 내 앞에 끝나지 않은 작업 수 + 1. 앱은 "대기 순번 (position - 1)번"으로 보여 준다
- `progress`: 학습 중. `position`은 1, `elapsed_seconds`는 워커가 학습을 시작한 뒤 지난 초 (#89)
- `success`: 학습 끝
- `fail`: 학습 실패. 워커가 꺼낸 뒤 `MODEL_GENERATION_TIMEOUT`(기본 10분)이 지나도 안 끝나도 실패로 본다 (#42). 이유는 `error`""",
)
async def get_training_status(user_uuid: str):
    return await read_training_status(user_uuid)


@app.post(
    "/users/{user_uuid}/tts",
    tags=["TTS"],
    summary="TTS (텍스트 → 내 목소리)",
    description="Redis에 TTS 작업(`job:{id}`)을 넣고 `stream:tts`에 번호를 넣는다. Windows의 TTS 워커가 끝 신호(`job:{id}:done`)를 줄 때까지 `BLPOP`으로 기다렸다가(최대 `TTS_WAIT_SECONDS`, 기본 90초) 결과 음성(`job:{id}:result`)을 내려준다. 빈 문장·학습이 끝나지 않은 사용자는 400, 워커 실패는 500, 시간 초과는 504. pitch를 안 보내면 학습 때 잰 자동 피치, 그것도 없으면 `config.ini`의 기본값(3) (워커가 고른다, #59).",
    dependencies=[rate_limit("tts", by_user=True)],
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


class TranslationRequest(BaseModel):
    text: str
    target: str  # 번역할 언어 코드 (en, ko)


@app.post(
    "/translations",
    tags=["번역"],
    summary="번역 (Google 번역을 대신 호출)",
    description="앱 대신 Google 번역 v2를 부른다. 키는 서버 `.env`의 `GOOGLE_TRANSLATE_API_KEY`에만 있다 (#102). 하루 글자 수 상한(`TRANSLATE_DAILY_CHAR_LIMIT`, 기본 2만 자)을 넘으면 Google을 부르지 않고 429 (#105). 빈 문장 400, 키 없음 503, Google 실패 502.",
    dependencies=[rate_limit("translation")],
)
async def translate(request: TranslationRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="문장이 비어 있습니다.")
    if not GOOGLE_TRANSLATE_API_KEY:
        raise HTTPException(status_code=503, detail="번역 키가 설정되지 않았습니다.")

    chars = len(request.text)
    if not await reserve_translation_chars(redis_client, chars, TRANSLATE_DAILY_CHAR_LIMIT):
        logging.warning(f"번역 하루 상한 초과: {chars}자 요청 거절")
        raise HTTPException(status_code=429, detail="오늘 번역할 수 있는 양을 다 썼습니다.")

    try:
        # 키는 주소(?key=)가 아니라 헤더로 보낸다: 에러 메시지·로그에 주소가 찍혀도 키가 남지 않는다
        # requests는 기다리는 동안 서버 전체를 멈추므로 다른 스레드에서 부른다
        response = await run_in_threadpool(
            requests.post,
            GOOGLE_TRANSLATE_URL,
            headers={"X-Goog-Api-Key": GOOGLE_TRANSLATE_API_KEY},
            json={"q": request.text, "target": request.target, "format": "text"},
            timeout=10,
        )
        response.raise_for_status()
        translated_text = response.json()["data"]["translations"][0]["translatedText"]
    except (requests.exceptions.RequestException, KeyError, IndexError, ValueError) as e:
        logging.error(f"번역 실패: {type(e).__name__}")
        await release_translation_chars(redis_client, chars)  # 번역 못 했으니 센 글자를 되돌린다
        raise HTTPException(status_code=502, detail="번역 서버 응답 오류")

    return {"translated_text": translated_text}


# 대기열 상태 조회 엔드포인트
@app.get(
    "/training-queue",
    tags=["학습"],
    summary="전체 대기열 크기",
    description="학습 작업 중 대기(`queued`)와 진행(`progress`) 수 (Redis 기준, #42).",
)
async def get_queue_status():
    counts = await count_train_jobs_by_status(redis_client)
    logging.info(f"대기열 크기: {counts['queued']}, 진행 중: {counts['progress']}")
    return {"queued": counts["queued"], "progress": counts["progress"]}

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
