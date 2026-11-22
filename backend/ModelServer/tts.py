# TTS: 내 모델 파일 찾기, 문장 → 내 목소리 음성 (edge-tts 기계 음성 → RVC로 내 목소리 변환)
# 결과(성공 / 실패) 기록은 부르는 쪽이 한다 (TTS 워커 → Redis)
import asyncio
import os
import re
import time
import uuid

import edge_tts

TTS_VOICE = "en-US-AndrewMultilingualNeural"
# 이 기계 음성의 평균 목소리 높이(F0, Hz). 자동 피치의 기준값 (#59, auto_pitch.py)
# 영어 문장 12개의 중앙값. 문장마다 102~146Hz로 다르다(질문은 끝을 올려 높다). 억양은 그대로 두고 평균 높이만 맞춘다
# 이 음성은 피치 0으로 변환한 결과가 기계 음성 높이와 거의 같았다. 다른 음성으로 바꾸면 실제 변환 결과로 다시 맞춘다
# (ko-KR-InJoonNeural은 잰 값 142Hz인데 피치 0 변환 결과가 156Hz로 어긋났다)
TTS_VOICE_F0_HZ = 120

# 기계 음성(edge-tts, Microsoft 서버) 받기 (#76). 보통 1초 안에 오지만 가끔 4~14초 걸리거나 소리 없이 끝난다(NoAudioReceived)
# 오래 기다리기보다 끊고 다시 받는 게 빠르다: 4초 넘으면 끊고, 쉬었다가 다시 (처음 1번 + 다시 2번)
EDGE_TTS_TIMEOUT_SECONDS = 4
EDGE_TTS_RETRY_WAIT_SECONDS = [0.5, 1.0]

# 내 목소리 변환(VoiceConverter.convert_audio) 설정값. rvc_cli.py run_tts_script가 넘기던 값 그대로 (명령줄 tts 기본값, #49)
# 기계 음성을 직접 받게 되면서(#76) run_tts_script 대신 convert_audio를 바로 부른다
VOICE_CONVERTER_OPTIONS = {
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
    "sid": 0,
    # run_tts_script가 None으로 넘기던 후처리 옵션들 (안 씀)
    "formant_shifting": None,
    "formant_qfrency": None,
    "formant_timbre": None,
    "post_process": None,
    "reverb": None,
    "pitch_shift": None,
    "limiter": None,
    "gain": None,
    "distortion": None,
    "chorus": None,
    "bitcrush": None,
    "clipping": None,
    "compressor": None,
    "delay": None,
    "sliders": None,
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


async def save_machine_voice(tts_text, output_path):
    await edge_tts.Communicate(tts_text, TTS_VOICE).save(output_path)


# 기계 음성을 받아 output_path에 저장한다. 시간 제한을 넘거나 실패하면 쉬었다가 다시 받는다 (#76)
# 다 실패하면 RuntimeError (TTS 워커가 작업 전체를 다시 시도한다). 몇 번째에 받았는지 돌려준다
def create_machine_voice(user_uuid, tts_text, output_path):
    waits = [0, *EDGE_TTS_RETRY_WAIT_SECONDS]
    last_error = None
    for attempt, wait_seconds in enumerate(waits, start=1):
        time.sleep(wait_seconds)
        try:
            asyncio.run(asyncio.wait_for(save_machine_voice(tts_text, output_path), EDGE_TTS_TIMEOUT_SECONDS))
            return attempt
        except Exception as e:  # 시간 초과, NoAudioReceived, 네트워크 에러 모두 다시 받으면 될 수 있다
            last_error = e
            print(f"[Model {user_uuid}] 기계 음성 받기 실패 ({attempt}/{len(waits)}): {type(e).__name__} {e}", flush=True)
    raise RuntimeError(f"기계 음성 받기 실패 ({len(waits)}번): {type(last_error).__name__} {last_error}")


# 문장을 내 목소리 음성으로 만들어 output_path에 저장한다 (TTS 워커용, #49)
# 기계 음성은 이 프로세스에서 직접 받고(#76), 내 목소리 변환은 rvc_cli의 VoiceConverter로 한다
# (rvc_cli의 run_tts_script는 기계 음성을 새 프로세스로 받고 시간 제한이 없어서 쓰지 않는다. rvc_cli는 고치지 않는다)
# VoiceConverter·HuBERT는 처음 부를 때 한 번 불러오고, 이후 요청은 다시 쓴다 (내 모델 .pth는 요청마다 읽음)
# 결과 파일이 없으면 RuntimeError (convert_audio는 에러를 출력만 하고 넘어가서, 결과 파일로 성공을 판단한다)
def convert_text_to_voice(user_uuid, tts_text, pitch, pth_path, index_path, output_path):
    from rvc_cli import import_voice_converter  # torch와 rvc-cli 전체를 불러와 무겁다. 테스트에서는 불리지 않게 여기서 import

    os.makedirs(os.path.join(".", "temptts"), exist_ok=True)
    # 기계 음성 임시 파일은 요청마다 다른 이름으로 (#18)
    temp_tts_path = os.path.join(".", "temptts", f"{user_uuid}_{uuid.uuid4().hex}.ogg")

    t_start = time.perf_counter()
    try:
        attempt = create_machine_voice(user_uuid, tts_text, temp_tts_path)
        t_machine_voice = time.perf_counter()
        import_voice_converter().convert_audio(
            audio_input_path=temp_tts_path,
            audio_output_path=output_path,
            model_path=pth_path,
            index_path=index_path,
            pitch=int(pitch),
            **VOICE_CONVERTER_OPTIONS,
        )
    finally:
        if os.path.exists(temp_tts_path):
            os.remove(temp_tts_path)
    t_end = time.perf_counter()
    # 구간별 시간 (#15와 같은 이름으로 남겨 전후를 비교한다)
    print(f"[Model {user_uuid}] [TTS 시간] edge-tts {t_machine_voice - t_start:.2f}s ({attempt}번째), "
          f"convert_audio {t_end - t_machine_voice:.2f}s, 전체 {t_end - t_start:.2f}s", flush=True)

    if not os.path.exists(output_path):
        raise RuntimeError("TTS wav 파일을 찾을 수 없습니다.")


# TTS 워커가 작업을 받기 전에 VoiceConverter와 HuBERT를 미리 올려 둔다 (#54)
# 안 하면 첫 요청 때 import·HuBERT 불러오기를 해서 첫 요청만 약 12초 걸린다 (#49 측정)
# import_voice_converter는 lru_cache라 convert_text_to_voice가 같은 객체를 쓴다.
# load_hubert는 무엇을 불러왔는지 기록하지 않아서, last_embedder_model까지 채워야 convert_audio가 다시 불러오지 않는다
def prepare_voice_converter():
    from rvc_cli import import_voice_converter

    embedder_model = VOICE_CONVERTER_OPTIONS["embedder_model"]
    voice_converter = import_voice_converter()
    voice_converter.load_hubert(embedder_model, VOICE_CONVERTER_OPTIONS["embedder_model_custom"])
    voice_converter.last_embedder_model = embedder_model
