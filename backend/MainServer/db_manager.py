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

    def delete_user_by_uuid(self, user_uuid: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE uuid = %s", (user_uuid,))
                conn.commit()
        except Exception as e:
            print(f"Error deleting user by uuid: {e}")

    def save_file_metadata(self, user_uuid: str, filename: str, file_path: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO files (user_uuid, filename, file_path) VALUES (%s, %s, %s)",
                    (user_uuid, filename, file_path),
                )
                conn.commit()
        except Exception as e:
            print(f"Error saving file metadata: {e}")

    def get_files_by_user(self, user_uuid: str) -> list:
        try:
            with self.connect() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT * FROM files WHERE user_uuid = %s", (user_uuid,)
                )
                return cursor.fetchall()
        except Exception as e:
            print(f"Error getting files by user: {e}")
            return []

    def get_file_by_filename(self, user_uuid: str, filename: str) -> dict:
        try:
            with self.connect() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT * FROM files WHERE user_uuid = %s AND filename = %s",
                    (user_uuid, filename),
                )
                return cursor.fetchone() or {}
        except Exception as e:
            print(f"Error getting file by filename: {e}")
            return {}

    def delete_file_by_filename(self, user_uuid: str, filename: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM files WHERE user_uuid = %s AND filename = %s",
                    (user_uuid, filename),
                )
                conn.commit()
        except Exception as e:
            print(f"Error deleting file by filename: {e}")

    def delete_files_by_user(self, user_uuid: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM files WHERE user_uuid = %s", (user_uuid,)
                )
                conn.commit()
        except Exception as e:
            print(f"Error deleting files by user: {e}")

    def delete_user_metadata(self, user_uuid: str):
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                
                # 먼저 사용자가 가지고 있는 파일을 삭제합니다.
                cursor.execute(
                    "DELETE FROM files WHERE user_uuid = %s", (user_uuid,)
                )
                
                # 그 후 사용자 메타데이터를 삭제합니다.
                cursor.execute(
                    "DELETE FROM users WHERE uuid = %s", (user_uuid,)
                )
                
                conn.commit()
                print(f"사용자({user_uuid})의 메타데이터가 삭제되었습니다.")
        except Exception as e:
            print(f"Error deleting user metadata: {e}")


