# TTS: 내 모델 파일 찾기, rvc_cli.py tts 실행 (edge-tts 기계 음성 → RVC로 내 목소리 변환)
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (main.py의 synthesize_tts_async → status.json)
import os
import sys
import time

from fastapi import HTTPException

from command import run_command_async


# 학습 결과 폴더 logs/{uuid}에서 모델 파일(.pth)과 인덱스(added_*.index) 경로를 찾는다. 없으면 FileNotFoundError
def find_model_files(user_uuid):
    model_dir = os.path.join(
        ".", "logs", user_uuid
    )  # os.path.join 사용

    pth_files = [
        f for f in os.listdir(model_dir) if f.endswith(".pth") and user_uuid in f  
    
    ]  # user_uuid가 포함된 파일만 추가

    index_files = [
        f
        for f in os.listdir(model_dir)
        if f.startswith("added_") and f.endswith(".index")
    ]

    if not pth_files:
        raise FileNotFoundError(f"No .pth file found in {model_dir}")
    if not index_files:
        raise FileNotFoundError(
            f"No 'added_*.index' file found in {model_dir}"
        )

    pth_path = os.path.join(
        model_dir, pth_files[0]
    )  # os.path.join 사용
    index_path = os.path.join(
        model_dir, index_files[0]
    )  # os.path.join 사용
    return pth_path, index_path


# 문장을 내 목소리 음성으로 만들어 user/{uuid}/convert.wav에 저장한다. 결과 파일이 없으면 HTTPException(500)
async def synthesize_voice(user_uuid, tts_text, pitch, pth_path, index_path):
    # TTS 임시 파일을 저장할 폴더가 없으면 만든다 (git은 빈 폴더를 저장하지 않아 새로 받으면 없다)
    os.makedirs(os.path.join(".", "temptts"), exist_ok=True)

    # TTS 명령어 실행
    tts_command = [
        sys.executable,
        "rvc_cli.py",
        "tts",
        "--tts_text",
        tts_text,
        "--tts_voice",
        "en-US-AndrewMultilingualNeural",
        "--output_tts_path",
        os.path.join(".", "temptts", "temp.ogg"),  # os.path.join 사용
        "--output_rvc_path",
        os.path.join(
            ".", "user", user_uuid, "convert.wav"
        ),  # os.path.join 사용
        "--pth_path",
        pth_path,
        "--index_path",
        index_path,
        "--export_format",
        "WAV",
        "--pitch",
        str(pitch)
    ]
    '''
    # pitch.txt 파일에서 피치 값 읽기
    pitch_file_path = os.path.join(".", "logs", user_uuid, "pitch.txt")
    if os.path.exists(pitch_file_path):
        with open(pitch_file_path, "r") as f:
            pitch = int(f.read())  # 읽은 피치 값을 정수형으로 변환
        print(f"pitch.txt에서 피치 값 {pitch}를 읽었습니다.")
        tts_command.extend(["--pitch", str(pitch)])  # tts_command에 pitch 값 추가
    else:
        print(f"pitch.txt 파일이 존재하지 않습니다. 기본 피치 값을 사용합니다.")
    '''
    t_start = time.perf_counter()
    await run_command_async(tts_command, user_uuid, "TTS")
    # TTS 전체 시간 (프로세스 띄우기 ~ 끝, #15)
    print(f"[Model {user_uuid}] [TTS 시간] 전체 {time.perf_counter() - t_start:.2f}s")

    # convert.m4a 파일 경로
    output_m4a_path = os.path.join(
        ".", "user", user_uuid, "convert.wav"
    )  # os.path.join 사용

    # 파일 존재 확인
    if not os.path.exists(output_m4a_path):
        raise HTTPException(
            status_code=500, detail="TTS wav 파일을 찾을 수 없습니다."
        )
