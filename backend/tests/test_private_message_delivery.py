from dataclasses import FrozenInstanceError
from unittest.mock import Mock, call

import httpx
import pytest

from services import private_message_delivery as module
from services import wecom_delivery


PRIVATE_TEXT = "private-body-marker"
TOKEN = "secret-token-marker"
SECRET = "corp-secret-marker"
USERID = "Recipient"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Unexpected network call")

    monkeypatch.setattr(module.httpx, "get", blocked)
    monkeypatch.setattr(module.httpx, "post", blocked)
    monkeypatch.setattr(wecom_delivery, "WECOM_CORP_ID", "test-corp")
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_SECRET", SECRET)
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")
    monkeypatch.setattr(wecom_delivery, "get_access_token", Mock(return_value=TOKEN))


def response(body, status=200):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


def test_result_is_frozen_and_has_only_safe_fields():
    result = module.DeliveryResult("sent")
    assert result.error_code is None
    assert vars(result) == {"status": "sent", "error_code": None}
    with pytest.raises(FrozenInstanceError):
        result.status = "failed"


@pytest.mark.parametrize("content", [PRIVATE_TEXT, "\u5b57" * 682 + "ab"])
def test_success_preserves_body_and_uses_official_single_recipient_payload(monkeypatch, content):
    post = Mock(return_value=response({"errcode": 0, "msgid": "not-returned"}))
    monkeypatch.setattr(module.httpx, "post", post)

    assert module.send_private_text(USERID, content) == module.DeliveryResult("sent")
    wecom_delivery.get_access_token.assert_called_once_with()
    post.assert_called_once()
    assert post.call_args.args == (f"{wecom_delivery.QYAPI}/message/send",)
    assert post.call_args.kwargs == {
        "params": {"access_token": TOKEN},
        "json": {
            "touser": USERID,
            "msgtype": "text",
            "agentid": 1000005,
            "text": {"content": content},
            "enable_duplicate_check": 0,
        },
        "timeout": 10,
    }


@pytest.mark.parametrize("userid", [None, 42, "", " ", "@all", "@ALL", "A|B", "A,B", " A", "A\n", "A/B", "\u540c\u4e8b", "a" * 65])
def test_invalid_recipient_fails_before_token_or_send(userid):
    assert module.send_private_text(userid, PRIVATE_TEXT) == module.DeliveryResult("failed", "INVALID_USERID")
    wecom_delivery.get_access_token.assert_not_called()


@pytest.mark.parametrize("agent_id", [None, "", "0", "-1", "1.5", "abc", True, 1.5, "1|2"])
def test_invalid_agent_id_fails_before_token_or_send(monkeypatch, agent_id):
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", agent_id)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("failed", "INVALID_AGENT_ID")
    wecom_delivery.get_access_token.assert_not_called()


