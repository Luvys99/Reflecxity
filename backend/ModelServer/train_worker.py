# 학습 워커: stream:train에서 작업을 꺼내 학습하고, 결과를 job:{job_id}에 기록한다 (#17)
# 실행: env\python.exe train_worker.py (Model Server와 별개 프로세스)
# 꺼내기·기록·재시도는 job_worker.py, 여기는 학습 한 건을 하는 부분만
import os

# main.py와 같은 이유 (Mac에서 RVC 변환이 멈추는 문제). torch를 import하기 전에 설정해야 한다
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio

from dotenv import load_dotenv
from fastapi import HTTPException

from job_worker import JobFailed, JobWorker, connect_redis
from training import create_model_async, prepare_training, DEFAULT_SAMPLE_RATE, DEFAULT_CPU_CORES

# 학습 코드가 user/, logs/, rvc_cli.py를 이 폴더 기준으로 찾는다
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

TRAIN_STREAM = "stream:train"
TRAIN_WORKER_GROUP = "train-workers"
MAX_ATTEMPTS = 2  # 처음 1번 + 재시도 1번 (학습은 비싸서 1번만)


def run_train_job(job):
    user_uuid = job["user"]

    # 녹음이 없으면 다시 해도 같으니 바로 실패
    try:
        dataset_path, voice_file_names = prepare_training(user_uuid)
    except FileNotFoundError:
        raise JobFailed("녹음 폴더 없음")
    if not voice_file_names:
        raise JobFailed("녹음 파일 없음")

    try:
        asyncio.run(create_model_async(user_uuid, dataset_path, DEFAULT_SAMPLE_RATE, DEFAULT_CPU_CORES, voice_file_names))
    except HTTPException as e:
        # 녹음이 짧아 조각이 10개 이하: 다시 해도 같으니 바로 실패
        raise JobFailed(e.detail)


def create_train_worker(redis_client):
    return JobWorker(redis_client, TRAIN_STREAM, TRAIN_WORKER_GROUP, MAX_ATTEMPTS, run_train_job)


if __name__ == "__main__":
    create_train_worker(connect_redis()).run_forever()
