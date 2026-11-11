import requests
import uuid
import os

# --- 설정 ---
MODEL_SERVER_API_URL = "http://localhost:48000"  # 모델 서버 API 주소 및 포트
TEST_AUDIO_FILE = "Haerin.m4a"  # 테스트에 사용할 오디오 파일

# --- 테스트 함수 ---

def test_model_creation():
    """모델 생성 API 테스트"""
    #user_uuid = str(uuid.uuid4())
    user_uuid = "5329081"
    print(f"사용자 {user_uuid}에 대한 모델 생성 테스트 시작...")

    # 파일 업로드 (여기서는 스킵, 실제 파일 업로드 로직 필요)  


    # 모델 생성 요청
    model_data = {
        "user_uuid": user_uuid,
        "sample_rate": "40000",
        "cpu_cores": 4
    }
    response = requests.post(f"{MODEL_SERVER_API_URL}/models", json=model_data)

    # 응답 확인
    print(f"응답 상태 코드: {response.status_code}")
    print(f"응답 내용: {response.json()}")


def test_tts():
    """TTS API 테스트"""
    user_uuid = "5329081"   # 모델 생성 시 사용한 user_uuid 입력
    tts_text = "Hello, I'm Haerin."  # TTS 테스트 문장
    pitch = 12  # 테스트 pitch 값

    print(f"사용자 {user_uuid} 모델을 사용한 TTS 테스트 시작...")
    
    tts_data = {
        "user_uuid": user_uuid,
        "tts_text": tts_text,
        "pitch": pitch
    }
    response = requests.post(f"{MODEL_SERVER_API_URL}/tts", json=tts_data)

    # 응답 확인 (파일 다운로드)
    if response.status_code == 200:
        with open(f"./test_tts_{user_uuid}.wav", "wb") as f:
            f.write(response.content)
        print(f"TTS 파일이 성공적으로 저장되었습니다: ./test_tts_{user_uuid}.wav")
    else:
        print(f"TTS 요청 실패: {response.status_code}, {response.text}")


# --- 메인 실행 --- 

if __name__ == "__main__":
    test_model_creation()  # 모델 생성 테스트
    #test_tts()  # TTS 테스트 (모델 생성 후 실행) 
