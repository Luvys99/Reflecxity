import logging
import os
import configparser
from typing import List
import asyncio
import time
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import io
from dotenv import load_dotenv

from file_manager import FileHandler
from db_manager import DBManager
from utils import allowed_file, generate_uuid

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

# Model Server 주소 (FileHandler도 config에서 읽으므로 config 값을 덮어쓴다)
config['MODEL_SERVER']['api_url'] = get_setting('MODEL_SERVER_URL', 'MODEL_SERVER', 'api_url')

ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg", "zip", "ogg", "m4a"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
CHUNK_SIZE = 1024 * 1024  # 1MB

BASE_DIR = os.getcwd()
config['FILE_PATH'] = {'base_dir': BASE_DIR}

# 대기열은 서버의 이벤트 루프 안에서 만든다 (아래 startup). Python 3.9에서는 asyncio.Queue가
# 만들어질 때의 루프에 묶여서, 서버 시작 전에 만들면 대기열이 빈 뒤 get()에서 RuntimeError가 나고
# 대기열 처리 작업이 죽는다 (#11)
model_queue = None
model_tasks = {}
model_queue_positions = []

db_manager = DBManager(DB_CONFIG)
db_manager.create_table()

app = FastAPI()

@app.on_event("startup")
async def create_model_queue():
    global model_queue
    model_queue = asyncio.Queue()
file_handler = FileHandler(DB_CONFIG, ALLOWED_EXTENSIONS, config)

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
# 학습 시간 초과와 확인 간격 (초). 측정할 때는 .env로 짧게 바꾼다
# 기본 30분: 10분 녹음 학습이 약 4분 20초 (Windows RTX 3060, 2026-11-14 측정). 원래 값은 6시간이었다 (#11)
MODEL_GENERATION_TIMEOUT = int(os.environ.get("MODEL_GENERATION_TIMEOUT", 1800))
CHECK_INTERVAL = int(os.environ.get("MODEL_CHECK_INTERVAL", 60))

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

# TTS 상태 확인 함수 추가
async def check_tts_status(user_uuid: str):
    try:
        response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/status")
        response.raise_for_status()
        status = response.json()
        return status["tts"]
    except requests.exceptions.RequestException as e:
        logging.error(f"TTS 상태 확인 중 오류 발생: {e}")
        return "error"

@app.post(
    "/user/{user_uuid}/upload",
    tags=["녹음 파일"],
    summary="녹음 업로드",
    description="확장자를 검사하고(ogg, m4a 등) Model Server의 `POST /user/{user_uuid}/upload`로 그대로 전달한다. 파일은 Model Server 디스크에만 저장되고 DB에는 기록하지 않는다.",
)
async def upload_file(user_uuid: str, file: UploadFile = File(...)):
    if not allowed_file(file.filename, ALLOWED_EXTENSIONS):
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
    description="Model Server의 `GET /user/{user_uuid}/modelcheck`를 부른다. \"모델 파일 존재\"면 완료, \"모델 생성 실패\"면 500, 그 외(\"모델 파일 없음\")는 아직 안 끝났거나 실패를 모르는 상태다 (#11).",
)
async def model_check(user_uuid: str):
    try:
        check_response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/modelcheck", timeout=10)
        if check_response.status_code == 200:
            message = check_response.json()["message"]
            if message == "모델 파일 존재":
                logging.info(f"모델 생성 완료: {user_uuid}")
                return check_response.json()
            elif message == "모델 생성 실패":
                logging.error(f"모델 생성 실패: {user_uuid}")
                raise HTTPException(status_code=500, detail="모델 생성 실패")
            else:
                return check_response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"모델 파일 확인 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"모델 파일 확인 중 오류 발생: {e}")


