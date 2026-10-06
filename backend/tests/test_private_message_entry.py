import pytest
from datetime import timedelta

from services import private_message_entry as entry
from services import wecom_app
from services.private_message_service import PrivateMessageService
from private_message_fakes import DB, NOW, SPACE, populate


@pytest.fixture
def env(monkeypatch):
    db, sent, replies, current = DB(), [], [], [NOW]
    people = populate(db)
    service = PrivateMessageService(db, lambda u, b: sent.append((u, b)) or "sent", lambda: current[0])
    monkeypatch.setattr(entry, "get_service", lambda: service)
    monkeypatch.setattr(entry, "bound_user_ids", lambda: [SPACE])
    monkeypatch.setattr(entry, "WECOM_PRIVATE_MESSAGES_ENABLED", True)
    monkeypatch.setattr(entry, "reply", lambda u, b: replies.append((u, b)))
    monkeypatch.setattr(entry, "delegation_pending", lambda *args: False)
    return service, db, sent, replies, current, people


def test_duplicate_callback_creates_one_draft(env):
    _, db, sent, replies, _, _ = env
    assert entry.handle_private_message("A", "给乙留言，立即发送：正文", "m1")
    assert entry.handle_private_message("A", "给乙留言，立即发送：正文", "m1")
    assert len(db.rows["private_messages"]) == 1
    assert len(replies) == 1
    assert not sent


def test_inbound_has_no_private_body(env):
    _, db, _, _, _, _ = env
    entry.handle_private_message("A", "给乙留言，立即发送：私密正文", "m1")
    row = db.rows["private_message_inbound"][0]
    assert "content" not in row
    assert "私密正文" not in str(row)


def test_unknown_and_excluded_sender_claimed_without_legacy_leak(env):
    _, db, _, replies, _, _ = env
    assert entry.handle_private_message("SheDe", "给乙留言，立即发送：正文", "m1")
    assert "未开通" in replies[-1][1]
    assert not db.rows.get("private_messages")


def test_disabled_private_requests_do_not_fall_back(monkeypatch, env):
    _, db, _, replies, _, _ = env
    monkeypatch.setattr(entry, "WECOM_PRIVATE_MESSAGES_ENABLED", False)
    assert entry.handle_private_message("A", "给乙留言，立即发送：正文", "m1")
    assert "尚未启用" in replies[-1][1]
    assert not db.rows.get("private_messages")
    assert not entry.handle_private_message("A", "收到", "m2")


def test_bare_ack_conflict_prompts_instead_of_guessing(monkeypatch, env):
    service, db, _, replies, _, people = env
    service.handle(SPACE, people[1], "给乙留言，立即发送：正文")
    service.handle(SPACE, people[1], "确认发送")
    monkeypatch.setattr(entry, "delegation_pending", lambda *args: True)
    assert entry.handle_private_message("B", "收到", "ack1")
    assert not db.rows["private_messages"][0]["acknowledged_at"]
    assert "留言收到" in replies[-1][1]
    assert entry.handle_private_message("B", "留言收到", "ack2")
    assert db.rows["private_messages"][0]["acknowledged_at"]


def test_plain_chat_and_delegation_are_not_claimed(env):
    assert not entry.handle_private_message("A", "同意 7859", "m1")
    assert not entry.handle_private_message("A", "你好", "m2")
    assert not entry.handle_private_message("A", "收到", "m3")


def test_numeric_choice_only_claimed_with_live_own_menu(env):
    service, _, _, _, current, people = env
    service.handle(SPACE, people[1], "给乙留言，立即发送：一")
    service.handle(SPACE, people[1], "给丙留言，立即发送：二")
    service.handle(SPACE, people[1], "确认发送")
    assert not entry.handle_private_message("B", "1", "m1")
    assert entry.handle_private_message("A", "1", "m2")
    current[0] += timedelta(minutes=11)
    assert not entry.handle_private_message("A", "2", "m3")


def test_private_entry_precedes_legacy_truncation(monkeypatch):
    received = []
    monkeypatch.setattr(wecom_app, "handle_private_message", lambda u, t, m: received.append(t) or True)
    monkeypatch.setattr(wecom_app, "handle_delegation_message", lambda *args: pytest.fail("private body leaked"))
    monkeypatch.setattr(wecom_app, "reserve_inbound_message", lambda *args: pytest.fail("private body leaked"))
    monkeypatch.setattr(wecom_app, "chat", lambda *args: pytest.fail("private body leaked"))
    text = "给乙留言，立即发送：" + "字" * 600
    wecom_app.handle_incoming_text("A", text, "m1")
    assert received == [text]


def test_disabled_scheduler_does_not_touch_database(monkeypatch, env):
    monkeypatch.setattr(entry, "WECOM_PRIVATE_MESSAGES_ENABLED", False)
    monkeypatch.setattr(entry, "get_service", lambda: pytest.fail("disabled scheduler touched private database"))
    entry.scan_private_messages()


def test_ambiguous_space_is_denied(env, monkeypatch):
    service, _, _, replies, _, _ = env
    monkeypatch.setattr(entry, "bound_user_ids", lambda: [SPACE, SPACE])
    assert entry.handle_private_message("A", "给乙留言，立即发送：正文", "m1")
    assert "唯一确定" in replies[-1][1]
