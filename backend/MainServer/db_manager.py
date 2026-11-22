import mysql.connector
import os

# DB 함수는 에러를 잡지 않고 그대로 올린다 (#19)
# 예전에는 print만 하고 넘어가서, 테이블이 없어도 서버가 정상처럼 뜨고 사용자 삭제가 실패해도 "성공"이라고 답했다
# → 서버를 켤 때 실패하면 서버가 멈추고, 요청 중에 실패하면 500 + Main 로그에 원인이 남는다
class DBManager:
    def __init__(self, db_config: dict):
        self.db_config = db_config

    def connect(self):
        return mysql.connector.connect(**self.db_config)

    # db_schema.sql을 한 문장씩 실행한다 (mysql-connector 9.x에서 사라진 multi=True를 쓰지 않는다)
    def create_table(self):
        with open("db_schema.sql", "r") as f:
            statements = [s.strip() for s in f.read().split(";") if s.strip()]

        with self.connect() as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            conn.commit()
        print("테이블 생성 완료")

    def save_user_metadata(self, user_uuid: str):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (uuid) VALUES (%s)", (user_uuid,)
            )
            conn.commit()

    def get_user_by_uuid(self, user_uuid: str) -> dict:
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM users WHERE uuid = %s", (user_uuid,)
            )
            return cursor.fetchone() or {}

    def delete_user_metadata(self, user_uuid: str):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM users WHERE uuid = %s", (user_uuid,)
            )
            conn.commit()
            print(f"사용자({user_uuid})의 메타데이터가 삭제되었습니다.")
