import pytest
from datetime import timedelta

from services import private_message_entry as entry
from services import wecom_app
from services.private_message_service import PrivateMessageService
from private_message_fakes import DB, NOW, SPACE, populate

REAL_DELEGATION_PENDING = entry.delegation_pending


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

def test_natural_notice_confirmed_once_sends_at_due_without_legacy(env, monkeypatch):
    service, db, sent, replies, current, _ = env
    monkeypatch.setattr(wecom_app, "handle_private_message", entry.handle_private_message)
    for name in ("handle_delegation_message", "reserve_inbound_message", "chat"):
        monkeypatch.setattr(wecom_app, name, lambda *a: pytest.fail("notice entered legacy flow"))
    text = "1分钟后给乙发消息提醒他4点下班，订单1234"
    wecom_app.handle_incoming_text("A", text, "natural1")
    wecom_app.handle_incoming_text("A", text, "natural1")
    assert len(db.rows["private_messages"]) == 1
    assert not sent
    assert "私人留言预览" in replies[-1][1]
    wecom_app.handle_incoming_text("A", "确认发送", "confirm1")
    wecom_app.handle_incoming_text("A", "确认发送", "confirm1")
    assert db.rows["private_messages"][0]["status"] == "scheduled"
    assert not sent
    current[0] += timedelta(minutes=1)
    service.scan(SPACE)
    service.scan(SPACE)
    deliveries = [body for user, body in sent if user == "B"]
    assert len(deliveries) == 1
    assert "提醒他4点下班，订单1234" in deliveries[0]
    assert all("待批准" not in body and "同意 " not in body for _, body in sent)
    assert not db.rows.get("delegated_tasks")


def test_private_menu_invalidates_only_same_actors_task_menu(env):
    service, db, _, _, _, people = env
    db.rows["delegation_command_contexts"] = [
        {"id": "old", "owner_user_id": SPACE, "actor_userid": "a", "version": 0,
         "expires_at": (NOW + timedelta(minutes=10)).isoformat()},
        {"id": "other", "owner_user_id": SPACE, "actor_userid": "b", "version": 0,
         "expires_at": (NOW + timedelta(minutes=10)).isoformat()},
    ]
    service.handle(SPACE, people[1], "立即给乙发消息：一")
    service.handle(SPACE, people[1], "立即给丙发消息：二")
    service.handle(SPACE, people[1], "确认发送")
    first, other = db.rows["delegation_command_contexts"]
    assert first["expires_at"] == NOW.isoformat()
    assert first["version"] == 1
    assert other["version"] == 0


def test_expired_private_menu_does_not_steal_new_task_menu_choice(env):
    from services.wecom_menu import expire_other_menu
    service, db, _, _, _, people = env
    service.handle(SPACE, people[1], "立即给乙发消息：一")
    service.handle(SPACE, people[1], "立即给丙发消息：二")
    service.handle(SPACE, people[1], "确认发送")
    db.rows["delegation_command_contexts"] = [{
        "id": "task-menu", "owner_user_id": SPACE, "actor_userid": "a", "version": 0,
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
    }]
    expire_other_menu(db, SPACE, "A", "delegation", NOW)
    assert not entry.handle_private_message("A", "1", "task-choice")
    assert all(m["status"] == "draft" for m in db.rows["private_messages"])


def test_ack_conflict_message_no_longer_requests_task_code(env, monkeypatch):
    service, _, _, replies, _, people = env
    service.handle(SPACE, people[1], "立即给乙发消息：正文")
    service.handle(SPACE, people[1], "确认发送")
    monkeypatch.setattr(entry, "delegation_pending", lambda *args: True)
    assert entry.handle_private_message("B", "收到", "conflict")
    assert "短码" not in replies[-1][1]
    assert "任务收到" in replies[-1][1]


@pytest.mark.parametrize("userid, enabled", [("SheDe", True), ("A", False)])
def test_natural_notice_never_falls_back_when_unavailable(env, monkeypatch, userid, enabled):
    _, db, _, _, _, _ = env
    monkeypatch.setattr(entry, "WECOM_PRIVATE_MESSAGES_ENABLED", enabled)
    assert entry.handle_private_message(userid, "1分钟后给乙发消息：正文", "unavailable")
    assert not db.rows.get("private_messages")

