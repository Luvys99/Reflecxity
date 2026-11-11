import os
from typing import List, Dict
import configparser
import shutil
import requests

from fastapi import UploadFile
from db_manager import DBManager
from utils import generate_uuid, allowed_file, get_file_extension

class FileHandler:
    def __init__(self, db_config: dict, allowed_extensions: set, config: configparser.ConfigParser):
        self.db_manager = DBManager(db_config)
        self.allowed_extensions = allowed_extensions
        self.base_dir = config['FILE_PATH']['base_dir']
        self.model_server_api_url = config.get('MODEL_SERVER', 'api_url')  # 모델 서버 API 주소

    async def save_file_chunk(self, user_uuid: str, file: UploadFile, filename: str, chunk_number: int, is_last_chunk: bool) -> str:
        user_folder = os.path.join(self.base_dir, "user", user_uuid, "raw")
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, filename)

        try:
            with open(file_path, 'ab' if chunk_number > 1 else 'wb') as f:
                chunk = await file.read()
                f.write(chunk)
            return file_path
        except Exception as e:
            print(f"Error saving file chunk {chunk_number}: {e}")
            return None
    
    def get_user_folder(self, user_uuid: str) -> List[Dict]:
        return self.db_manager.get_files_by_user(user_uuid)

    def remove_file(self, user_uuid: str, filename: str) -> bool:
        file_data = self.db_manager.get_file_by_filename(user_uuid, filename)
        if file_data:
            file_path = file_data.get('file_path')
            try:
                os.remove(file_path)
                self.db_manager.delete_file_by_filename(user_uuid, filename)
                return True
            except Exception as e:
                print(f"Error deleting file: {e}")
                return False
        return False

    def get_file_path(self, user_uuid: str, filename: str) -> str:
        file_data = self.db_manager.get_file_by_filename(user_uuid, filename)
        if file_data:
            return file_data.get('file_path')
        return None

    def remove_user(self, user_uuid: str) -> bool:
        try:
            self.db_manager.delete_user_by_uuid(user_uuid)  # 데이터베이스에서 사용자 정보 삭제
            self.db_manager.delete_files_by_user(user_uuid)
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"Error removing user from model server: {e}")
            return False
        except Exception as e:
            print(f"Error removing user: {e}")
            return False
