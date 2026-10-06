from copy import deepcopy
from datetime import timedelta
import pytest

from services.private_message_service import PrivateMessageService
from services.private_message_policy import PrivateMessageError
from private_message_fakes import DB, NOW, SPACE, populate


@pytest.fixture
def env():
    db, sent, current = DB(), [], [NOW]
    owner, a, b, c = populate(db)
    service = PrivateMessageService(db, lambda user, body: sent.append((user, body)) or "sent",
                                    lambda: current[0])
    return service, db, sent, current, owner, a, b, c


def draft(env, actor=None, text="给乙留言，立即发送：交接订单"):
    service, _, _, _, _, a, _, _ = env
    return service.handle(SPACE, actor or a, text)


def messages(env):
    return env[1].rows.get("private_messages", [])


def test_unconfirmed_message_is_private_and_has_no_visible_code(env):
    preview = draft(env)
    assert "乙" in preview and "交接订单" in preview
    assert "确认发送" in preview
    assert messages(env)[0]["id"] not in preview
    assert "短码" not in preview
    env[0].scan(SPACE)
    assert not env[2]


def test_confirm_immediate_and_duplicate_confirm_delivers_once(env):
    service, _, sent, _, _, a, _, _ = env
    draft(env)
    service.handle(SPACE, a, "确认发送")
    service.handle(SPACE, a, "确认发送")
    service.scan(SPACE)
    assert len([body for user, body in sent if user == "B"]) == 1
    assert messages(env)[0]["status"] == "sent"
    assert "来自：甲" in [body for user, body in sent if user == "B"][0]


def test_future_message_only_delivers_when_due(env):
    service, _, sent, now, _, a, _, _ = env
    draft(env, text="10分钟后给乙留言：交接")
    service.handle(SPACE, a, "确认发送")
    service.scan(SPACE)
    assert not [body for user, body in sent if user == "B"]
    now[0] += timedelta(minutes=10)
    service.scan(SPACE)
    assert len([body for user, body in sent if user == "B"]) == 1


def test_recipient_and_owner_cannot_read_draft(env):
    service, _, _, _, owner, _, b, c = env
    draft(env)
    mid = messages(env)[0]["id"]
    for actor in (owner, b, c):
        with pytest.raises(PrivateMessageError):
            service.visible_message(SPACE, actor, mid)
    assert "交接订单" not in service.handle(SPACE, b, "我的留言")


def test_only_both_parties_can_read_delivered_message(env):
    service, _, _, _, owner, a, b, c = env
    draft(env)
    service.handle(SPACE, a, "确认发送")
    mid = messages(env)[0]["id"]
    assert service.visible_message(SPACE, b, mid)["content"] == "交接订单"
    for actor in (owner, c):
        with pytest.raises(PrivateMessageError):
            service.visible_message(SPACE, actor, mid)


def test_multi_candidate_confirm_requires_choice_and_actor_scoping(env):
    service, _, sent, _, _, a, b, _ = env
    draft(env)
    draft(env, text="给丙留言，立即发送：另一件交接")
    menu = service.handle(SPACE, a, "确认发送")
    assert "1." in menu and "2." in menu
    assert not sent
    with pytest.raises(PrivateMessageError):
        service.handle(SPACE, b, "1")
    assert not sent
    service.handle(SPACE, a, "1")
    assert len([user for user, _ in sent if user in ("B", "C")]) == 1


def test_old_menu_cannot_confirm_modified_message(env):
    service, _, sent, _, _, a, _, _ = env
    draft(env)
    draft(env, text="给丙留言，立即发送：另一件")
    service.handle(SPACE, a, "确认发送")
    row = messages(env)[0]
    service.change(row, {"content": "新正文", "version": row["version"] + 1})
    with pytest.raises(PrivateMessageError):
        service.handle(SPACE, a, "1")
    assert not sent


def test_expired_choice_is_not_reused(env):
    service, _, sent, now, _, a, _, _ = env
    draft(env); draft(env, text="给丙留言，立即发送：另一件")
    service.handle(SPACE, a, "确认发送")
    now[0] += timedelta(minutes=11)
    with pytest.raises(PrivateMessageError):
        service.handle(SPACE, a, "1")
    assert not sent


def test_modification_revokes_schedule_and_requires_new_confirmation(env):
    service, _, sent, _, _, a, _, _ = env
    draft(env, text="10分钟后给乙留言：旧正文")
    service.handle(SPACE, a, "确认发送")
    service.handle(SPACE, a, "修改留言：新正文")
    assert messages(env)[0]["status"] == "draft"
    service.scan(SPACE)
    assert not [u for u, _ in sent if u == "B"]


