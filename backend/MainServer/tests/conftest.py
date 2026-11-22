# 테스트 파일들이 같이 쓰는 준비물 (pytest가 자동으로 읽는다)
import os

import pytest
import redis
from fastapi.testclient import TestClient

import main

TEST_DB = 15  # 실제 작업이 있는 0번 DB를 건드리지 않는다


@pytest.fixture
def test_redis(monkeypatch):
    # Main은 REDIS_DB 환경 변수로 테스트 DB에 붙는다. 확인·준비는 이 동기 연결로 한다
    monkeypatch.setenv("REDIS_DB", str(TEST_DB))
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=TEST_DB,
        decode_responses=True,
    )
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def api(test_redis, monkeypatch):
    # .env에 APP_KEY가 있어도 테스트에서는 앱 키 검사를 끈다 (#115). 검사를 시험하는 테스트는 직접 켠다
    monkeypatch.setattr(main, "APP_KEY", None)
    with TestClient(main.app) as client:  # with 안에서 startup이 돌아 Redis에 연결한다
        yield client
