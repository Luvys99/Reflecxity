# TTS: 내 모델 파일 찾기, 문장 → 내 목소리 음성 (edge-tts 기계 음성 → RVC로 내 목소리 변환)
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (TTS 워커 → Redis)
import os
import re
import time
import uuid

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


# 모델 파일 이름({uuid}_10e_90s.pth)에서 학습한 epoch 수를 읽는다. 없으면 0
def read_trained_epochs(pth_file_name):
    match = re.search(r"_(\d+)e_", pth_file_name)
    return int(match.group(1)) if match else 0


# 학습 결과 폴더 logs/{uuid}에서 모델 파일(.pth)과 인덱스(added_*.index) 경로를 찾는다. 없으면 FileNotFoundError
# 다시 학습하면 이전 모델 파일(예: 2 epoch)이 남아 있으므로 가장 많이 학습한 파일을 쓴다 (#65)
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

    pth_path = os.path.join(model_dir, max(pth_files, key=read_trained_epochs))
    index_path = os.path.join(
        model_dir, index_files[0]
    )  # os.path.join 사용
    return pth_path, index_path


# 문장을 내 목소리 음성으로 만들어 output_path에 저장한다 (TTS 워커용, #49)
# rvc_cli.py를 새 프로세스로 띄우지 않고 이 프로세스 안에서 한다 (예전에는 TTS마다 새 프로세스였다).
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


# TTS 워커가 작업을 받기 전에 VoiceConverter와 HuBERT를 미리 올려 둔다 (#54)
# 안 하면 첫 요청 때 import·HuBERT 불러오기를 해서 첫 요청만 약 12초 걸린다 (#49 측정)
# import_voice_converter는 lru_cache라 run_tts_script가 같은 객체를 쓴다.
# load_hubert는 무엇을 불러왔는지 기록하지 않아서, last_embedder_model까지 채워야 convert_audio가 다시 불러오지 않는다
def prepare_voice_converter():
    from rvc_cli import import_voice_converter

    embedder_model = RVC_TTS_DEFAULT_OPTIONS["embedder_model"]
    voice_converter = import_voice_converter()
    voice_converter.load_hubert(embedder_model, RVC_TTS_DEFAULT_OPTIONS["embedder_model_custom"])
    voice_converter.last_embedder_model = embedder_model
