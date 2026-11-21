import mysql.connector
import os

class DBManager:
    def __init__(self, db_config: dict):
        self.db_config = db_config

    def connect(self):
        return mysql.connector.connect(**self.db_config)

    def create_table(self):
        try:
            conn = self.connect()
            cursor = conn.cursor()
    
            # Read the SQL script from db_schema.sql
            with open("db_schema.sql", "r") as f:
                sql_script = f.read()
    
            # Execute SQL script with multi=True
            for result in cursor.execute(sql_script, multi=True):
                pass  # You can process each result here if needed
    
            conn.commit()
            print("테이블 생성 완료")
        except Exception as e:
            print(f"테이블 생성 실패: {e}")
        finally:
            # Close the cursor and connection
            if cursor:
                cursor.close()
            if conn:
                conn.close()


    def save_user_metadata(self, user_uuid: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (uuid) VALUES (%s)", (user_uuid,)
                )
                conn.commit()
        except Exception as e:
            print(f"Error saving user metadata: {e}")

    def get_user_by_uuid(self, user_uuid: str) -> dict:
        try:
            with self.connect() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT * FROM users WHERE uuid = %s", (user_uuid,)
                )
                return cursor.fetchone() or {}
        except Exception as e:
            print(f"Error getting user by uuid: {e}")
            return {}

    def delete_user_metadata(self, user_uuid: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM users WHERE uuid = %s", (user_uuid,)
                )
                
                conn.commit()
                print(f"사용자({user_uuid})의 메타데이터가 삭제되었습니다.")
        except Exception as e:
            print(f"Error deleting user metadata: {e}")


