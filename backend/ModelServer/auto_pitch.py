# 자동 피치: 녹음의 목소리 높이(F0)와 기계 음성 높이의 차이를 반음 단위로 계산해, TTS가 내 목소리 높이로 나오게 한다 (#59)
# 학습 끝에 한 번 재서 모델 옆(logs/{uuid}/auto_pitch.txt)에 저장하고, TTS 워커가 요청에 pitch가 없을 때 읽는다
import math
import os

from tts import TTS_VOICE_F0_HZ

MEASURE_SECONDS = 60  # 녹음 앞부분만 잰다 (10분 녹음도 몇 초 안에 끝나게)
MIN_VOICE_F0_HZ = 70  # 사람 목소리 범위 밖이면 잘못 잰 것으로 본다
MAX_VOICE_F0_HZ = 400
MIN_VOICED_RATIO = 0.2  # 목소리로 잡힌 구간이 이보다 적으면 잡음이 많은 녹음으로 본다
MAX_PITCH = 12  # 한 옥타브


def auto_pitch_path(user_uuid):
    return os.path.join("logs", user_uuid, "auto_pitch.txt")


# 녹음의 F0 중앙값(Hz). 목소리 구간이 너무 적거나 사람 목소리 범위 밖이면 None
def measure_voice_f0_hz(audio_path):
    import librosa  # 무거워서 TTS 워커(read_auto_pitch만 씀)는 불러오지 않게 여기서 import
    import numpy as np

    samples, sample_rate = librosa.load(audio_path, sr=16000, duration=MEASURE_SECONDS)
    f0, voiced, _ = librosa.pyin(samples, fmin=60, fmax=450, sr=sample_rate, frame_length=1024)
    if voiced.mean() < MIN_VOICED_RATIO:
        return None
    voice_f0_hz = float(np.median(f0[voiced]))
    if not MIN_VOICE_F0_HZ <= voice_f0_hz <= MAX_VOICE_F0_HZ:
        return None
    return voice_f0_hz


# 기계 음성을 내 목소리 높이로 옮기려면 몇 반음 올려야(+) / 내려야(-) 하는지
def calculate_auto_pitch(voice_f0_hz):
    pitch = round(12 * math.log2(voice_f0_hz / TTS_VOICE_F0_HZ))
    return max(-MAX_PITCH, min(MAX_PITCH, pitch))


# 녹음 폴더의 첫 녹음으로 자동 피치를 재서 저장한다. 잴 수 없으면 이전 값도 지운다 (TTS는 기본값을 쓴다)
# 돌려주는 값: (F0 Hz, 피치) / 잴 수 없으면 (None, None)
def save_auto_pitch(user_uuid, dataset_path):
    path = auto_pitch_path(user_uuid)
    voice_files = sorted(f for f in os.listdir(dataset_path) if f.endswith((".ogg", ".wav", ".m4a")))
    voice_f0_hz = measure_voice_f0_hz(os.path.join(dataset_path, voice_files[0])) if voice_files else None
    if voice_f0_hz is None:
        if os.path.exists(path):
            os.remove(path)
        return None, None
    pitch = calculate_auto_pitch(voice_f0_hz)
    with open(path, "w") as f:
        f.write(str(pitch))
    return voice_f0_hz, pitch


# 저장한 자동 피치. 없으면 None
def read_auto_pitch(user_uuid):
    path = auto_pitch_path(user_uuid)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return int(f.read().strip())
