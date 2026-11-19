# tts_worker.py의 TTS 전용 규칙을 실제 Redis(테스트용 DB 15번, conftest.py)로 확인한다. TTS는 가짜 함수로 바꾼다
# 꺼내기·재시도 같은 공통 동작은 test_train_worker.py가 확인한다
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests  (Mac Redis가 켜져 있어야 함)
import os

import pytest
from fastapi import HTTPException

import tts_worker


@pytest.fixture
def tts_job_worker(test_redis, monkeypatch):
    # 테스트 Redis로 TTS 워커를 만든다. 기본은 모델 파일이 있는 상태
    monkeypatch.setattr(tts_worker, "find_model_files", lambda user_uuid: ("model.pth", "added_model.index"))
    job_worker = tts_worker.create_tts_worker(test_redis)
    job_worker.wait_for_job_ms = 100
    job_worker.create_group_if_missing()
    return job_worker


def enqueue_tts_job(test_redis, job_id="job1", **fields):
    # Main이 할 일 (④): 작업 정보를 queued로 만들고 목록에 job_id를 넣는다
    job = {"type": "tts", "user": "user1", "text": "Hello", "pitch": 3, "status": "queued", "attempts": 0}
    job.update(fields)
    test_redis.hset(f"job:{job_id}", mapping=job)
    test_redis.xadd(tts_worker.TTS_STREAM, {"job_id": job_id})
    return f"job:{job_id}"


FAKE_AUDIO = "fake-wav"


def fake_tts_results(monkeypatch, *results):
    # 가짜 TTS: 부를 때마다 results를 앞에서부터 하나씩 쓴다. 예외면 던지고, None이면 결과 파일에 FAKE_AUDIO를 쓴다
    calls = []

    async def fake_synthesize_voice(user_uuid, tts_text, pitch, pth_path, index_path, output_path):
        calls.append((user_uuid, tts_text, pitch, pth_path, index_path, output_path))
        result = results[len(calls) - 1]
        if result is not None:
            raise result
        with open(output_path, "w") as f:
            f.write(FAKE_AUDIO)

    monkeypatch.setattr(tts_worker, "synthesize_voice", fake_synthesize_voice)
    return calls


def count_unfinished_jobs(test_redis):
    # 꺼냈지만 아직 XACK 안 된 작업 수
    return test_redis.xpending(tts_worker.TTS_STREAM, tts_worker.TTS_WORKER_GROUP)["pending"]


def test_성공하면_success로_기록하고_문장과_pitch를_그대로_넘긴다(test_redis, tts_job_worker, monkeypatch):
    calls = fake_tts_results(monkeypatch, None)
    job = enqueue_tts_job(test_redis, text="Nice to meet you", pitch=5)

    tts_job_worker.process_next_job()

    assert test_redis.hget(job, "status") == "success"
    assert test_redis.hget(job, "attempts") == "1"
    assert calls[0][:5] == ("user1", "Nice to meet you", "5", "model.pth", "added_model.index")
    assert count_unfinished_jobs(test_redis) == 0


def test_모델_파일이_없으면_TTS를_하지_않고_바로_실패한다(test_redis, tts_job_worker, monkeypatch):
    calls = fake_tts_results(monkeypatch, None)

    def no_model(user_uuid):
        raise FileNotFoundError(user_uuid)

    monkeypatch.setattr(tts_worker, "find_model_files", no_model)
    job = enqueue_tts_job(test_redis)

    tts_job_worker.process_next_job()

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error") == "모델 파일 없음"
    assert calls == []
    assert count_unfinished_jobs(test_redis) == 0


def test_문장이_없으면_바로_실패한다(test_redis, tts_job_worker, monkeypatch):
    calls = fake_tts_results(monkeypatch, None)
    job = enqueue_tts_job(test_redis, text="")

    tts_job_worker.process_next_job()

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error") == "문장 없음"
    assert calls == []


def test_결과_파일이_없으면_다시_해서_성공할_수_있다(test_redis, tts_job_worker, monkeypatch):
    # edge-tts가 일시적으로 소리를 안 보내면 synthesize_voice가 결과 파일 없음으로 HTTPException(500)을 던진다
    no_output = HTTPException(status_code=500, detail="TTS wav 파일을 찾을 수 없습니다.")
    calls = fake_tts_results(monkeypatch, no_output, None)
    job = enqueue_tts_job(test_redis)

    tts_job_worker.process_next_job()
    assert count_unfinished_jobs(test_redis) == 1  # XACK 안 함 → 다시 꺼낼 수 있게 남아 있다

    tts_job_worker.process_next_job()
    assert test_redis.hget(job, "status") == "success"
    assert test_redis.hget(job, "attempts") == "2"
    assert len(calls) == 2


def test_세_번_모두_실패하면_재시도_뒤_실패한다(test_redis, tts_job_worker, monkeypatch):
    no_output = HTTPException(status_code=500, detail="TTS wav 파일을 찾을 수 없습니다.")
    calls = fake_tts_results(monkeypatch, no_output, no_output, no_output)
    job = enqueue_tts_job(test_redis)

    for _ in range(4):  # 4번째로 꺼냈을 때 포기
        tts_job_worker.process_next_job()

    assert test_redis.hget(job, "status") == "fail"
    assert test_redis.hget(job, "error").startswith("재시도 횟수 초과")
    assert len(calls) == 3
    assert count_unfinished_jobs(test_redis) == 0


def done_signals(test_redis, job):
    return test_redis.lrange(f"{job}:done", 0, -1)


def test_성공하면_결과를_Redis에_담고_끝_신호를_남기며_임시_파일은_지운다(test_redis, tts_job_worker, monkeypatch):
    calls = fake_tts_results(monkeypatch, None)
    job = enqueue_tts_job(test_redis)

    tts_job_worker.process_next_job()

    assert test_redis.get(f"{job}:result") == FAKE_AUDIO
    assert test_redis.ttl(f"{job}:result") > 0  # 가져가지 않아도 시간이 지나면 지워진다
    assert done_signals(test_redis, job) == ["success"]
    output_path = calls[0][5]
    assert not os.path.exists(output_path)


def test_작업마다_다른_결과_파일을_쓴다(test_redis, tts_job_worker, monkeypatch):
    # 같은 사용자의 TTS가 겹쳐도 서로의 결과를 덮어쓰지 않는다 (#36)
    calls = fake_tts_results(monkeypatch, None, None)
    enqueue_tts_job(test_redis, "job1")
    enqueue_tts_job(test_redis, "job2")

    tts_job_worker.process_next_job()
    tts_job_worker.process_next_job()

    assert calls[0][5] != calls[1][5]


def test_재시도_중에는_끝_신호를_보내지_않는다(test_redis, tts_job_worker, monkeypatch):
    no_output = HTTPException(status_code=500, detail="TTS wav 파일을 찾을 수 없습니다.")
    fake_tts_results(monkeypatch, no_output, None)
    job = enqueue_tts_job(test_redis)

    tts_job_worker.process_next_job()
    assert done_signals(test_redis, job) == []

    tts_job_worker.process_next_job()
    assert done_signals(test_redis, job) == ["success"]


def test_최종_실패하면_결과_없이_실패_신호를_남긴다(test_redis, tts_job_worker, monkeypatch):
    fake_tts_results(monkeypatch, None)
    job = enqueue_tts_job(test_redis, text="")

    tts_job_worker.process_next_job()

    assert done_signals(test_redis, job) == ["fail"]
    assert test_redis.get(f"{job}:result") is None
