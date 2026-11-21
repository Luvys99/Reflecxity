# 앱이 부르는 번역 API가 Google 번역을 대신 부르고, 키는 서버만 가지는지 확인한다 (#102)
# 하루 글자 수 상한을 넘으면 Google을 부르지 않는지도 확인한다 (#105)
# Google은 가짜로 바꾼다 (requests.post). Redis는 테스트용 DB 15번 (conftest.py)
import pytest
import requests

import main
import translation_limit


class FakeGoogleResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Error")

    def json(self):
        return self.body


@pytest.fixture
def google(monkeypatch):
    # Google로 보낸 요청을 모으고, 돌려줄 응답을 정할 수 있게 한다
    calls = []
    state = {"response": FakeGoogleResponse(body={"data": {"translations": [{"translatedText": "Hello"}]}})}

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json})
        return state["response"]

    monkeypatch.setattr(main, "GOOGLE_TRANSLATE_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    return {"calls": calls, "state": state}


def translate(api, text="안녕하세요", target="en"):
    return api.post("/translations", json={"text": text, "target": target})


def test_번역하면_Google_결과를_돌려준다(api, google):
    response = translate(api)

    assert response.status_code == 200
    assert response.json() == {"translated_text": "Hello"}
    sent = google["calls"][0]
    assert sent["json"] == {"q": "안녕하세요", "target": "en", "format": "text"}


def test_키는_주소가_아니라_헤더로_보낸다(api, google):
    translate(api)

    sent = google["calls"][0]
    assert sent["headers"] == {"X-Goog-Api-Key": "test-key"}
    assert "test-key" not in sent["url"]


def test_빈_문장은_400이고_Google을_부르지_않는다(api, google):
    response = translate(api, text="   ")

    assert response.status_code == 400
    assert google["calls"] == []


def test_키가_없으면_503(api, google, monkeypatch):
    monkeypatch.setattr(main, "GOOGLE_TRANSLATE_API_KEY", None)

    response = translate(api)

    assert response.status_code == 503
    assert google["calls"] == []


@pytest.mark.parametrize("fake_response", [
    FakeGoogleResponse(status_code=403),  # 키가 틀렸거나 막힘
    FakeGoogleResponse(body={"error": "unexpected"}),  # 모양이 다른 응답
])
def test_Google이_실패하면_502이고_키를_돌려주지_않는다(api, google, fake_response):
    google["state"]["response"] = fake_response

    response = translate(api)

    assert response.status_code == 502
    assert "test-key" not in response.text


def used_today(test_redis):
    return int(test_redis.get(translation_limit.daily_chars_key()) or 0)


def test_번역한_글자_수를_오늘_날짜로_센다(api, google, test_redis):
    translate(api, text="안녕하세요")  # 5자
    translate(api, text="반가워요")  # 4자

    assert used_today(test_redis) == 9
    # 하루 단위 기록이라 영원히 남지 않는다
    assert 0 < test_redis.ttl(translation_limit.daily_chars_key()) <= translation_limit.KEY_TTL_SECONDS


def test_하루_상한을_넘으면_429이고_Google을_부르지_않는다(api, google, test_redis, monkeypatch):
    monkeypatch.setattr(main, "TRANSLATE_DAILY_CHAR_LIMIT", 10)
    assert translate(api, text="안녕하세요").status_code == 200  # 5자, 합계 5

    response = translate(api, text="만나서 반가워요")  # 8자, 합계 13 > 10

    assert response.status_code == 429
    assert len(google["calls"]) == 1
    assert used_today(test_redis) == 5  # 거절한 글자는 세지 않는다


def test_상한까지는_번역한다(api, google, test_redis, monkeypatch):
    monkeypatch.setattr(main, "TRANSLATE_DAILY_CHAR_LIMIT", 10)

    assert translate(api, text="안녕하세요").status_code == 200
    assert translate(api, text="반가워요요").status_code == 200  # 합계 정확히 10

    assert used_today(test_redis) == 10


def test_Google이_실패하면_센_글자를_되돌린다(api, google, test_redis):
    google["state"]["response"] = FakeGoogleResponse(status_code=500)

    translate(api, text="안녕하세요")

    assert used_today(test_redis) == 0
