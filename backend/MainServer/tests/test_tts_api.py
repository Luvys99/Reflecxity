# 앱이 부르는 TTS API가 Redis 작업 큐로 처리되는지 확인한다 (#38)
# 앱이 기대하는 응답 (android/.../MainActivity.java): 200 + wav 본문이면 재생, 그 밖의 코드는 에러
# 워커는 다른 스레드에서 가짜로 흉내 낸다: 목록에서 꺼내 결과와 끝 신호를 남긴다. Redis는 테스트용 DB 15번 (conftest.py)
import threading

import pytest

import main
import train_queue
import tts_queue

TTS_WORKER_GROUP = "tts-workers"
FAKE_AUDIO = b"RIFF-fake-wav"


@pytest.fixture
def trained_user(test_redis):
    # 학습이 끝난 사용자 (Main이 학습 작업을 기록해 둔 것처럼)
    test_redis.hset(train_queue.job_key("train1"), mapping={"type": "train", "user": "userA", "status": "success"})
    test_redis.set(train_queue.user_train_key("userA"), "train1")
    test_redis.xgroup_create(tts_queue.TTS_STREAM, TTS_WORKER_GROUP, id="0", mkstream=True)
    return "userA"


def start_fake_tts_worker(test_redis, final_status, audio=FAKE_AUDIO):
    # TTS 워커 흉내: 작업 하나를 꺼내 기록하고, 결과(성공일 때)와 끝 신호를 남긴다
    taken = {}

    def work():
        result = test_redis.xreadgroup(TTS_WORKER_GROUP, "test-worker", {tts_queue.TTS_STREAM: ">"}, count=1, block=5000)
        job_id = result[0][1][0][1]["job_id"]
        taken.update(test_redis.hgetall(f"job:{job_id}"), job_id=job_id)
        if final_status == "success":
            test_redis.set(f"job:{job_id}:result", audio)
        else:
            test_redis.hset(f"job:{job_id}", "error", "모델 파일 없음")
        test_redis.hset(f"job:{job_id}", "status", final_status)
        test_redis.lpush(f"job:{job_id}:done", final_status)

    worker = threading.Thread(target=work)
    worker.start()
    return worker, taken


def request_tts(api, user_uuid, text="Hello", **form):
    return api.post(f"/user/{user_uuid}/tts", data={"tts_text": text, **form})


def test_워커가_성공하면_결과_음성을_돌려주고_Redis에서_지운다(api, test_redis, trained_user):
    worker, taken = start_fake_tts_worker(test_redis, "success")

    response = request_tts(api, trained_user, "Nice to meet you", pitch=5)
    worker.join()

    assert response.status_code == 200
    assert response.content == FAKE_AUDIO
    assert response.headers["content-type"] == "audio/wav"
    assert taken["text"] == "Nice to meet you"
    assert taken["pitch"] == "5"
    assert test_redis.get(f"job:{taken['job_id']}:result") is None  # 가져가면서 지웠다


def test_pitch를_안_보내면_기본값으로_넣는다(api, test_redis, trained_user):
    worker, taken = start_fake_tts_worker(test_redis, "success")

    request_tts(api, trained_user)
    worker.join()

    assert taken["pitch"] == str(main.DEFAULT_PITCH)


def test_워커가_실패하면_결과_없이_500으로_답한다(api, test_redis, trained_user):
    # 예전에는 실패해도 남아 있던 이전 문장의 음성이 200으로 나갔다 (#38)
    worker, _ = start_fake_tts_worker(test_redis, "fail")

    response = request_tts(api, trained_user)
    worker.join()

    assert response.status_code == 500
    assert "모델 파일 없음" in response.json()["detail"]


def test_시간_안에_끝_신호가_없으면_504로_답한다(api, test_redis, trained_user, monkeypatch):
    monkeypatch.setattr(main, "TTS_WAIT_SECONDS", 1)

    response = request_tts(api, trained_user)

    assert response.status_code == 504


def test_빈_문장은_큐에_넣지_않고_400으로_답한다(api, test_redis, trained_user):
    response = request_tts(api, trained_user, "   ")

    assert response.status_code == 400
    assert test_redis.xlen(tts_queue.TTS_STREAM) == 0


def test_학습이_끝나지_않은_사용자는_큐에_넣지_않고_400으로_답한다(api, test_redis, trained_user):
    test_redis.hset(train_queue.job_key("train1"), "status", "progress")

    assert request_tts(api, trained_user).status_code == 400
    assert request_tts(api, "nobody").status_code == 400
    assert test_redis.xlen(tts_queue.TTS_STREAM) == 0