@pytest.mark.parametrize("field", ["WECOM_CORP_ID", "WECOM_APP_SECRET"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_missing_credentials_fail_before_token_or_send(monkeypatch, field, value):
    monkeypatch.setattr(wecom_delivery, field, value)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("failed", "NOT_CONFIGURED")
    wecom_delivery.get_access_token.assert_not_called()


@pytest.mark.parametrize("content", [None, 42, "", " ", "\ud800"])
def test_invalid_body_fails_before_token_or_send(content):
    assert module.send_private_text(USERID, content) == module.DeliveryResult("failed", "INVALID_CONTENT")
    wecom_delivery.get_access_token.assert_not_called()


@pytest.mark.parametrize("content", ["x" * 2049, "\u5b57" * 683])
def test_utf8_length_limit_rejects_without_truncation(content):
    assert module.send_private_text(USERID, content) == module.DeliveryResult("failed", "CONTENT_TOO_LONG")
    wecom_delivery.get_access_token.assert_not_called()


@pytest.mark.parametrize("token", [None, "", " ", 42])
def test_missing_token_fails_without_sending(monkeypatch, token):
    monkeypatch.setattr(wecom_delivery, "get_access_token", Mock(return_value=token))
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("failed", "TOKEN_UNAVAILABLE")


@pytest.mark.parametrize("exception,status,code", [
    (httpx.ConnectError, "failed", "CONNECT_ERROR"),
    (httpx.ConnectTimeout, "failed", "CONNECT_TIMEOUT"),
    (httpx.ReadTimeout, "uncertain", "READ_TIMEOUT"),
    (httpx.WriteTimeout, "uncertain", "WRITE_TIMEOUT"),
    (httpx.ReadError, "uncertain", "REQUEST_ERROR"),
    (httpx.WriteError, "uncertain", "REQUEST_ERROR"),
    (httpx.PoolTimeout, "uncertain", "REQUEST_ERROR"),
    (httpx.RemoteProtocolError, "uncertain", "REQUEST_ERROR"),
    (RuntimeError, "uncertain", "REQUEST_ERROR"),
])
def test_request_exceptions_are_classified_without_retry_or_leaks(monkeypatch, caplog, capsys, exception, status, code):
    post = Mock(side_effect=exception(f"{TOKEN} {SECRET} {PRIVATE_TEXT} https://example.invalid"))
    monkeypatch.setattr(module.httpx, "post", post)
    result = module.send_private_text(USERID, PRIVATE_TEXT)
    assert result == module.DeliveryResult(status, code)
    post.assert_called_once()
    wecom_delivery.get_access_token.assert_called_once_with()
    output = caplog.text + capsys.readouterr().out + repr(result)
    assert code in caplog.text
    for sensitive in (TOKEN, SECRET, PRIVATE_TEXT, USERID, "https://"):
        assert sensitive not in output


@pytest.mark.parametrize("status,expected", [(400, "failed"), (401, "failed"), (403, "failed"), (429, "failed"), (500, "uncertain"), (503, "uncertain"), (201, "uncertain"), (302, "uncertain")])
def test_http_status_takes_precedence_over_body_and_never_retries(monkeypatch, status, expected):
    reply = response({"errcode": 42001}, status=status)
    post = Mock(return_value=reply)
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult(expected, f"HTTP_{status}")
    reply.json.assert_not_called()
    post.assert_called_once()
    wecom_delivery.get_access_token.assert_called_once_with()


@pytest.mark.parametrize("body", [None, [], "raw-private-body", {}, {"errcode": None}, {"errcode": "0"}, {"errcode": False}, {"errcode": SECRET}, {"errcode": 0, "invaliduser": []}, {"errcode": 0, "unlicenseduser": 1}])
def test_malformed_or_unknown_result_is_uncertain(monkeypatch, body):
    post = Mock(return_value=response(body))
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("uncertain", "INVALID_RESPONSE")
    post.assert_called_once()


def test_invalid_json_is_uncertain_without_retry(monkeypatch):
    reply = response(None)
    reply.json.side_effect = ValueError(PRIVATE_TEXT + TOKEN)
    post = Mock(return_value=reply)
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("uncertain", "INVALID_RESPONSE")
    post.assert_called_once()


@pytest.mark.parametrize("body,code", [
    ({"errcode": 81013, "errmsg": PRIVATE_TEXT + TOKEN}, "WECOM_81013"),
    ({"errcode": -1}, "WECOM_-1"),
    ({"errcode": 0, "invaliduser": USERID}, "INVALID_USER"),
    ({"errcode": 0, "unlicenseduser": USERID}, "UNLICENSED_USER"),
])
def test_official_rejection_is_safe_definite_failure_without_retry(monkeypatch, caplog, body, code):
    post = Mock(return_value=response(body))
    monkeypatch.setattr(module.httpx, "post", post)
    result = module.send_private_text(USERID, PRIVATE_TEXT)
    assert result == module.DeliveryResult("failed", code)
    assert code in caplog.text
    assert PRIVATE_TEXT not in caplog.text
    assert TOKEN not in caplog.text
    assert USERID not in caplog.text
    post.assert_called_once()


@pytest.mark.parametrize("errcode", [40014, 42001])
@pytest.mark.parametrize("second,expected", [
    ({"errcode": 0}, module.DeliveryResult("sent")),
    ({"errcode": 42001}, module.DeliveryResult("failed", "WECOM_42001")),
    ({"errcode": 81013}, module.DeliveryResult("failed", "WECOM_81013")),
])
def test_expired_token_refreshes_only_once_after_explicit_rejection(monkeypatch, errcode, second, expected):
    token = Mock(side_effect=[TOKEN, "refreshed-token"])
    post = Mock(side_effect=[response({"errcode": errcode}), response(second)])
    monkeypatch.setattr(wecom_delivery, "get_access_token", token)
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == expected
    assert token.call_args_list == [call(), call(force_refresh=True)]
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"] == post.call_args_list[1].kwargs["json"]
    assert post.call_args_list[1].kwargs["params"] == {"access_token": "refreshed-token"}


def test_timeout_after_refresh_is_uncertain_and_stops(monkeypatch):
    token = Mock(side_effect=[TOKEN, "refreshed-token"])
    post = Mock(side_effect=[response({"errcode": 42001}), httpx.ReadTimeout(TOKEN)])
    monkeypatch.setattr(wecom_delivery, "get_access_token", token)
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("uncertain", "READ_TIMEOUT")
    assert post.call_count == 2
    assert token.call_count == 2


def test_refresh_failure_does_not_send_again(monkeypatch):
    monkeypatch.setattr(wecom_delivery, "get_access_token", Mock(side_effect=[TOKEN, None]))
    post = Mock(return_value=response({"errcode": 42001}))
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("failed", "TOKEN_UNAVAILABLE")
    post.assert_called_once()


def test_token_exception_fails_without_leaking(monkeypatch, caplog):
    monkeypatch.setattr(wecom_delivery, "get_access_token", Mock(side_effect=RuntimeError(TOKEN + PRIVATE_TEXT)))
    assert module.send_private_text(USERID, PRIVATE_TEXT) == module.DeliveryResult("failed", "TOKEN_ERROR")
    assert TOKEN not in caplog.text
    assert PRIVATE_TEXT not in caplog.text


def test_shared_token_fetch_exception_is_sanitized(monkeypatch, capsys):
    real_get_token = Mock(side_effect=httpx.ConnectError(f"https://example.invalid?corpsecret={SECRET}"))
    monkeypatch.setattr(module.httpx, "get", real_get_token)
    assert _original_get_access_token(force_refresh=True) is None
    output = capsys.readouterr().out
    assert "TOKEN_REQUEST_FAILED" in output
    assert SECRET not in output
    assert "https://" not in output


def test_shared_token_fetch_error_code_is_sanitized(monkeypatch, capsys):
    monkeypatch.setattr(module.httpx, "get", Mock(return_value=response({"errcode": SECRET, "errmsg": PRIVATE_TEXT})))
    assert _original_get_access_token(force_refresh=True) is None
    output = capsys.readouterr().out
    assert "INVALID_RESPONSE" in output
    assert SECRET not in output
    assert PRIVATE_TEXT not in output


_original_get_access_token = wecom_delivery.get_access_token

def test_two_legitimate_identical_messages_are_not_suppressed(monkeypatch):
    accepted, seen = [], set()
    def post(*args, **kwargs):
        payload = kwargs["json"]
        content = payload["text"]["content"]
        key = (payload["touser"], content)
        if not payload.get("enable_duplicate_check", 0) or key not in seen:
            accepted.append(content)
            seen.add(key)
        return response({"errcode": 0})
    monkeypatch.setattr(module.httpx, "post", post)
    assert module.send_private_text(USERID, PRIVATE_TEXT).status == "sent"
    assert module.send_private_text(USERID, PRIVATE_TEXT).status == "sent"
    assert len(accepted) == 2
