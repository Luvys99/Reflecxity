# 학습 파이프라인(training.py) 중 학습 없이 확인할 수 있는 부분을 확인한다
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests
import asyncio

import numpy as np
import soundfile as sf

import training


def write_tone(path, frequency_hz, seconds=1.0, sample_rate=44100):
    times = np.arange(int(seconds * sample_rate)) / sample_rate
    sf.write(path, 0.5 * np.sin(2 * np.pi * frequency_hz * times), sample_rate)


def energy_ratio_above(audio, sample_rate, frequency_hz):
    power = np.abs(np.fft.rfft(audio)) ** 2
    frequencies = np.fft.rfftfreq(len(audio), 1 / sample_rate)
    return power[frequencies > frequency_hz].sum() / power.sum()


def test_녹음_여러_개를_원래_음질_그대로_합친다(tmp_path):
    # 앱 녹음(44,100Hz)에 15kHz 소리를 넣는다. 22,050Hz로 합치면 11kHz 위가 잘려 사라진다 (#74)
    write_tone(tmp_path / "1.wav", 15000)
    write_tone(tmp_path / "2.wav", 15000)

    combined_path = asyncio.run(training.combine_audio("test-user", str(tmp_path), ["1.wav", "2.wav"]))

    combined_audio, sample_rate = sf.read(combined_path)
    assert sample_rate == 44100
    assert len(combined_audio) == 2 * 44100
    assert energy_ratio_above(combined_audio, sample_rate, 11000) > 0.99


def test_샘플레이트가_다른_녹음은_첫_녹음에_맞춰_합친다(tmp_path):
    write_tone(tmp_path / "1.wav", 440, sample_rate=44100)
    write_tone(tmp_path / "2.wav", 440, sample_rate=48000)

    combined_path = asyncio.run(training.combine_audio("test-user", str(tmp_path), ["1.wav", "2.wav"]))

    combined_audio, sample_rate = sf.read(combined_path)
    assert sample_rate == 44100
    assert len(combined_audio) == 2 * 44100
