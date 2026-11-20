# TTS: 내 모델 파일 찾기, 문장 → 내 목소리 음성 (edge-tts 기계 음성 → RVC로 내 목소리 변환)
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (main.py의 synthesize_tts_async → status.json, TTS 워커 → Redis)
import os
import sys
import time
import uuid

from fastapi import HTTPException

from command import run_command_async

TTS_VOICE = "en-US-AndrewMultilingualNeural"

# rvc_cli.py tts 명령의 기본값 (rvc_cli.py의 tts_parser). 새 프로세스로 실행하던 때와 같은 음성이 나오게 그대로 쓴다 (#49)
RVC_TTS_DEFAULT_OPTIONS = {
    "tts_file": None,
    "tts_rate": 0,
    "filter_radius": 3,
    "index_rate": 0.3,
    "volume_envelope": 1,
    "protect": 0.33,
    "hop_length": 128,
    "f0_method": "rmvpe",
    "split_audio": False,
    "f0_autotune": False,
    "f0_autotune_strength": 1.0,
    "clean_audio": False,
    "clean_strength": 0.7,
    "export_format": "WAV",
    "upscale_audio": False,
    "f0_file": None,
    "embedder_model": "contentvec",
    "embedder_model_custom": None,
}


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


# 문장을 내 목소리 음성으로 만들어 output_path에 저장한다. 결과 파일이 없으면 HTTPException(500)
# Model 서버는 user/{uuid}/convert.wav, TTS 워커는 작업마다 다른 임시 파일을 넘긴다 (#36)
async def synthesize_voice(user_uuid, tts_text, pitch, pth_path, index_path, output_path):
    # TTS 임시 파일을 저장할 폴더가 없으면 만든다 (git은 빈 폴더를 저장하지 않아 새로 받으면 없다)
    os.makedirs(os.path.join(".", "temptts"), exist_ok=True)
    # edge-tts 기계 음성 임시 파일은 요청마다 다른 이름으로 쓴다.
    # 하나를 같이 쓰면 동시 요청끼리 덮어써서 남의 문장이 내 목소리로 변환된다 (#18)
    temp_tts_path = os.path.join(".", "temptts", f"{user_uuid}_{uuid.uuid4().hex}.ogg")

    # TTS 명령어 실행
    tts_command = [
        sys.executable,
        "rvc_cli.py",
        "tts",
        "--tts_text",
        tts_text,
        "--tts_voice",
        TTS_VOICE,
        "--output_tts_path",
        temp_tts_path,
        "--output_rvc_path",
        output_path,
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
    try:
        await run_command_async(tts_command, user_uuid, "TTS")
    finally:
        # 다 쓴 임시 파일은 성공·실패와 상관없이 지운다 (쌓이지 않게)
        if os.path.exists(temp_tts_path):
            os.remove(temp_tts_path)
    # TTS 전체 시간 (프로세스 띄우기 ~ 끝, #15)
    print(f"[Model {user_uuid}] [TTS 시간] 전체 {time.perf_counter() - t_start:.2f}s")

    # 파일 존재 확인
    if not os.path.exists(output_path):
        raise HTTPException(
            status_code=500, detail="TTS wav 파일을 찾을 수 없습니다."
        )


# 문장을 내 목소리 음성으로 만들어 output_path에 저장한다 (TTS 워커용, #49)
# synthesize_voice와 같은 일을 새 프로세스 없이 이 프로세스 안에서 한다.
# rvc_cli와 VoiceConverter·HuBERT는 처음 부를 때 한 번 불러오고, 이후 요청은 다시 쓴다 (내 모델 .pth는 요청마다 읽음)
# 결과 파일이 없으면 RuntimeError (convert_audio는 에러를 출력만 하고 넘어가서, 결과 파일로 성공을 판단한다)
def convert_text_to_voice(user_uuid, tts_text, pitch, pth_path, index_path, output_path):
    from rvc_cli import run_tts_script  # torch와 rvc-cli 전체를 불러와 무겁다. 테스트에서는 불리지 않게 여기서 import

    os.makedirs(os.path.join(".", "temptts"), exist_ok=True)
    # 기계 음성 임시 파일은 요청마다 다른 이름으로 (#18)
    temp_tts_path = os.path.join(".", "temptts", f"{user_uuid}_{uuid.uuid4().hex}.ogg")

    t_start = time.perf_counter()
    try:
        run_tts_script(
            tts_text=tts_text,
            tts_voice=TTS_VOICE,
            pitch=int(pitch),
            output_tts_path=temp_tts_path,
            output_rvc_path=output_path,
            pth_path=pth_path,
            index_path=index_path,
            **RVC_TTS_DEFAULT_OPTIONS,
        )
    finally:
        if os.path.exists(temp_tts_path):
            os.remove(temp_tts_path)
    # TTS 전체 시간 (#15와 같은 이름으로 남겨 전후를 비교한다)
    print(f"[Model {user_uuid}] [TTS 시간] 전체 {time.perf_counter() - t_start:.2f}s", flush=True)

    if not os.path.exists(output_path):
        raise RuntimeError("TTS wav 파일을 찾을 수 없습니다.")
