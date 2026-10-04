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
    assert payloads[0]["enable_duplicate_check"] == 1

def test_timeout_is_uncertain(monkeypatch):
    def post(*_, **__): raise httpx.ReadTimeout("test")
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda **_: "test")
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")
    monkeypatch.setattr(wecom_delivery.httpx, "post", post)
    assert wecom_delivery.send_delegation_text("Colleague", "任务") == "uncertain"
