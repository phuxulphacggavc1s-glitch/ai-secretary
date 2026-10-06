import httpx

def test_long_message_is_not_silently_truncated(monkeypatch):
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda **_: "test")
    monkeypatch.setattr(wecom_delivery.httpx, "post", lambda *a, **k: pytest.fail("must not send"))
    assert wecom_delivery.send_delegation_text("Colleague", "字" * 700) == "failed"

import pytest
from services import wecom_delivery

@pytest.mark.parametrize("body,expected", [
    ({"errcode": 0}, "sent"),
    ({"errcode": 0, "invaliduser": "Colleague"}, "failed"),
    ({"errcode": 0, "unlicenseduser": "Colleague"}, "failed"),
    ({"errcode": 81013}, "failed"),
])
def test_delegation_delivery_checks_recipient(monkeypatch, body, expected):
    class Response:
        def json(self): return body
    payloads = []
    def post(url, json, timeout):
        payloads.append(json); return Response()
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda **_: "test")
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")
    monkeypatch.setattr(wecom_delivery.httpx, "post", post)
    assert wecom_delivery.send_delegation_text("Colleague", "任务") == expected
    assert payloads[0]["enable_duplicate_check"] == 0

def test_timeout_is_uncertain(monkeypatch):
    def post(*_, **__): raise httpx.ReadTimeout("test")
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda **_: "test")
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")
    monkeypatch.setattr(wecom_delivery.httpx, "post", post)
    assert wecom_delivery.send_delegation_text("Colleague", "任务") == "uncertain"


def test_independently_confirmed_identical_text_is_not_suppressed(monkeypatch):
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda **_: "test")
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")
    accepted, seen = [], set()
    class Response:
        def json(self): return {"errcode": 0}
    def post(url, json, timeout):
        key = (json["touser"], json["text"]["content"])
        if not json.get("enable_duplicate_check") or key not in seen:
            accepted.append(key)
            seen.add(key)
        return Response()
    monkeypatch.setattr(wecom_delivery.httpx, "post", post)
    assert wecom_delivery.send_delegation_text("Colleague", "同一任务文本") == "sent"
    assert wecom_delivery.send_delegation_text("Colleague", "同一任务文本") == "sent"
    assert len(accepted) == 2