def test_cancelled_message_never_delivers(env):
    service, _, sent, now, _, a, _, _ = env
    draft(env, text="10分钟后给乙留言：交接")
    service.handle(SPACE, a, "确认发送")
    service.handle(SPACE, a, "取消留言")
    now[0] += timedelta(minutes=10)
    service.scan(SPACE)
    assert messages(env)[0]["status"] == "cancelled"
    assert not [u for u, _ in sent if u == "B"]


def test_acknowledgement_and_reply_preserve_two_party_thread(env):
    service, _, sent, _, _, a, b, _ = env
    draft(env)
    service.handle(SPACE, a, "确认发送")
    service.handle(SPACE, b, "留言收到")
    assert messages(env)[0]["acknowledged_at"]
    before = len(sent)
    service.handle(SPACE, b, "留言收到")
    assert len(sent) == before
    preview = service.handle(SPACE, b, "回复留言：我已处理")
    assert "甲" in preview and "我已处理" in preview
    service.handle(SPACE, b, "确认发送")
    assert len(messages(env)) == 2
    assert messages(env)[0]["thread_id"] == messages(env)[1]["thread_id"]
    assert any(u == "A" and "我已处理" in body for u, body in sent)


def test_disabled_or_excluded_participant_cannot_send(env):
    service, _, sent, _, _, a, _, _ = env
    with pytest.raises(PrivateMessageError):
        service.participant(SPACE, "SheDe")
    a["active"] = False
    with pytest.raises(PrivateMessageError):
        draft(env, a)
    assert not sent


def test_recipient_disabled_before_due_stops_delivery(env):
    service, db, sent, now, _, a, _, _ = env
    draft(env, text="10分钟后给乙留言：交接")
    service.handle(SPACE, a, "确认发送")
    next(p for p in db.rows["private_message_participants"] if p["wecom_userid"] == "B")["active"] = False
    now[0] += timedelta(minutes=10)
    service.scan(SPACE)
    assert messages(env)[0]["status"] == "failed"
    assert not [u for u, _ in sent if u == "B"]


def test_restart_recovers_confirmed_schedule_without_duplicate(env):
    service, db, sent, now, _, a, _, _ = env
    draft(env, text="10分钟后给乙留言：交接")
    service.handle(SPACE, a, "确认发送")
    now[0] += timedelta(minutes=10)
    restarted = PrivateMessageService(db, service.sender, lambda: now[0])
    restarted.scan(SPACE); restarted.scan(SPACE)
    assert len([u for u, _ in sent if u == "B"]) == 1


def test_late_schedule_is_paused_not_delivered(env):
    service, _, sent, now, _, a, _, _ = env
    draft(env, text="1分钟后给乙留言：交接")
    service.handle(SPACE, a, "确认发送")
    now[0] += timedelta(minutes=17)
    service.scan(SPACE)
    assert messages(env)[0]["status"] == "failed"
    assert messages(env)[0]["failure_code"] == "TIME_EXPIRED"
    assert not [u for u, _ in sent if u == "B"]


@pytest.mark.parametrize("outcome, expected_attempts", [("failed", 2), ("uncertain", 1)])
def test_failures_stop_without_manual_cancel(env, outcome, expected_attempts):
    service, _, sent, _, _, a, _, _ = env
    calls = []
    service.sender = lambda u, body: calls.append(u) or (outcome if u == "B" else "sent")
    draft(env)
    service.handle(SPACE, a, "确认发送")
    for _ in range(4): service.scan(SPACE)
    assert calls.count("B") == expected_attempts
    assert messages(env)[0]["status"] == outcome


def test_notice_failure_does_not_resend_body(env):
    service, _, _, _, _, a, _, _ = env
    calls = []
    service.sender = lambda u, body: calls.append(u) or ("sent" if u == "B" else "failed")
    draft(env)
    service.handle(SPACE, a, "确认发送")
    for _ in range(5): service.scan(SPACE)
    assert calls.count("B") == 1


def test_no_private_body_in_legacy_tables_or_selection_candidates(env):
    service, db, _, _, _, a, _, _ = env
    draft(env); draft(env, text="给丙留言，立即发送：第二条正文")
    service.handle(SPACE, a, "确认发送")
    assert not any(name in db.rows for name in ("tasks", "delegated_tasks", "wecom_inbound_messages", "secretary_messages"))
    candidates = db.rows["private_message_contexts"][0]["candidates"]
    assert all(set(item) == {"id", "version"} for item in candidates)

def test_large_selection_menu_fits_one_wecom_message(env):
    service, _, _, _, _, a, _, _ = env
    for n in range(20):
        draft(env, text="给乙留言，立即发送：" + "订单交接内容" * 20 + str(n))
    menu = service.handle(SPACE, a, "确认发送")
    assert len(menu.encode("utf-8")) <= 2048
    assert "20." in menu


