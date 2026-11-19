# 학습 워커: stream:train에서 작업을 꺼내 학습하고, 결과를 job:{job_id}에 기록한다 (#17)
# 실행: env\python.exe train_worker.py (Model Server와 별개 프로세스)
import os

# main.py와 같은 이유 (Mac에서 RVC 변환이 멈추는 문제). torch를 import하기 전에 설정해야 한다
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
import socket
import time

import redis
from dotenv import load_dotenv
from fastapi import HTTPException

from training import create_model_async, prepare_training, DEFAULT_SAMPLE_RATE, DEFAULT_CPU_CORES

# 학습 코드가 user/, logs/, rvc_cli.py를 이 폴더 기준으로 찾는다
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "127.0.0.1"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True,
)
name = socket.gethostname()  # 워커 이름 = 컴퓨터 이름 (누가 처리했는지 기록용)

STREAM = "stream:train"   # 할 일 목록 (한 줄에 job_id 하나)
GROUP = "train-workers"   # 그룹으로 읽어야 Redis가 "누가 꺼냈고 아직 안 끝냈는지"(PEL)를 기억한다
MAX_ATTEMPTS = 2          # 처음 1번 + 재시도 1번
BLOCK_MS = 5_000          # 새 작업을 최대 5초 기다린 뒤 반복 (Ctrl + C가 바로 먹게)


def ensure_group():
    # 그룹이 없으면 만든다 (mkstream: 스트림이 없으면 같이 만든다). 이미 있으면 넘어간다
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def fail(msg_id, job_key, reason):
    # 실패로 기록하고 목록에서 끝난 것으로 처리한다 (다시 꺼내지 않는다)
    r.hset(job_key, mapping={"status": "fail", "error": reason, "finished_at": timestamp()})
    r.xack(STREAM, GROUP, msg_id)
    print(f"[{name}] {job_key} 실패: {reason}")


def handle(msg_id, fields):
    job_key = f"job:{fields['job_id']}"
    job = r.hgetall(job_key)
    if not job:
        r.xack(STREAM, GROUP, msg_id)
        print(f"[{name}] {job_key} 작업 정보 없음, 건너뜀")
        return
    user_uuid = job["user"]

    # 1) 시도 횟수: 재시도까지 다 썼으면 포기
    attempts = r.hincrby(job_key, "attempts", 1)
    if attempts > MAX_ATTEMPTS:
        fail(msg_id, job_key, f"재시도 횟수 초과 (마지막 에러: {job.get('error', '')})")
        return

    # 2) 학습 준비: 녹음이 없으면 다시 해도 같으니 바로 실패
    try:
        dataset_path, voice_files = prepare_training(user_uuid)
    except FileNotFoundError:
        fail(msg_id, job_key, "녹음 폴더 없음")
        return
    if not voice_files:
        fail(msg_id, job_key, "녹음 파일 없음")
        return

    # 3) 학습
    r.hset(job_key, mapping={"status": "progress", "worker": name, "started_at": timestamp()})
    print(f"[{name}] {job_key} 학습 시작 ({attempts}번째 시도)")
    try:
        asyncio.run(create_model_async(user_uuid, dataset_path, DEFAULT_SAMPLE_RATE, DEFAULT_CPU_CORES, voice_files))
    except HTTPException as e:
        # 녹음이 짧아 조각이 10개 이하: 다시 해도 같으니 바로 실패
        fail(msg_id, job_key, e.detail)
        return
    except Exception as e:
        # 원인 모를 에러: XACK를 하지 않는다 → 다음 반복의 1)에서 다시 꺼낸다 (재시도)
        r.hset(job_key, "error", f"{type(e).__name__}: {e}")
        print(f"[{name}] {job_key} 에러 → 다시 시도: {e}")
        return

    # 4) 성공
    r.hset(job_key, mapping={"status": "success", "error": "", "finished_at": timestamp()})
    r.xack(STREAM, GROUP, msg_id)  # 끝났다고 알린다 → PEL에서 빠진다
    print(f"[{name}] {job_key} 성공")


def work_once():
    # 1) 내가 꺼냈지만 끝내지 못한 작업부터 (학습 중 꺼졌거나, 원인 모를 에러로 재시도할 것)
    #    "0" = 내 PEL을 처음부터
    result = r.xreadgroup(GROUP, name, {STREAM: "0"}, count=1)
    if not result or not result[0][1]:
        # 2) 없으면 새 작업을 기다린다 (">" = 아직 아무에게도 안 준 것)
        result = r.xreadgroup(GROUP, name, {STREAM: ">"}, count=1, block=BLOCK_MS)
    for _, messages in result:
        for msg_id, fields in messages:
            handle(msg_id, fields)


def main():
    ensure_group()
    print(f"[{name}] {STREAM} 대기 중...")
    while True:
        work_once()


if __name__ == "__main__":
    main()