def test_case_insensitive_task_conflict_does_not_ack_private(env, monkeypatch):
    service, db, _, replies, _, people = env
    service.handle(SPACE, people[1], "立即给乙发消息：正文")
    service.handle(SPACE, people[1], "确认发送")
    db.rows["colleagues"] = [{
        "id": "colleague-B", "owner_user_id": SPACE, "wecom_userid": "B", "active": True,
    }]
    db.rows["delegated_tasks"] = [{
        "id": "task", "owner_user_id": SPACE, "colleague_id": "colleague-B",
        "delivery_status": "sent", "task_status": "awaiting_reply", "approval_status": "approved",
    }]
    monkeypatch.setattr(entry, "delegation_pending", REAL_DELEGATION_PENDING)
    assert entry.handle_private_message("b", "收到", "lowercase-ack")
    assert "任务收到" in replies[-1][1]
    assert not db.rows["private_messages"][0]["acknowledged_at"]


@pytest.mark.parametrize("delivery, status", [
    ("sent", "acknowledged"), ("uncertain", "not_started"), ("sending", "not_started"),
])
def test_active_formal_task_also_requires_explicit_private_ack(env, monkeypatch, delivery, status):
    service, db, _, _, _, _ = env
    db.rows["colleagues"] = [{
        "id": "c", "owner_user_id": SPACE, "wecom_userid": "B", "active": True,
    }]
    db.rows["delegated_tasks"] = [{
        "id": "task", "owner_user_id": SPACE, "colleague_id": "c", "delivery_status": delivery,
        "task_status": status, "approval_status": "approved",
    }]
    assert REAL_DELEGATION_PENDING(service, SPACE, "b")

def test_full_callback_menu_switches_cannot_confirm_wrong_business(env, monkeypatch):
    from services.delegation import DelegationService
    from services import delegation_entry as formal
    private, db, sent, replies, current, people = env
    task_service = DelegationService(
        db, lambda u, b: sent.append((u, b)) or "sent",
        lambda owner: "Owner" if owner == SPACE else None, lambda: current[0])
    colleague = task_service.save_colleague(SPACE, {"name": "乙", "wecom_userid": "B"})
    for body in ("正式任务一", "正式任务二"):
        task_service.create_task(SPACE, {
            "colleague_id": colleague["id"], "content": body, "scheduled_at": NOW.isoformat(),
        })
    task_service.scan(SPACE)
    private.handle(SPACE, people[0], "立即给甲发消息：私人一")
    private.handle(SPACE, people[0], "立即给乙发消息：私人二")
    private.handle(SPACE, people[0], "确认发送")
    monkeypatch.setattr(formal, "get_service", lambda: task_service)
    monkeypatch.setattr(formal, "WECOM_DELEGATION_ENABLED", True)
    monkeypatch.setattr(formal, "bound_user_ids", lambda: [SPACE])
    monkeypatch.setattr(formal, "resolve_supabase_user_id", lambda u: SPACE if u.lower() == "owner" else None)
    seen = set()
    def reserve(mid, *args):
        if mid in seen:
            return False
        seen.add(mid)
        return True
    monkeypatch.setattr(formal, "reserve_inbound_message", reserve)
    monkeypatch.setattr(formal, "mark_inbound_processed", lambda *args: None)
    monkeypatch.setattr(formal, "mark_inbound_failed", lambda *args: pytest.fail("callback failed"))
    monkeypatch.setattr(formal, "send_app_text", lambda u, b: replies.append((u, b)))
    monkeypatch.setattr(wecom_app, "handle_private_message", entry.handle_private_message)
    monkeypatch.setattr(wecom_app, "handle_delegation_message", formal.handle_delegation_message)
    monkeypatch.setattr(wecom_app, "chat", lambda *args: pytest.fail("menu reached AI"))
    wecom_app.handle_incoming_text("Owner", "批准任务", "open-task")
    wecom_app.handle_incoming_text("Owner", "1", "choose-task")
    tasks = db.rows["delegated_tasks"]
    assert sum(t["approval_status"] == "approved" for t in tasks) == 1
    assert all(m["status"] == "draft" for m in db.rows["private_messages"])
    wecom_app.handle_incoming_text("Owner", "确认发送", "open-private")
    wecom_app.handle_incoming_text("Owner", "1", "choose-private")
    assert sum(m["status"] == "sent" for m in db.rows["private_messages"]) == 1
    assert sum(t["approval_status"] == "approved" for t in db.rows["delegated_tasks"]) == 1
