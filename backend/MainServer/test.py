import requests
import uuid
import os
import json  # json 모듈 추가
import time

# --- 설정 ---
MAIN_SERVER_API_URL = "http://localhost:28300"  # 메인 서버 API 주소 및 포트
MODEL_SERVER_API_URL = "http://localhost:48000"  # 모델 서버 API 주소
TEST_AUDIO_FILE = "bani.m4a"  # 테스트에 사용할 오디오 파일 (메인 서버에 위치)

# --- 테스트 함수 ---

def test_user_creation():
    """사용자 생성 API 테스트"""
    print("사용자 생성 테스트 시작...")
    response = requests.post(f"{MAIN_SERVER_API_URL}/user")

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")
    return response.json()['uuid']  # UUID 반환

def test_file_upload(user_uuid: str, filename: str = TEST_AUDIO_FILE):
    """파일 업로드 API 테스트"""
    print(f"사용자 {user_uuid} 파일 업로드 테스트 시작...")

    # 파일 읽기 (메인 서버의 haerin.ogg 파일을 읽음)
    with open(filename, "rb") as f:
        file_data = f.read()

    # 업로드 요청
    files = {"file": (filename, file_data, "audio/m4a")}
    response = requests.post(
        f"{MAIN_SERVER_API_URL}/user/{user_uuid}/upload", files=files
    )

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_get_user_files(user_uuid: str):
    """사용자 파일 목록 조회 API 테스트"""
    print(f"사용자 {user_uuid} 파일 목록 조회 테스트 시작...")
    response = requests.get(f"{MAIN_SERVER_API_URL}/user/{user_uuid}/files")

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_create_user_model(user_uuid: str):
    """모델 생성 API 테스트 (메인 서버를 통해 모델 서버로 요청)"""
    print(f"사용자 {user_uuid} 모델 생성 테스트 시작...")

    model_data = {
        "user_uuid": user_uuid,
        "sample_rate": "40000",
        "cpu_cores": 4,
    }
    response = requests.post(
        f"{MAIN_SERVER_API_URL}/user/{user_uuid}/models", json=model_data
    )

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_synthesize_tts(user_uuid: str):
    """TTS API 테스트 (메인 서버를 통해 모델 서버로 요청)"""
    print(f"사용자 {user_uuid} 모델을 사용한 TTS 테스트 시작...")
    tts_text = "Tonight, I want to speak with you about our nation's unprecedented response to the coronavirus outbreak that started in China and is now spreading throughout the world. Today, the World Health Organization officially announced that this is a global pandemic. We have been in frequent contact with our allies, and we are marshalling the full power of the federal government and the private sector to protect the American people. This is the most aggressive and comprehensive effort to confront a foreign virus in modern history.I am confident that by counting and continuing to take these tough measures, we will significantly reduce the threat to our citizens, and we will ultimately and expeditiously defeat this virus. From the beginning of time, nations and people have faced unforeseen challenges, including large-scale and very dangerous health threats.This is the way it always was and always will be.It only matters how you respond, and we are responding with great speed and professionalism."  # TTS 테스트 문장
    pitch = 5  # 테스트 pitch 값

    tts_data = {"user_uuid": user_uuid, "tts_text": tts_text, "pitch": pitch} 
    print(tts_data)
    response = requests.post(
        f"{MAIN_SERVER_API_URL}/user/{user_uuid}/tts", data=tts_data 
    )

    # 응답 확인 (파일 다운로드)
    if response.status_code == 200:
        with open(f"./test_tts_{user_uuid}.wav", "wb") as f:
            f.write(response.content)
        print(
            f"TTS 파일이 성공적으로 저장되었습니다: ./test_tts_{user_uuid}.wav"
        )
    else:
        print(f"TTS 요청 실패: {response.status_code}, {response.text}")

