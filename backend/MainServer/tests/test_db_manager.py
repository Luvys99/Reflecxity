# DB 함수가 실패를 삼키지 않는지 확인한다 (#19)
# 실행: cd backend/MainServer && .venv/bin/python -m pytest tests (compose를 켜 둬야 한다)
import mysql.connector
import pytest

import main
from db_manager import DBManager

# 아무것도 듣지 않는 포트 → 연결이 바로 실패한다
UNREACHABLE_DB_CONFIG = {**main.DB_CONFIG, "host": "127.0.0.1", "port": 1, "connection_timeout": 2}


@pytest.fixture
def broken_db():
    return DBManager(UNREACHABLE_DB_CONFIG)


def test_DB에_못_붙으면_테이블_생성이_에러를_올린다(broken_db):
    # 예전에는 print만 하고 넘어가서 서버가 테이블 없이 정상처럼 떴다
    with pytest.raises(mysql.connector.Error):
        broken_db.create_table()


def test_DB에_못_붙으면_사용자_저장_조회_삭제가_에러를_올린다(broken_db):
    # 예전에는 삭제가 실패해도 API가 "사용자 삭제 성공"이라고 답했다
    with pytest.raises(mysql.connector.Error):
        broken_db.save_user_metadata("test-user")
    with pytest.raises(mysql.connector.Error):
        broken_db.get_user_by_uuid("test-user")
    with pytest.raises(mysql.connector.Error):
        broken_db.delete_user_metadata("test-user")


def test_테이블_생성은_여러_번_해도_된다():
    # 서버를 켤 때마다 부른다 (CREATE TABLE IF NOT EXISTS)
    main.db_manager.create_table()
    main.db_manager.create_table()
