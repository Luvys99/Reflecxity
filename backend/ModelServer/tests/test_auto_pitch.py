# 자동 피치(auto_pitch.py)의 계산·안전장치·저장을 확인한다 (#59)
# 녹음은 일정한 높이의 사인파로 흉내 낸다 (librosa로 실제로 잰다)
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests
import numpy as np
import pytest
import soundfile as sf

import auto_pitch
from tts import TTS_VOICE_F0_HZ


def write_tone(path, f0_hz, seconds=3.0, sample_rate=16000):
    times = np.arange(int(seconds * sample_rate)) / sample_rate
    sf.write(path, 0.5 * np.sin(2 * np.pi * f0_hz * times), sample_rate)


@pytest.mark.parametrize("voice_f0_hz, expected_pitch", [
    (TTS_VOICE_F0_HZ, 0),       # 기계 음성과 같은 높이
    (TTS_VOICE_F0_HZ * 2, 12),  # 한 옥타브 위
    (122, 1),                   # 측정한 남자 녹음 (#59 댓글)
    (232, 12),                  # 높은 여자 목소리
    (500, 12),                  # 한 옥타브보다 크면 12로 제한
    (40, -12),
])
def test_기계_음성과의_차이를_반음으로_계산하고_한_옥타브로_제한한다(voice_f0_hz, expected_pitch):
    assert auto_pitch.calculate_auto_pitch(voice_f0_hz) == expected_pitch


def test_녹음_높이를_잰다(tmp_path):
    write_tone(tmp_path / "voice.wav", 200)

    assert auto_pitch.measure_voice_f0_hz(str(tmp_path / "voice.wav")) == pytest.approx(200, rel=0.03)


def test_목소리가_없는_녹음은_잴_수_없다(tmp_path):
    sf.write(tmp_path / "silence.wav", np.zeros(16000 * 3), 16000)

    assert auto_pitch.measure_voice_f0_hz(str(tmp_path / "silence.wav")) is None


@pytest.fixture
def user_folders(tmp_path, monkeypatch):
    # logs/user1/ (모델 옆, 자동 피치 저장 위치)와 user/user1/raw/ (녹음)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs" / "user1").mkdir(parents=True)
    dataset_path = tmp_path / "user" / "user1" / "raw"
    dataset_path.mkdir(parents=True)
    return dataset_path


def test_학습_끝에_잰_자동_피치를_저장하고_읽는다(user_folders):
    write_tone(user_folders / "voice.wav", TTS_VOICE_F0_HZ * 2)

    voice_f0_hz, pitch = auto_pitch.save_auto_pitch("user1", str(user_folders))

    assert pitch == 12
    assert auto_pitch.read_auto_pitch("user1") == 12


def test_잴_수_없으면_저장하지_않고_이전_값도_지운다(user_folders):
    # 다시 학습했는데 이번 녹음은 잴 수 없음 → 예전 녹음의 값을 계속 쓰면 안 된다
    (user_folders.parent.parent.parent / "logs" / "user1" / "auto_pitch.txt").write_text("5")
    sf.write(user_folders / "noise.wav", np.zeros(16000 * 3), 16000)

    assert auto_pitch.save_auto_pitch("user1", str(user_folders)) == (None, None)
    assert auto_pitch.read_auto_pitch("user1") is None