def test_stale_observation_cannot_authorize_new_body(env):
    service, _, sent, _, _, a, _, _ = env
    draft(env)
    stale = deepcopy(messages(env)[0])
    service.change(stale, {"content": "未经确认的新正文"})
    with pytest.raises(PrivateMessageError):
        service.perform(SPACE, a, "confirm", stale, {})
    assert not sent


def test_definite_retry_after_deadline_does_not_deliver_expired_body(env):
    service, _, _, current, _, a, _, _ = env
    calls = []
    service.sender = lambda u, body: calls.append(u) or ("failed" if u == "B" else "sent")
    draft(env)
    service.handle(SPACE, a, "确认发送")
    assert calls.count("B") == 1
    current[0] += timedelta(minutes=16)
    service.scan(SPACE)
    assert calls.count("B") == 1
    assert messages(env)[0]["failure_code"] == "TIME_EXPIRED"


def test_saved_success_is_reconciled_without_repeat_delivery(monkeypatch, env):
    service, _, sent, _, _, a, _, _ = env
    draft(env)
    original = service.change
    failed = [False]
    def change(row, values):
        if values.get("status") == "sent" and not failed[0]:
            failed[0] = True
            raise RuntimeError("simulated interrupted state save")
        return original(row, values)
    monkeypatch.setattr(service, "change", change)
    with pytest.raises(RuntimeError):
        service.handle(SPACE, a, "确认发送")
    service.scan(SPACE)
    assert messages(env)[0]["status"] == "sent"
    assert len([u for u, _ in sent if u == "B"]) == 1


def test_lost_success_response_pauses_without_repeating(monkeypatch, env):
    from services import private_message_queue as queue
    service, _, sent, now, _, a, _, _ = env
    draft(env)
    original = queue._update
    interrupted = [False]
    def update(svc, row, values):
        if values.get("status") == "sent" and row["kind"] == "delivery" and not interrupted[0]:
            interrupted[0] = True
            raise RuntimeError("simulated process interruption")
        return original(svc, row, values)
    monkeypatch.setattr(queue, "_update", update)
    with pytest.raises(RuntimeError):
        service.handle(SPACE, a, "确认发送")
    now[0] += timedelta(minutes=6)
    service.scan(SPACE)
    assert messages(env)[0]["status"] == "uncertain"
    assert len([u for u, _ in sent if u == "B"]) == 1

def test_old_history_does_not_hide_new_due_message(env):
    service, db, sent, current, _, a, _, _ = env
    draft(env, text="1分钟后给乙留言：需要按时送达")
    service.handle(SPACE, a, "确认发送")
    pending = deepcopy(messages(env)[0])
    history = []
    for n in range(1000):
        item = deepcopy(pending)
        item.update(id="old-" + str(n), status="sent", created_at="2020-01-01T00:00:00+00:00")
        history.append(item)
    db.rows["private_messages"] = [*history, pending]
    current[0] += timedelta(minutes=1)
    service.scan(SPACE)
    assert len([u for u, _ in sent if u == "B"]) == 1
    assert db.rows["private_messages"][-1]["status"] == "sent"


@pytest.mark.parametrize("operation, target_status", [
    ("confirm", "draft"), ("cancel", "scheduled"),
    ("modify", "scheduled"), ("retime", "scheduled"), ("ack", "sent"),
])
def test_eligible_message_is_not_hidden_by_newer_history(env, operation, target_status):
    service, db, _, _, _, a, b, _ = env
    draft(env, text="10分钟后给乙留言：仍需处理")
    target = deepcopy(messages(env)[0])
    target["status"] = target_status
    history = []
    for n in range(100):
        item = deepcopy(target)
        item.update(id="new-" + str(n), status="sent",
                    acknowledged_at=NOW.isoformat(),
                    created_at="2026-10-06T02:01:00+00:00")
        history.append(item)
    db.rows["private_messages"] = [target, *history]
    actor = b if operation == "ack" else a
    assert target["id"] in {m["id"] for m in service.candidates(SPACE, actor, operation)}


def test_reply_keeps_older_peer_when_another_thread_has_many_new_messages(env):
    service, db, _, _, _, a, _, _ = env
    draft(env, text="给乙留言，立即发送：乙的会话")
    first = deepcopy(messages(env)[0])
    first["status"] = "sent"
    draft(env, text="给丙留言，立即发送：丙的会话")
    recent = deepcopy(messages(env)[1])
    history = []
    for n in range(100):
        item = deepcopy(recent)
        item.update(id="recent-" + str(n), status="sent",
                    created_at="2026-10-06T02:01:00+00:00")
        history.append(item)
    db.rows["private_messages"] = [first, *history]
    candidates = service.candidates(SPACE, a, "reply")
    assert len(candidates) == 2
    assert {m["recipient_id"] for m in candidates} == {first["recipient_id"], recent["recipient_id"]}
