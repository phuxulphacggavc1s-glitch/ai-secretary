import xml.etree.ElementTree as ET

from routers import wecom
from services import wecom_app


def test_duplicate_message_stops_before_chat(monkeypatch):
    monkeypatch.setattr(wecom_app, "resolve_supabase_user_id", lambda _wid: "user-1")
    monkeypatch.setattr(wecom_app, "reserve_inbound_message", lambda *_args: False)
    monkeypatch.setattr(
        wecom_app,
        "chat",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not chat")),
    )

    wecom_app.handle_incoming_text("User", "完成了", "msg-1")


def test_task_reply_sends_processor_response_and_skips_chat(monkeypatch):
    sent = []
    processed = []
    monkeypatch.setattr(wecom_app, "resolve_supabase_user_id", lambda _wid: "user-1")
    monkeypatch.setattr(wecom_app, "reserve_inbound_message", lambda *_args: True)
    monkeypatch.setattr(
        wecom_app,
        "process_pending_task_reply",
        lambda _uid, _text: {"handled": True, "reply": "收到，已标记完成。"},
    )
    monkeypatch.setattr(wecom_app, "send_app_text", lambda _wid, content: sent.append(content) or True)
    monkeypatch.setattr(
        wecom_app,
        "mark_inbound_processed",
        lambda msg_id, user_id: processed.append((msg_id, user_id)),
    )
    monkeypatch.setattr(
        wecom_app,
        "chat",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not chat")),
    )

    wecom_app.handle_incoming_text("User", "完成了", "msg-1")

    assert sent == ["收到，已标记完成。"]
    assert processed == [("msg-1", "user-1")]


def test_message_id_uses_native_id_or_stable_fallback():
    with_id = ET.fromstring("<xml><MsgId>123</MsgId></xml>")
    without_id = ET.fromstring("<xml><CreateTime>456</CreateTime></xml>")

    assert wecom._message_id(with_id, "User", "完成了") == "123"
    assert wecom._message_id(without_id, "User", "完成了") == wecom._message_id(
        without_id, "User", "完成了"
    )
