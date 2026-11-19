# train_worker.py가 지켜야 할 규칙을 실제 Redis(테스트용 DB 15번)로 확인한다. 학습은 가짜 함수로 바꾼다
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests  (Mac Redis가 켜져 있어야 함)
import os

import pytest
import redis
from fastapi import HTTPException

import train_worker as worker

TEST_DB = 15  # 실제 작업이 있는 0번 DB를 건드리지 않는다


@pytest.fixture
def test_redis(monkeypatch):
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=TEST_DB,
        decode_responses=True,
    )
    client.flushdb()
    monkeypatch.setattr(worker, "redis_client", client)
    monkeypatch.setattr(worker, "WAIT_FOR_JOB_MS", 100)
    monkeypatch.setattr(worker, "prepare_training", lambda user_uuid: ("raw", ["voice.m4a"]))
    worker.create_group_if_missing()
    yield client
    client.flushdb()


def enqueue_train_job(test_redis, job_id="job1"):
    # Main이 할 일 (④): 작업 정보를 queued로 만들고 목록에 job_id를 넣는다
    test_redis.hset(f"job:{job_id}", mapping={"type": "train", "user": "user1", "status": "queued", "attempts": 0})
    test_redis.xadd(worker.TRAIN_STREAM, {"job_id": job_id})
    return f"job:{job_id}"


def fake_training_results(monkeypatch, *results):
    # 가짜 학습: 부를 때마다 results를 앞에서부터 하나씩 쓴다. 예외면 던지고, None이면 성공
    calls = []

    async def fake_train_model(*args):
        calls.append(args)
        result = results[len(calls) - 1]
        if result is not None:
            raise result

    monkeypatch.setattr(worker, "create_model_async", fake_train_model)
    return calls


def count_unfinished_jobs(test_redis):
    # 꺼냈지만 아직 XACK 안 된 작업 수
    return test_redis.xpending(worker.TRAIN_STREAM, worker.TRAIN_WORKER_GROUP)["pending"]


def test_성공하면_success로_기록하고_목록에서_끝낸다(test_redis, monkeypatch):
    fake_training_results(monkeypatch, None)
    job = enqueue_train_job(test_redis)

    worker.process_next_job()

    assert test_redis.hget(job, "status") == "success"
    assert test_redis.hget(job, "attempts") == "1"
    assert count_unfinished_jobs(test_redis) == 0


def test_녹음이_없으면_학습하지_않고_바로_실패한다(test_redis, monkeypatch):
    calls = fake_training_results(monkeypatch, None)
    monkeypatch.setattr(worker, "prepare_training", lambda user_uuid: ("raw", []))
    job = enqueue_train_job(test_redis)

    worker.process_next_job()

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error") == "녹음 파일 없음"
    assert calls == []
    assert count_unfinished_jobs(test_redis) == 0


def test_녹음_폴더가_없으면_바로_실패한다(test_redis, monkeypatch):
    def no_folder(user_uuid):
        raise FileNotFoundError(user_uuid)

    monkeypatch.setattr(worker, "prepare_training", no_folder)
    job = enqueue_train_job(test_redis)

    worker.process_next_job()

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error") == "녹음 폴더 없음"
    assert count_unfinished_jobs(test_redis) == 0


def test_조각이_10개_이하면_재시도하지_않고_실패한다(test_redis, monkeypatch):
    calls = fake_training_results(monkeypatch, HTTPException(status_code=500, detail="조각 10개 이하"))
    job = enqueue_train_job(test_redis)

    worker.process_next_job()
    worker.process_next_job()  # 한 번 더 돌아도 다시 꺼낼 것이 없어야 한다

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error") == "조각 10개 이하"
    assert len(calls) == 1
    assert count_unfinished_jobs(test_redis) == 0


def test_원인_모를_에러는_한_번_다시_해서_성공할_수_있다(test_redis, monkeypatch):
    calls = fake_training_results(monkeypatch, RuntimeError("GPU 메모리 부족"), None)
    job = enqueue_train_job(test_redis)

    worker.process_next_job()
    assert count_unfinished_jobs(test_redis) == 1  # XACK 안 함 → 다시 꺼낼 수 있게 남아 있다
    assert "GPU 메모리 부족" in test_redis.hget(job, "error")

    worker.process_next_job()
    assert test_redis.hget(job, "status") == "success"
    assert test_redis.hget(job, "attempts") == "2"
    assert len(calls) == 2
    assert count_unfinished_jobs(test_redis) == 0


def test_원인_모를_에러가_계속되면_재시도_뒤_실패한다(test_redis, monkeypatch):
    calls = fake_training_results(monkeypatch, RuntimeError("1번째"), RuntimeError("2번째"))
    job = enqueue_train_job(test_redis)

    worker.process_next_job()
    worker.process_next_job()
    worker.process_next_job()  # 3번째로 꺼냈을 때 포기

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error").startswith("재시도 횟수 초과")
    assert len(calls) == 2
    assert count_unfinished_jobs(test_redis) == 0


def test_꺼냈지만_못_끝낸_작업을_새_작업보다_먼저_한다(test_redis, monkeypatch):
    fake_training_results(monkeypatch, None, None)
    first = enqueue_train_job(test_redis, "first")
    # 워커가 first를 꺼낸 뒤 학습 중에 꺼졌다 (XACK 없이 PEL에 남음)
    test_redis.xreadgroup(worker.TRAIN_WORKER_GROUP, worker.worker_name, {worker.TRAIN_STREAM: ">"}, count=1)
    second = enqueue_train_job(test_redis, "second")

    worker.process_next_job()

    assert test_redis.hget(first, "status") == "success"
    assert test_redis.hget(second, "status") == "queued"
