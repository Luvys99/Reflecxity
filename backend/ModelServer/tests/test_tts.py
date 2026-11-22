# tts.py가 기계 음성을 받고(edge-tts) 내 목소리로 바꾸는(VoiceConverter) 과정을 확인한다 (#49, #76)
# 진짜 rvc_cli는 torch까지 불러와 무겁고, 진짜 edge-tts는 Microsoft 서버를 부르므로 둘 다 가짜로 바꾼다
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests
import asyncio
import os
import sys
import types

import pytest

import tts

FAKE_AUDIO = "fake-wav"


class FakeVoiceConverter:
    def __init__(self):
        self.loaded_embedders = []
        self.last_embedder_model = None
        self.calls = []
        self.write_output = True  # False면 결과 파일을 안 만든다 (convert_audio가 에러를 삼킨 경우)

    def load_hubert(self, embedder_model, embedder_model_custom=None):
        self.loaded_embedders.append((embedder_model, embedder_model_custom))

    def convert_audio(self, **options):
        self.calls.append(options)
        assert os.path.exists(options["audio_input_path"])  # 기계 음성을 받은 뒤에 부른다
        if self.write_output:
            with open(options["audio_output_path"], "w") as f:
                f.write(FAKE_AUDIO)


@pytest.fixture
def voice_converter(tmp_path, monkeypatch):
    # 가짜 rvc_cli: import_voice_converter가 가짜 VoiceConverter를 돌려준다
    monkeypatch.chdir(tmp_path)
    converter = FakeVoiceConverter()
    module = types.ModuleType("rvc_cli")
    module.import_voice_converter = lambda: converter
    monkeypatch.setitem(sys.modules, "rvc_cli", module)
    return converter


@pytest.fixture
def machine_voice(monkeypatch):
    # 가짜 edge-tts: 부를 때마다 results를 앞에서부터 하나씩 쓴다
    # None = 바로 성공, 숫자 = 그만큼(초) 걸린 뒤 성공, 예외 = 던진다. 다 쓰면 바로 성공
    state = types.SimpleNamespace(results=[], calls=0)

    async def fake_save_machine_voice(tts_text, output_path):
        result = state.results[state.calls] if state.calls < len(state.results) else None
        state.calls += 1
        if isinstance(result, Exception):
            raise result
        if result is not None:
            await asyncio.sleep(result)
        with open(output_path, "w") as f:
            f.write("machine-voice")

    monkeypatch.setattr(tts, "save_machine_voice", fake_save_machine_voice)
    monkeypatch.setattr(tts, "EDGE_TTS_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(tts, "EDGE_TTS_RETRY_WAIT_SECONDS", [0.01, 0.01])
    return state


def test_명령줄과_같은_설정값으로_변환하고_pitch는_숫자로_바꾼다(voice_converter, machine_voice):
    tts.convert_text_to_voice("user1", "Hello", "5", "model.pth", "added_model.index", "out.wav")

    options = voice_converter.calls[0]
    assert options["pitch"] == 5  # Redis에서는 글자("5")로 온다
    assert options["model_path"] == "model.pth"
    assert options["index_path"] == "added_model.index"
    assert options["audio_output_path"] == "out.wav"
    for name, value in tts.VOICE_CONVERTER_OPTIONS.items():
        assert options[name] == value


def test_성공하면_결과_파일을_남기고_기계_음성_임시_파일은_지운다(voice_converter, machine_voice):
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    with open("out.wav") as f:
        assert f.read() == FAKE_AUDIO
    assert not os.path.exists(voice_converter.calls[0]["audio_input_path"])


def test_결과_파일이_없으면_에러를_내고_임시_파일은_지운다(voice_converter, machine_voice):
    voice_converter.write_output = False

    with pytest.raises(RuntimeError):
        tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    assert not os.path.exists(voice_converter.calls[0]["audio_input_path"])


def test_요청마다_다른_기계_음성_임시_파일을_쓴다(voice_converter, machine_voice):
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out1.wav")
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out2.wav")

    assert voice_converter.calls[0]["audio_input_path"] != voice_converter.calls[1]["audio_input_path"]


def test_기계_음성이_시간_제한을_넘으면_끊고_다시_받는다(voice_converter, machine_voice):
    # 2초 걸릴 요청을 0.2초에서 끊고 다시 받는다 (실제는 4초)
    machine_voice.results = [2.0, None]

    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    assert machine_voice.calls == 2
    assert os.path.exists("out.wav")


def test_기계_음성이_소리_없이_끝나면_다시_받는다(voice_converter, machine_voice):
    machine_voice.results = [tts.edge_tts.exceptions.NoAudioReceived("No audio"), None]

    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    assert machine_voice.calls == 2


def test_기계_음성을_3번_다_못_받으면_변환하지_않고_에러를_낸다(voice_converter, machine_voice):
    machine_voice.results = [tts.edge_tts.exceptions.NoAudioReceived("No audio")] * 3

    with pytest.raises(RuntimeError, match="기계 음성 받기 실패"):
        tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    assert machine_voice.calls == 3
    assert voice_converter.calls == []
    assert os.listdir("temptts") == []  # 받다 만 임시 파일도 지운다


def test_미리_준비하면_변환에_쓸_HuBERT를_불러오고_불러온_것을_기록한다(voice_converter):
    # convert_audio는 last_embedder_model이 쓸 embedder_model과 다르면 HuBERT를 다시 불러온다 (rvc/infer/infer.py)

    tts.prepare_voice_converter()

    embedder_model = tts.VOICE_CONVERTER_OPTIONS["embedder_model"]
    assert voice_converter.loaded_embedders == [(embedder_model, tts.VOICE_CONVERTER_OPTIONS["embedder_model_custom"])]
    assert voice_converter.last_embedder_model == embedder_model


def make_model_files(tmp_path, monkeypatch, file_names):
    # logs/user1/ 아래에 빈 모델·인덱스 파일을 만든다
    monkeypatch.chdir(tmp_path)
    model_dir = tmp_path / "logs" / "user1"
    model_dir.mkdir(parents=True)
    for file_name in file_names:
        (model_dir / file_name).write_text("")


def test_다시_학습해_모델_파일이_여러_개면_가장_많이_학습한_파일을_쓴다(tmp_path, monkeypatch):
    make_model_files(tmp_path, monkeypatch, ["user1_2e_18s.pth", "user1_10e_90s.pth", "D_2333333.pth", "added_user1_v2.index"])

    pth_path, index_path = tts.find_model_files("user1")

    assert os.path.basename(pth_path) == "user1_10e_90s.pth"
    assert os.path.basename(index_path) == "added_user1_v2.index"


def test_모델_파일이_없으면_FileNotFoundError(tmp_path, monkeypatch):
    make_model_files(tmp_path, monkeypatch, ["added_user1_v2.index"])

    with pytest.raises(FileNotFoundError):
        tts.find_model_files("user1")
