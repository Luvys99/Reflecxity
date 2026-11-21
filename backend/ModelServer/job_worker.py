# 워커 공통 부분: Redis 스트림에서 작업을 꺼내고, 작업 정보 job:{job_id}에 상태를 기록한다 (#35)
# 학습 워커(train_worker.py)와 TTS 워커가 같이 쓴다. 작업 한 건을 실제로 하는 함수(run_job)만 워커마다 다르다
import argparse
import os
import socket
import time

import redis

# 결과(job:{id}:result)와 끝 신호(job:{id}:done)를 Redis에 남겨 두는 시간. Main이 가져가지 못한 것의 청소용
RESULT_TTL_SECONDS = 600


class JobFailed(Exception):
    """다시 해도 같은 결과라 재시도하지 않는 실패 (녹음 없음, 모델 없음 등). run_job이 던진다"""


def connect_redis():
    # 접속 정보는 .env에서 읽는다 (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True,
    )


def read_worker_number():
    # 실행할 때 --number로 워커 번호를 받는다 (없으면 1). 한 컴퓨터에 같은 종류의 워커를 여러 개 켤 때 쓴다 (#51)
    parser = argparse.ArgumentParser()
    parser.add_argument("--number", type=int, default=1, help="이 컴퓨터에서 이 워커의 번호. 다시 켤 때 같은 번호를 쓰면 못 끝낸 작업을 이어받는다")
    return parser.parse_args().number


def format_now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class JobWorker:
    def __init__(self, redis_client, stream, group, max_attempts, run_job, worker_number=1, wait_for_job_ms=5_000):
        self.redis_client = redis_client
        self.stream = stream                    # 할 일 목록 (한 줄에 job_id 하나)
        self.group = group                      # 그룹으로 읽어야 Redis가 "누가 꺼냈고 아직 안 끝냈는지"(PEL)를 기억한다
        self.max_attempts = max_attempts        # 처음 1번 + 재시도 횟수
        self.run_job = run_job                  # 작업 한 건을 실제로 하는 함수. 작업 정보(dict)를 받고, 결과(bytes)가 있으면 돌려준다
        self.wait_for_job_ms = wait_for_job_ms  # 새 작업을 기다리는 시간. 끝나면 다시 기다린다 (Ctrl + C가 바로 먹게)
        # 워커 이름 = 컴퓨터 이름-번호. Redis는 이 이름으로 "누가 꺼냈고 아직 안 끝냈는지"(PEL)를 기억한다
        # 한 컴퓨터의 워커끼리 이름이 같으면 서로의 PEL을 자기 것으로 꺼내 같은 작업을 두 번 한다 (#51)
        self.worker_name = f"{socket.gethostname()}-{worker_number}"

    def create_group_if_missing(self):
        # 그룹이 없으면 만든다 (mkstream: 스트림이 없으면 같이 만든다). 이미 있으면 넘어간다
        try:
            self.redis_client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def signal_job_done(self, job_key, status):
        # 끝났다는 신호. 기다리는 쪽(Main)은 BLPOP으로 이 목록을 기다리다가 바로 깨어난다
        # 최종 success / fail에서만 보낸다 (재시도 중에는 보내지 않음)
        done_key = f"{job_key}:done"
        self.redis_client.lpush(done_key, status)
        self.redis_client.expire(done_key, RESULT_TTL_SECONDS)

    def mark_job_failed(self, message_id, job_key, reason):
        # 실패로 기록하고 목록에서 끝난 것으로 처리한다 (다시 꺼내지 않는다)
        self.redis_client.hset(job_key, mapping={"status": "fail", "error": reason, "finished_at": format_now()})
        self.redis_client.xack(self.stream, self.group, message_id)
        self.signal_job_done(job_key, "fail")
        print(f"[{self.worker_name}] {job_key} 실패: {reason}")

    def process_job(self, message_id, message):
        job_key = f"job:{message['job_id']}"
        job = self.redis_client.hgetall(job_key)
        if not job:
            self.redis_client.xack(self.stream, self.group, message_id)
            print(f"[{self.worker_name}] {job_key} 작업 정보 없음, 건너뜀")
            return

        # 1) 시도 횟수: 재시도까지 다 썼으면 포기
        attempts = self.redis_client.hincrby(job_key, "attempts", 1)
        if attempts > self.max_attempts:
            self.mark_job_failed(message_id, job_key, f"재시도 횟수 초과 (마지막 에러: {job.get('error', '')})")
            return

        # 2) 작업 실행
        self.redis_client.hset(job_key, mapping={"status": "progress", "worker": self.worker_name, "started_at": format_now()})
        print(f"[{self.worker_name}] {job_key} 시작 ({attempts}번째 시도)")
        try:
            result = self.run_job(job)
        except JobFailed as e:
            # 다시 해도 같은 실패: 바로 실패로 끝낸다
            self.mark_job_failed(message_id, job_key, str(e))
            return
        except Exception as e:
            # 원인 모를 에러: XACK를 하지 않는다 → 다음 반복의 1)에서 다시 꺼낸다 (재시도)
            self.redis_client.hset(job_key, "error", f"{type(e).__name__}: {e}")
            print(f"[{self.worker_name}] {job_key} 에러 → 다시 시도: {e}")
            return

        # 3) 성공: 결과가 있으면 먼저 저장하고 신호를 보낸다 (신호를 받은 쪽이 바로 결과를 가져갈 수 있게)
        if result is not None:
            self.redis_client.set(f"{job_key}:result", result, ex=RESULT_TTL_SECONDS)
        self.redis_client.hset(job_key, mapping={"status": "success", "error": "", "finished_at": format_now()})
        self.redis_client.xack(self.stream, self.group, message_id)  # 끝났다고 알린다 → PEL에서 빠진다
        self.signal_job_done(job_key, "success")
        print(f"[{self.worker_name}] {job_key} 성공")

    def process_next_job(self):
        # 1) 내가 꺼냈지만 끝내지 못한 작업부터 (작업 중 꺼졌거나, 원인 모를 에러로 재시도할 것)
        #    "0" = 내 PEL을 처음부터
        result = self.redis_client.xreadgroup(self.group, self.worker_name, {self.stream: "0"}, count=1)
        if not result or not result[0][1]:
            # 2) 없으면 새 작업을 기다린다 (">" = 아직 아무에게도 안 준 것)
            result = self.redis_client.xreadgroup(self.group, self.worker_name, {self.stream: ">"}, count=1, block=self.wait_for_job_ms)
        for _, messages in result:
            for message_id, message in messages:
                self.process_job(message_id, message)

    def run_forever(self):
        self.create_group_if_missing()
        print(f"[{self.worker_name}] {self.stream} 대기 중...")
        while True:
            self.process_next_job()
