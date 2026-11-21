# 공개할 때의 보호 장치를 확인한다 (#103): 요청 수 제한, 앱 전용 문구
# 바깥 서버(Google, Model 서버)는 가짜로 바꾼다. Redis는 테스트용 DB 15번 (conftest.py)
import pytest

import main
from rate_limit import client_ip


class FakeOkResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"translations": [{"translatedText": "Hello"}]}, "file_path": "./user/x/raw/voice"}


@pytest.fixture
def fake_outside(monkeypatch):
    # Google 번역과 Model 서버 업로드를 부른 횟수를 센다
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return FakeOkResponse()

    monkeypatch.setattr(main, "GOOGLE_TRANSLATE_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    return calls


def translate(api, **headers):
    return api.post("/translations", json={"text": "안녕", "target": "en"}, headers=headers)


def upload(api, user_uuid):
    return api.post(f"/users/{user_uuid}/recordings", files={"file": ("voice.m4a", b"fake-audio")})


def test_IP별_횟수를_넘으면_429와_기다릴_시간을_주고_Google을_부르지_않는다(api, fake_outside, monkeypatch):
    monkeypatch.setitem(main.RATE_LIMITS, "translation", (2, 60))

    assert translate(api).status_code == 200
    assert translate(api).status_code == 200
    response = translate(api)

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert len(fake_outside) == 2


def test_바깥에서_꾸민_X_Forwarded_For로는_제한을_피할_수_없다(api, fake_outside, monkeypatch):
    # 테스트 클라이언트는 127.0.0.1이 아니라서 헤더를 믿지 않는다 → 같은 사람으로 센다
    monkeypatch.setitem(main.RATE_LIMITS, "translation", (2, 60))

    translate(api, **{"X-Forwarded-For": "1.1.1.1"})
    translate(api, **{"X-Forwarded-For": "2.2.2.2"})

    assert translate(api, **{"X-Forwarded-For": "3.3.3.3"}).status_code == 429


def test_사용자별_제한은_다른_사용자에게_영향이_없다(api, fake_outside, monkeypatch):
    monkeypatch.setitem(main.RATE_LIMITS, "upload", (2, 3600))

    upload(api, "userA")
    upload(api, "userA")

    assert upload(api, "userA").status_code == 429
    assert upload(api, "userB").status_code == 200


class FakeRequest:
    def __init__(self, host, forwarded_for=None):
        self.client = type("Client", (), {"host": host})()
        self.headers = {"x-forwarded-for": forwarded_for} if forwarded_for else {}


def test_Tailscale을_거친_요청만_X_Forwarded_For의_IP를_쓴다():
    # Funnel → 이 Mac의 Tailscale(127.0.0.1) → Main. 진짜 IP는 헤더의 첫 번째 값
    assert client_ip(FakeRequest("127.0.0.1", "203.0.113.7, 100.64.0.1")) == "203.0.113.7"
    assert client_ip(FakeRequest("127.0.0.1")) == "127.0.0.1"  # 에뮬레이터 → Mac은 헤더 없음
    assert client_ip(FakeRequest("192.168.0.9", "203.0.113.7")) == "192.168.0.9"  # 바깥에서 꾸민 헤더


def test_앱_키가_설정되면_맞는_키가_있는_요청만_받는다(api, monkeypatch):
    monkeypatch.setattr(main, "APP_KEY", "secret")

    assert api.get("/").status_code == 401
    assert api.get("/", headers={"X-App-Key": "wrong"}).status_code == 401
    assert api.get("/", headers={"X-App-Key": "secret"}).status_code == 200


def test_앱_키가_틀린_요청은_요청_수에_세지_않는다(api, fake_outside, monkeypatch):
    # 앱 키 검사가 먼저라서, 키 없는 봇이 진짜 사용자의 횟수를 깎지 못한다
    monkeypatch.setattr(main, "APP_KEY", "secret")
    monkeypatch.setitem(main.RATE_LIMITS, "translation", (1, 60))

    assert translate(api).status_code == 401
    assert translate(api, **{"X-App-Key": "secret"}).status_code == 200


def test_앱_키가_없으면_개발용으로_검사하지_않는다(api):
    assert api.get("/").status_code == 200
