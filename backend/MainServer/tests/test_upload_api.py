# 앱이 부르는 녹음 업로드 API가 녹음 형식만 받는지 확인한다 (#60)
# 허용: 학습이 녹음으로 읽는 m4a, ogg, wav. 그 밖은 400이고 Model 서버로 보내지 않는다
# Model 서버는 가짜로 바꾼다 (requests.post)
import pytest

import main


class FakeModelServerResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"file_path": "./user/userA/raw/voice"}


@pytest.fixture
def sent_files(monkeypatch):
    # Model 서버로 보낸 파일 이름을 모은다
    sent_file_names = []

    def fake_post(url, files):
        sent_file_names.append(files["file"][0])
        return FakeModelServerResponse()

    monkeypatch.setattr(main.requests, "post", fake_post)
    return sent_file_names


def upload(api, filename):
    return api.post("/user/userA/upload", files={"file": (filename, b"fake-audio")})


@pytest.mark.parametrize("filename", ["voice.m4a", "voice.ogg", "voice.wav", "VOICE.M4A"])
def test_녹음_형식은_Model_서버로_보낸다(api, sent_files, filename):
    response = upload(api, filename)

    assert response.status_code == 200
    assert sent_files == [filename]


@pytest.mark.parametrize("filename", ["notes.txt", "report.pdf", "photo.png", "photo.jpg", "backup.zip", "voice"])
def test_녹음이_아닌_형식은_400이고_Model_서버로_보내지_않는다(api, sent_files, filename):
    response = upload(api, filename)

    assert response.status_code == 400
    assert sent_files == []