@app.get(
    "/user/{user_uuid}/raw/{filename}",
    tags=["녹음 파일"],
    summary="파일 받기",
    description="Model Server의 `GET /user/{user_uuid}/raw/{filename}`로 파일을 받아 그대로 내려준다. TTS 결과는 `convert.wav`.",
)
async def download_file(user_uuid: str, filename: str):
    try:
        response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/raw/{filename}", timeout=10)
        response.raise_for_status()
        wav_data = response.content
        wav_file = io.BytesIO(wav_data)

        logging.info(f"파일 다운로드 성공: {filename}")
        return StreamingResponse(
            wav_file, 
            media_type="audio/wav",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 다운로드 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 다운로드 중 오류 발생: {e}")


@app.post(
    "/user/{user_uuid}/models",
    tags=["학습"],
    summary="학습 요청 (대기열에 추가)",
    description="학습을 바로 하지 않고 Main의 대기열(메모리)에 넣는다. 대기열 처리 작업이 한 명씩 꺼내 Model Server의 `POST /models`로 보내고, 끝날 때까지 `modelcheck`로 확인한다. 같은 사용자가 이미 대기 중이면 다시 넣지 않는다.",
)
 
async def create_user_model(
    user_uuid: str,
    sample_rate: str = Form("40000"), 
    cpu_cores: int = Form(4), 
):
    try:
        if user_uuid in [p[0] for p in model_tasks] or user_uuid in model_queue_positions:
            logging.warning(f"모델 생성 중이거나 대기열에 있음: {user_uuid}")
            return {"message": "이미 모델 생성 요청이 진행 중이거나 대기열에 있습니다."}
        
        await model_queue.put((user_uuid, sample_rate, cpu_cores))
        model_queue_positions.append(user_uuid)
        logging.info(f"모델 생성 요청이 대기열에 추가됨: {user_uuid}")

        # 처리 작업이 없거나 (예상 못 한 에러로) 끝나 있으면 다시 시작한다
        if 'queue_processor' not in model_tasks or model_tasks['queue_processor'].done():
            model_tasks['queue_processor'] = asyncio.create_task(process_model_queue())

        return {"message": "모델 생성 요청이 대기열에 추가되었습니다.", "model_id": user_uuid}

    except requests.exceptions.RequestException as e:
        logging.error(f"모델 생성 요청 中 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"모델 생성 요청 中 오류 발생: {e}")


# TTS 요청 처리 함수 수정 (파일 다운로드 추가)
@app.post(
    "/user/{user_uuid}/tts",
    tags=["TTS"],
    summary="TTS (텍스트 → 내 목소리)",
    description="Model Server의 `POST /tts`로 요청하고, `GET /user/{user_uuid}/status`가 `progress`인 동안 0.3초마다 확인한 뒤 `convert.wav`를 받아 바로 내려준다. pitch를 안 보내면 `config.ini`의 기본값(3).",
)
async def synthesize_tts(user_uuid: str, tts_text: str = Form(...), pitch: int = Form(DEFAULT_PITCH)):
    try:
        tts_data = {
            "user_uuid": user_uuid,
            "tts_text": tts_text,
            "pitch" : pitch
        }

        response = requests.post(f"{MODEL_SERVER_API_URL}/tts", json=tts_data, timeout=60)
        response.raise_for_status()

        # 모델 서버에서 TTS 상태 확인 (await 사용)
        print(f"테스트 확인 {await check_tts_status(user_uuid)}") 
        while await check_tts_status(user_uuid) == "progress":  # await 사용
            logging.info(f"TTS 진행중 ({user_uuid})...")
            await asyncio.sleep(0.3)  # 1초 대기

        # TTS 결과 파일 다운로드 
        response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/raw/convert.wav")
        response.raise_for_status()

        m4a_data = response.content
        m4a_file = io.BytesIO(m4a_data)

        logging.info(f"TTS 생성 성공: {user_uuid}")
        return StreamingResponse(m4a_file, media_type="audio/wav", headers={"Content-Disposition": f"attachment; filename={user_uuid}.wav"})

    except requests.exceptions.RequestException as e:
        logging.error(f"TTS 요청 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"TTS 요청 중 오류 발생: {e}")


# 모델 대기열 처리 함수
async def process_model_queue():
    logging.info("대기열 처리 작업 시작")
    logging.info(f"현재 대기열: {model_queue_positions}")

    while True:
        user_uuid, sample_rate, cpu_cores = await model_queue.get()

        logging.info(f"큐에서 작업 가져오기: {user_uuid}")
        logging.info(f"현재 대기열: {model_queue_positions}")
        logging.info(f"현재 작업: {model_tasks}")

        try:
            logging.info(f"모델 생성 요청 전달: {user_uuid}")
            response = requests.post(
                f"{MODEL_SERVER_API_URL}/models",
                json={"user_uuid": user_uuid, "sample_rate": sample_rate, "cpu_cores": cpu_cores},
                timeout=MODEL_GENERATION_TIMEOUT
            )

            response.raise_for_status()
            logging.info(f"모델 생성 요청 전달 완료: {user_uuid}")

            start_time = time.time()
            while True:
                elapsed_time = time.time() - start_time
                if elapsed_time >= MODEL_GENERATION_TIMEOUT:
                    # task_done()과 대기열 정리는 finally가 한다
                    raise TimeoutError(f"모델 생성 시간 초과: {user_uuid}")

                check_response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/modelcheck", timeout=CHECK_INTERVAL)
                if check_response.status_code == 200:
                    message = check_response.json()["message"]
                    if message == "모델 파일 존재":
                        logging.info(f"모델 생성 완료: {user_uuid}")
                        break
                    elif message == "모델 생성 실패":
                        logging.error(f"모델 생성 실패: {user_uuid}")
                        break

                logging.info(f"모델 생성 상태 확인 대기: {user_uuid}")
                await asyncio.sleep(CHECK_INTERVAL)
                logging.info(f"모델 생성 상태 확인 다시 시도: {user_uuid}")

        # 한 사용자의 실패로 대기열 처리 작업이 끝나지 않도록, 로그만 남기고 다음 사용자로 넘어간다 (#11)
        except requests.exceptions.RequestException as e:
            logging.error(f"모델 생성 요청 중 오류 발생: {user_uuid}: {e}")

        except TimeoutError as e:
            logging.error(f"모델 생성 시간 초과: {e}")

        except Exception as e:
            logging.error(f"모델 생성 중 오류 발생: {user_uuid}: {type(e).__name__}: {e}")

        finally:
            model_queue.task_done()
            logging.info(f"큐 작업 완료: {user_uuid}")
            if user_uuid in model_queue_positions:
                model_queue_positions.remove(user_uuid)
                logging.info(f"대기열 위치 삭제: {user_uuid}")

# 대기열 상태 조회 엔드포인트
@app.get(
    "/queue_status",
    tags=["학습"],
    summary="전체 대기열 크기",
    description="대기열에 남은 요청 수(`queue_size`)와 `model_tasks` 항목 수(`active_tasks`)를 돌려준다.",
)
async def queue_status():
    logging.info("대기열 상태 조회 요청")
    queue_size = model_queue.qsize()
    active_tasks = len(model_tasks)
    logging.info(f"대기열 크기: {queue_size}, 활성 작업 수: {active_tasks}")
    return {"queue_size": queue_size, "active_tasks": active_tasks}

# 사용자 대기열 정보 조회 엔드포인트
@app.get(
    "/user/{user_uuid}/queue",
    tags=["학습"],
    summary="내 대기열 위치",
    description="대기 중이면 위치를 돌려준다. 학습이 시작돼 대기열에서 빠지면 \"대기열에 추가되지 않았습니다\"가 나온다 (대기 / 학습 중 / 완료 / 실패를 구분하지 못함).",
)
async def get_user_queue_info(user_uuid: str):
    logging.info(f"사용자 {user_uuid} 대기열 상태 조회 요청")
    if user_uuid in [p[0] for p in model_tasks]:
        logging.info(f"사용자 {user_uuid}는 모델 생성 중")
        return {"status": "모델 생성 중"}
    elif user_uuid in model_queue_positions:
        position = model_queue_positions.index(user_uuid) + 1
        logging.info(f"사용자 {user_uuid}는 대기열에 있습니다. 위치: {position}")
        return {"status": "대기열에 있습니다.", "position": position}
    else:
        logging.info(f"사용자 {user_uuid}는 대기열에 추가되지 않았습니다.")
        return {"status": "대기열에 추가되지 않았습니다."}

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