def test_delete_user(user_uuid: str):
    """사용자 삭제 API 테스트"""
    print(f"사용자 {user_uuid} 삭제 테스트 시작...")
    response = requests.delete(f"{MAIN_SERVER_API_URL}/user/{user_uuid}")

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_delete_file(user_uuid: str, filename: str = TEST_AUDIO_FILE):
    """파일 삭제 API 테스트"""
    print(f"사용자 {user_uuid} 파일 삭제 테스트 시작...")
    response = requests.delete(
        f"{MAIN_SERVER_API_URL}/user/{user_uuid}/raw/{filename}"
    )

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_download_file(user_uuid: str, filename: str = TEST_AUDIO_FILE):
    """파일 다운로드 API 테스트"""
    print(f"사용자 {user_uuid} 파일 다운로드 테스트 시작...")
    response = requests.get(f"{MAIN_SERVER_API_URL}/user/{user_uuid}/raw/{filename}")

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")

    if response.status_code == 200:
        with open(f"./download_{filename}", "wb") as f:
            f.write(response.content)
        print(f"파일이 성공적으로 다운로드되었습니다: ./download_{filename}")
    else:
        print(f"파일 다운로드 실패: {response.status_code}, {response.text}")

def test_model_check(user_uuid: str):
    """모델 파일 존재 여부 확인 API 테스트"""
    print(f"사용자 {user_uuid} 모델 파일 존재 여부 확인 테스트 시작...")

    while True:  # 무한 루프로 변경 (시간 제한 없음)
        response = requests.get(f"{MAIN_SERVER_API_URL}/user/{user_uuid}/modelcheck")

        if response.status_code == 200:
            # 모델 파일이 존재하는 경우
            print(f"응답 상태 코드: {response.status_code}")
            print(f"응답 내용: {response.json()}")
            if response.json()['message'] == "모델 파일 존재":
                print("모델 파일이 존재합니다.")
                return False  # 모델 파일 존재 확인 후 루프 종료
            else:
                print("모델 파일이 존재하지 않습니다.")
                time.sleep(1)  # 1초 대기

        else:
            # 모델 파일이 존재하지 않는 경우
            print(f"응답 상태 코드: {response.status_code}")
            print(f"응답 내용: {response.json()}")
            time.sleep(1)  # 1초 대기
            

def test_queue_status():
    """대기열 상태 조회 API 테스트"""
    print("대기열 상태 조회 API 테스트 시작...")
    response = requests.get(f"{MAIN_SERVER_API_URL}/queue_status")

    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

def test_user_queue_info(user_uuid: str):
    """사용자 대기열 정보 조회 API 테스트"""
    print(f"사용자 {user_uuid} 대기열 정보 조회 API 테스트 시작...")
    response = requests.get(f"{MAIN_SERVER_API_URL}/user/{user_uuid}/queue")

    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")

# --- 메인 실행 ---

def test_check_online():
    """서버 온라인 상태 확인 API 테스트"""
    print("서버 온라인 상태 확인 API 테스트 시작...")
    response = requests.get(f"{MAIN_SERVER_API_URL}/online")

if __name__ == "__main__":
    # 12. 서버 온라인 상태 확인
    test_check_online()
    
    # 1. 사용자 생성
    user_uuid = test_user_creation()
    #user_uuid = "e74e5e26-cd40-427b-bf9a-7eff9f8a9a83"
    #user_uuid = "7fb1f418-bf3b-4f2e-a24b-00c12928955f"
    #user_uuid = "bddc6025-7c7c-439f-8a9f-e3a27c59b5ee"
    #user_uuid = "3c615bfe-8e4f-48e9-bc1c-a2fe27944d8c"
    print(user_uuid)

    # 2. 파일 업로드 (m4a 파일 추가)
    test_file_upload(user_uuid, filename="김영서 10분 녹음.m4a")  # m4a 파일 업로드 테스트
    #test_file_upload(user_uuid, filename="김영서 10분 녹음2.m4a")

    # 3. 사용자 파일 목록 조회
    #test_get_user_files(user_uuid)

    # 4. 모델 생성
    test_create_user_model(user_uuid)

    # 10. 대기열 상태 조회
    #test_queue_status()

    # 11. 사용자 대기열 정보 조회
    #test_user_queue_info(user_uuid)
    
    # 5. 모델 파일 존재 여부 확인
    #print("모델 생성 완료될 때까지 잠시 대기...")
    #if test_model_check(user_uuid):
    #    print("모델 생성 완료.")
    #else:
    #    print("모델 생성 실패.")

    # 6. TTS 테스트
    #test_synthesize_tts(user_uuid)

    # 7. 파일 다운로드
    #test_download_file(user_uuid)

    # 8. 파일 삭제 (모델 생성 후 파일 삭제)
    #test_delete_file(user_uuid)

    # 9. 사용자 삭제
    #test_delete_user(user_uuid)
