# TTS 워커: stream:tts에서 작업을 꺼내 문장을 내 목소리 음성으로 만들고, 결과를 job:{job_id}에 기록한다 (#17)
# 실행: env\python.exe tts_worker.py (Model Server, 학습 워커와 별개 프로세스)
# 꺼내기·기록·재시도는 job_worker.py, 여기는 TTS 한 건을 하는 부분만
import os

# main.py와 같은 이유 (Mac에서 RVC 변환이 멈추는 문제). torch를 import하기 전에 설정해야 한다
os.environ.setdefault("OMP_NUM_THREADS", "1")

import uuid

from dotenv import load_dotenv

from job_worker import JobFailed, JobWorker, connect_redis
from tts import convert_text_to_voice, find_model_files

# TTS 코드가 user/, logs/, rvc_cli.py를 이 폴더 기준으로 찾는다
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

TTS_STREAM = "stream:tts"
TTS_WORKER_GROUP = "tts-workers"
MAX_ATTEMPTS = 3  # 처음 1번 + 재시도 2번 (edge-tts가 가끔 일시적으로 실패한다, #17 댓글)


def run_tts_job(job):
    user_uuid = job["user"]

    # 문장·pitch가 없거나 모델이 없으면 다시 해도 같으니 바로 실패
    # pitch 기본값은 Main 설정에 있어서 Main이 작업을 넣을 때 채운다
    if not job.get("text"):
        raise JobFailed("문장 없음")
    if "pitch" not in job:
        raise JobFailed("pitch 없음")
    try:
        pth_path, index_path = find_model_files(user_uuid)
    except FileNotFoundError:
        raise JobFailed("모델 파일 없음")

    # 결과는 작업마다 다른 임시 파일에 만들고, 읽어서 돌려준 뒤 지운다 (JobWorker가 Redis에 담는다, #36)
    # 결과 파일이 없으면(edge-tts 일시 실패 등) convert_text_to_voice가 RuntimeError를 던진다 → 재시도 대상
    os.makedirs("temptts", exist_ok=True)
    output_path = os.path.join("temptts", f"{user_uuid}_{uuid.uuid4().hex}.wav")
    try:
        convert_text_to_voice(user_uuid, job["text"], job["pitch"], pth_path, index_path, output_path)
        with open(output_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def create_tts_worker(redis_client):
    return JobWorker(redis_client, TTS_STREAM, TTS_WORKER_GROUP, MAX_ATTEMPTS, run_tts_job)


if __name__ == "__main__":
    create_tts_worker(connect_redis()).run_forever()
