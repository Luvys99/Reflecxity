# 학습 작업 큐 (Redis): 학습 요청을 stream:train에 넣고, 작업 정보 job:{job_id}로 상태를 알려 준다 (#42)
# 작업은 Windows의 학습 워커(ModelServer/train_worker.py)가 꺼내 처리한다
# 키 이름과 상태 값은 워커와의 약속이다 (AGENTS.md "Redis 키" 표). 한쪽만 바꾸면 깨진다
import os
import time
import uuid

import redis.asyncio as redis

TRAIN_STREAM = "stream:train"
TRAIN_WORKER_GROUP = "train-workers"
ACTIVE_STATUSES = ("queued", "progress")  # 아직 끝나지 않은 상태


def connect_redis(decode_responses=True):
    # 접속 정보는 .env에서 읽는다 (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, 테스트는 REDIS_DB=15)
    # TTS 결과(음성 bytes)를 읽을 때는 글자로 바꾸지 않는 연결(decode_responses=False)을 쓴다
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=decode_responses,
    )


async def create_group_if_missing(redis_client):
    # 워커 그룹이 없으면 만든다. Main이 먼저 켜져도 대기 순서·시간 초과 계산(XPENDING)이 되도록
    # 워커(job_worker.py)와 같은 설정: 목록 처음부터 읽는다(id="0"), 목록이 없으면 같이 만든다
    try:
        await redis_client.xgroup_create(TRAIN_STREAM, TRAIN_WORKER_GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def job_key(job_id):
    return f"job:{job_id}"


def user_train_key(user_uuid):
    # 사용자 → 이 사용자의 최근 학습 작업 ID
    return f"user:{user_uuid}:train"


async def find_train_job(redis_client, user_uuid):
    # 사용자의 최근 학습 작업 정보. 없으면 None
    job_id = await redis_client.get(user_train_key(user_uuid))
    if not job_id:
        return None
    job = await redis_client.hgetall(job_key(job_id))
    return job or None


async def enqueue_train_job(redis_client, user_uuid):
    # 작업 정보(queued)를 만들고 목록에 작업 ID를 넣는다. 이미 끝나지 않은 학습이 있으면 None
    job = await find_train_job(redis_client, user_uuid)
    if job and job["status"] in ACTIVE_STATUSES:
        return None

    job_id = str(uuid.uuid4())
    await redis_client.hset(job_key(job_id), mapping={
        "type": "train",
        "user": user_uuid,
        "status": "queued",
        "attempts": 0,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    message_id = await redis_client.xadd(TRAIN_STREAM, {"job_id": job_id})
    await redis_client.hset(job_key(job_id), "message_id", message_id)  # 대기 순서와 시간 초과를 계산할 때 쓴다
    await redis_client.set(user_train_key(user_uuid), job_id)
    return job_id


async def count_jobs_ahead(redis_client, job):
    # 목록에서 내 작업보다 먼저 들어온 작업 중 아직 끝나지 않은 것의 수
    ahead = 0
    for message_id, message in await redis_client.xrange(TRAIN_STREAM, "-", job["message_id"]):
        if message_id == job["message_id"]:
            break
        status = await redis_client.hget(job_key(message["job_id"]), "status")
        if status in ACTIVE_STATUSES:
            ahead += 1
    return ahead


async def working_ms(redis_client, job):
    # 워커가 이 작업을 꺼낸 뒤 지난 시간(ms). Redis가 직접 센다 (두 컴퓨터의 시계 차이와 상관없음)
    # 재시도로 다시 꺼내면 0부터 다시 센다. 꺼낸 워커가 없으면 None
    pending = await redis_client.xpending_range(TRAIN_STREAM, TRAIN_WORKER_GROUP, job["message_id"], job["message_id"], 1)
    return pending[0]["time_since_delivered"] if pending else None


async def count_train_jobs_by_status(redis_client):
    # 목록의 작업들을 상태별로 센다 (queued, progress)
    counts = {"queued": 0, "progress": 0}
    for _, message in await redis_client.xrange(TRAIN_STREAM):
        status = await redis_client.hget(job_key(message["job_id"]), "status")
        if status in counts:
            counts[status] += 1
    return counts
