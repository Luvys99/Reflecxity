import json
import os
import threading

class StatusManager:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.lock = threading.Lock()  # 멀티쓰레드 환경에서 상태 파일 접근 동시성 문제 방지

    def get_status(self, user_uuid: str):
        status_file = os.path.join(self.base_dir, "user", user_uuid, "status.json")

        try:
            with open(status_file, "r") as f:
                status = json.load(f)
        except FileNotFoundError:
            status = {"tts": "idle"}  # 파일이 없으면 기본 상태 설정

        return status

    def update_status(self, user_uuid: str, task: str, value: str):
        status_file = os.path.join(self.base_dir, "user", user_uuid, "status.json")

        with self.lock:  # 상태 파일 동시 접근 시 잠금 설정
            try:
                with open(status_file, "r") as f:
                    status = json.load(f)
            except FileNotFoundError:
                status = {"tts": "idle"}

            status[task] = value
            with open(status_file, "w") as f:
                json.dump(status, f)

