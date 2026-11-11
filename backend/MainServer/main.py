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

from file_manager import FileHandler
from db_manager import DBManager
from utils import allowed_file, generate_uuid

# 로그 설정: 시간과 함께 출력
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 설정 파일 불러오기
config = configparser.ConfigParser()
config.read('config.ini')

# 설정 파일에서 DB 정보 가져오기
DB_CONFIG = {
    "host": config.get('DATABASE', 'host'),
    "user": config.get('DATABASE', 'user'),
    "password": config.get('DATABASE', 'password'),
    "database": config.get('DATABASE', 'database'),
}

ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg", "zip", "ogg", "m4a"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
CHUNK_SIZE = 1024 * 1024  # 1MB

BASE_DIR = os.getcwd()
config['FILE_PATH'] = {'base_dir': BASE_DIR}

model_queue = asyncio.Queue()
model_tasks = {}
model_queue_positions = []

db_manager = DBManager(DB_CONFIG)
db_manager.create_table()

app = FastAPI()
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
MODEL_GENERATION_TIMEOUT = 21600
CHECK_INTERVAL = 60

# 요청별 로깅 미들웨어
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f"요청 시작: {request.method} {request.url}")
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logging.info(f"요청 종료: {request.method} {request.url} - 처리 시간: {process_time:.4f}초")
    return response


@app.get("/")
def read_root():
    return {"message": "파일 업로드 및 관리 시스템 API"}

@app.post("/user")
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

@app.delete("/user/{user_uuid}")
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

@app.post("/user/{user_uuid}/upload")
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


@app.get("/user/{user_uuid}/files")
def get_user_files(user_uuid: str):
    try:
        response = requests.get(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/files", timeout=10)
        response.raise_for_status()
        logging.info(f"파일 목록 조회 성공: {user_uuid}")
        return response.json()

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 목록 조회 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 중 오류 발생: {e}")


@app.delete("/user/{user_uuid}/raw/{filename}")
async def delete_file(user_uuid: str, filename: str):
    try:
        response = requests.delete(f"{MODEL_SERVER_API_URL}/user/{user_uuid}/raw/{filename}", timeout=10)
        response.raise_for_status()
        logging.info(f"파일 삭제 성공: {filename}")
        return {"message": "파일 삭제 성공"}

    except requests.exceptions.RequestException as e:
        logging.error(f"파일 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"파일 삭제 중 오류 발생: {e}")


@app.get("/user/{user_uuid}/modelcheck")
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


@app.get("/user/{user_uuid}/raw/{filename}")
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


@app.post("/user/{user_uuid}/models") 
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

        if 'queue_processor' not in model_tasks:
            model_tasks['queue_processor'] = asyncio.create_task(process_model_queue())

        return {"message": "모델 생성 요청이 대기열에 추가되었습니다.", "model_id": user_uuid}

    except requests.exceptions.RequestException as e:
        logging.error(f"모델 생성 요청 中 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"모델 생성 요청 中 오류 발생: {e}")


# TTS 요청 처리 함수 수정 (파일 다운로드 추가)
@app.post("/user/{user_uuid}/tts")
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
                    logging.error(f"모델 생성 시간 초과: {user_uuid}")
                    model_queue.task_done()
                    del model_tasks[user_uuid]
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

        except requests.exceptions.RequestException as e:
            logging.error(f"모델 생성 요청 중 오류 발생: {e}")
            raise

        except TimeoutError as e:
            logging.error(f"모델 생성 시간 초과: {e}")
            raise

        except Exception as e:
            logging.error(f"모델 생성 중 오류 발생: {e}")
            raise

        finally:
            model_queue.task_done()
            logging.info(f"큐 작업 완료: {user_uuid}")
            if user_uuid in model_queue_positions:
                model_queue_positions.remove(user_uuid)
                logging.info(f"대기열 위치 삭제: {user_uuid}")

# 대기열 상태 조회 엔드포인트
@app.get("/queue_status")
async def queue_status():
    logging.info("대기열 상태 조회 요청")
    queue_size = model_queue.qsize()
    active_tasks = len(model_tasks)
    logging.info(f"대기열 크기: {queue_size}, 활성 작업 수: {active_tasks}")
    return {"queue_size": queue_size, "active_tasks": active_tasks}

# 사용자 대기열 정보 조회 엔드포인트
@app.get("/user/{user_uuid}/queue")
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
@app.get("/online")
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
