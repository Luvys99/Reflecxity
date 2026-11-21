# 앱이 부르는 학습 API(요청, 대기 순서, 완료 확인)가 Redis 작업 큐 위에서 예전과 같은 모양으로 답하는지 확인한다 (#42)
# 앱이 기대하는 응답: android/.../TaskStatusActivity.java
#   /queue      → {"status", "position"}, position 1 = 학습 중, 2 이상 = 대기 순번 (position - 1)
#   /modelcheck → 200 {"message": "모델 파일 존재"} = 완료, 200 다른 문장 = 진행 중, 500 = 실패
# 워커는 가짜로 흉내 낸다 (Redis 명령으로 꺼내고 상태를 바꾼다). Redis는 테스트용 DB 15번 (conftest.py)
# 실행: cd backend/MainServer && .venv/bin/python -m pytest tests  (Mac Redis가 켜져 있어야 함)
import main
import train_queue


def request_training(api, user_uuid):
    return api.post(f"/user/{user_uuid}/models")


def fake_worker_takes_next_job(test_redis):
    # 학습 워커가 하는 일 흉내: 목록에서 하나 꺼내고 상태를 progress로
    result = test_redis.xreadgroup(train_queue.TRAIN_WORKER_GROUP, "test-worker", {train_queue.TRAIN_STREAM: ">"}, count=1)
    job_id = result[0][1][0][1]["job_id"]
    test_redis.hset(train_queue.job_key(job_id), "status", "progress")
    return job_id


def set_status(test_redis, user_uuid, status):
    job_id = test_redis.get(train_queue.user_train_key(user_uuid))
    test_redis.hset(train_queue.job_key(job_id), "status", status)


def test_학습을_요청하면_작업_정보와_목록이_생기고_응답_모양은_그대로다(api, test_redis):
    response = request_training(api, "userA")

    assert response.status_code == 200
    assert response.json() == {"message": "모델 생성 요청이 대기열에 추가되었습니다.", "model_id": "userA"}
    job_id = test_redis.get(train_queue.user_train_key("userA"))
    job = test_redis.hgetall(train_queue.job_key(job_id))
    assert job["type"] == "train"
    assert job["user"] == "userA"
    assert job["status"] == "queued"
    assert test_redis.xlen(train_queue.TRAIN_STREAM) == 1


def test_대기_중에_다시_요청하면_새로_넣지_않는다(api, test_redis):
    request_training(api, "userA")

    response = request_training(api, "userA")

    assert response.json() == {"message": "이미 모델 생성 요청이 진행 중이거나 대기열에 있습니다."}
    assert test_redis.xlen(train_queue.TRAIN_STREAM) == 1


def test_끝난_뒤_다시_요청하면_새_작업이_생긴다(api, test_redis):
    request_training(api, "userA")
    set_status(test_redis, "userA", "fail")

    response = request_training(api, "userA")

    assert response.json()["message"] == "모델 생성 요청이 대기열에 추가되었습니다."
    assert test_redis.xlen(train_queue.TRAIN_STREAM) == 2


def test_대기_순서는_학습_중이면_1_그_뒤는_2다(api, test_redis):
    request_training(api, "userA")
    request_training(api, "userB")
    fake_worker_takes_next_job(test_redis)  # A 학습 시작

    response_a = api.get("/user/userA/queue").json()
    assert response_a["status"] == "대기열에 있습니다." and response_a["position"] == 1
    assert api.get("/user/userB/queue").json() == {"status": "대기열에 있습니다.", "position": 2}


def test_학습_중이면_시작한_지_지난_초를_주고_대기_중이면_주지_않는다(api, test_redis):
    # 앱이 남은 시간 = 예상 학습 시간 - 지난 시간으로 보여 준다 (#89)
    request_training(api, "userA")
    request_training(api, "userB")
    fake_worker_takes_next_job(test_redis)  # A 학습 시작

    response_a = api.get("/user/userA/queue").json()
    assert isinstance(response_a["elapsed_seconds"], int)
    assert 0 <= response_a["elapsed_seconds"] < 5
    assert "elapsed_seconds" not in api.get("/user/userB/queue").json()


def test_앞_작업이_끝나면_대기_순서가_당겨진다(api, test_redis):
    request_training(api, "userA")
    request_training(api, "userB")
    set_status(test_redis, "userA", "success")

    assert api.get("/user/userB/queue").json() == {"status": "대기열에 있습니다.", "position": 1}


def test_요청이_없거나_끝났으면_대기열에_없다고_답한다(api, test_redis):
    assert api.get("/user/nobody/queue").json() == {"status": "대기열에 추가되지 않았습니다."}

    request_training(api, "userA")
    set_status(test_redis, "userA", "success")
    assert api.get("/user/userA/queue").json() == {"status": "대기열에 추가되지 않았습니다."}


def test_완료_확인은_상태에_따라_예전과_같은_응답을_준다(api, test_redis):
    assert api.get("/user/nobody/modelcheck").json() == {"message": "모델 파일 없음"}

    request_training(api, "userA")
    assert api.get("/user/userA/modelcheck").json() == {"message": "모델 파일 없음"}  # queued

    fake_worker_takes_next_job(test_redis)
    assert api.get("/user/userA/modelcheck").json() == {"message": "모델 파일 없음"}  # progress

    set_status(test_redis, "userA", "success")
    response = api.get("/user/userA/modelcheck")
    assert response.status_code == 200
    assert response.json() == {"message": "모델 파일 존재"}

    set_status(test_redis, "userA", "fail")
    assert api.get("/user/userA/modelcheck").status_code == 500


def test_워커가_꺼낸_뒤_시간이_초과되면_실패로_응답한다(api, test_redis, monkeypatch):
    request_training(api, "userA")
    fake_worker_takes_next_job(test_redis)
    monkeypatch.setattr(main, "MODEL_GENERATION_TIMEOUT_SECONDS", 0)

    response = api.get("/user/userA/modelcheck")

    assert response.status_code == 500
    assert response.json()["detail"] == "모델 생성 시간 초과"


def test_전체_대기열은_대기와_진행_수를_센다(api, test_redis):
    request_training(api, "userA")
    request_training(api, "userB")
    request_training(api, "userC")
    fake_worker_takes_next_job(test_redis)
    set_status(test_redis, "userC", "fail")

    assert api.get("/queue_status").json() == {"queue_size": 1, "active_tasks": 1}
