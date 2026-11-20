# tts.py의 convert_text_to_voice가 rvc_cli의 run_tts_script를 어떻게 부르는지 확인한다 (#49)
# 진짜 rvc_cli는 torch까지 불러와 무거우므로 가짜 모듈로 바꾼다
# 실행: cd backend/ModelServer && .venv/bin/python -m pytest tests
import os
import sys
import types

import pytest

import tts

FAKE_AUDIO = "fake-wav"


@pytest.fixture
def fake_rvc_cli(tmp_path, monkeypatch):
    # 가짜 rvc_cli: run_tts_script를 부른 인자를 기록하고, 기계 음성·결과 파일을 만든다
    # write_output=False로 바꾸면 결과 파일을 안 만든다 (convert_audio가 에러를 삼킨 경우)
    monkeypatch.chdir(tmp_path)
    module = types.ModuleType("rvc_cli")
    module.calls = []
    module.write_output = True

    def fake_run_tts_script(**options):
        module.calls.append(options)
        with open(options["output_tts_path"], "w") as f:
            f.write("machine-voice")
        if module.write_output:
            with open(options["output_rvc_path"], "w") as f:
                f.write(FAKE_AUDIO)

    module.run_tts_script = fake_run_tts_script
    monkeypatch.setitem(sys.modules, "rvc_cli", module)
    return module


def test_명령줄과_같은_설정값으로_부르고_pitch는_숫자로_바꾼다(fake_rvc_cli):
    tts.convert_text_to_voice("user1", "Hello", "5", "model.pth", "added_model.index", "out.wav")

    options = fake_rvc_cli.calls[0]
    assert options["tts_text"] == "Hello"
    assert options["tts_voice"] == tts.TTS_VOICE
    assert options["pitch"] == 5  # Redis에서는 글자("5")로 온다
    assert options["pth_path"] == "model.pth"
    assert options["index_path"] == "added_model.index"
    assert options["output_rvc_path"] == "out.wav"
    for name, value in tts.RVC_TTS_DEFAULT_OPTIONS.items():
        assert options[name] == value


def test_성공하면_결과_파일을_남기고_기계_음성_임시_파일은_지운다(fake_rvc_cli):
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    with open("out.wav") as f:
        assert f.read() == FAKE_AUDIO
    assert not os.path.exists(fake_rvc_cli.calls[0]["output_tts_path"])


def test_결과_파일이_없으면_에러를_내고_임시_파일은_지운다(fake_rvc_cli):
    fake_rvc_cli.write_output = False

    with pytest.raises(RuntimeError):
        tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out.wav")

    assert not os.path.exists(fake_rvc_cli.calls[0]["output_tts_path"])


def test_요청마다_다른_기계_음성_임시_파일을_쓴다(fake_rvc_cli):
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out1.wav")
    tts.convert_text_to_voice("user1", "Hello", 3, "model.pth", "added_model.index", "out2.wav")

    assert fake_rvc_cli.calls[0]["output_tts_path"] != fake_rvc_cli.calls[1]["output_tts_path"]


class FakeVoiceConverter:
    def __init__(self):
        self.loaded_embedders = []
        self.last_embedder_model = None

    def load_hubert(self, embedder_model, embedder_model_custom=None):
        self.loaded_embedders.append((embedder_model, embedder_model_custom))


def test_미리_준비하면_변환에_쓸_HuBERT를_불러오고_불러온_것을_기록한다(fake_rvc_cli):
    # convert_audio는 last_embedder_model이 쓸 embedder_model과 다르면 HuBERT를 다시 불러온다 (rvc/infer/infer.py)
    voice_converter = FakeVoiceConverter()
    fake_rvc_cli.import_voice_converter = lambda: voice_converter

    tts.prepare_voice_converter()

    embedder_model = tts.RVC_TTS_DEFAULT_OPTIONS["embedder_model"]
    assert voice_converter.loaded_embedders == [(embedder_model, tts.RVC_TTS_DEFAULT_OPTIONS["embedder_model_custom"])]
    assert voice_converter.last_embedder_model == embedder_model
