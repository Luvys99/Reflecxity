# 테스트 파일들이 같이 쓰는 준비물 (pytest가 자동으로 읽는다)
import os

import pytest
import redis

TEST_DB = 15  # 실제 작업이 있는 0번 DB를 건드리지 않는다


@pytest.fixture
def test_redis():
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
