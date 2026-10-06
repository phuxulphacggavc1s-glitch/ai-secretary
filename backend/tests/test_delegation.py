from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from services.delegation import DelegationService, DelegationError




def test_second_followup_recovery_still_notifies_owner(env):
    service, db, sent, current, _ = env
    task = create(env)
    service.scan("u1")
    service.action("u1", task["id"], "approve")
    current[0] += timedelta(minutes=30)
    service.scan("u1")
    current[0] += timedelta(hours=1)
    service.scan("u1")
    db.rows["delegation_outbox"] = [r for r in db.rows["delegation_outbox"]
                                    if not r["operation_key"].endswith(":notice:unresponsive")]
    followup = next(r for r in db.rows["delegation_outbox"]
                    if r["kind"] == "followup" and r["operation_key"].endswith(":2"))
    followup["applied"] = False
    before = len(sent)
    service.drain("u1")
    service.drain("u1")
    assert len([text for _, text in sent[before:] if "委派未回复" in text]) == 1


def test_old_approval_failure_cannot_pause_modified_task(env):
    service, _, sent, _, _ = env
    task = create(env)
    modified = [False]
    def sender(recipient, text):
        sent.append((recipient, text))
        if not modified[0]:
            modified[0] = True
            service.action("u1", task["id"], "modify", "新内容")
            return "uncertain"
        return "sent"
    service.sender = sender
    service.scan("u1")
    result = service.get_task("u1", task["id"])
    assert result["content"] == "新内容"
    assert result["approval_requested_at"] is not None
    assert result["paused_reason"] is None
def test_reply_while_followup_fails_is_preserved(env):
    service, _, sent, current, _ = env
    task = create(env)
    service.scan("u1")
    service.action("u1", task["id"], "approve")
    def sender(recipient, text):
        sent.append((recipient, text))
        if recipient == "ZhangSan":
            service.colleague_reply("u1", "ZhangSan", "任务收到", "followup-reply")
            return "uncertain"
        return "sent"
    service.sender = sender
    current[0] += timedelta(minutes=30)
    service.scan("u1")
    result = service.get_task("u1", task["id"])
    assert result["task_status"] == "acknowledged"
    assert result["paused_reason"] is None
    assert result["next_followup_at"] is None

def test_reply_while_delivery_is_finishing_is_preserved(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1")
    def sender(recipient, text):
        sent.append((recipient,text))
        if recipient == "ZhangSan":
            service.colleague_reply("u1", "ZhangSan", "任务收到", "early-reply")
        return "sent"
    service.sender = sender
    service.action("u1", task["id"], "approve")
    result = service.get_task("u1", task["id"])
    assert result["task_status"] == "acknowledged"
    assert result["next_followup_at"] is None

def test_explicit_task_reply_resolves_uncertain_delivery(env):
    service, _, _, _, _ = env
    task = create(env); service.scan("u1")
    service.sender = lambda recipient,text: "uncertain" if recipient == "ZhangSan" else "sent"
    service.action("u1", task["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "任务完成", "proof-of-receipt")
    result = service.get_task("u1", task["id"])
    assert result["delivery_status"] == "sent"
    assert result["task_status"] == "completed"

def test_long_task_is_rejected_before_saving(env):
    service, _, _, _, colleague = env
    with pytest.raises(DelegationError):
        service.create_task("u1", {"colleague_id":colleague["id"], "content":"字" * 401,
                                  "scheduled_at":NOW.isoformat()})


def test_disabled_service_never_drains_saved_outbox(env):
    service, _, sent, _, _ = env
    task = create(env); service.scan("u1")
    service.sender = None
    before = len(sent)
    service.action("u1", task["id"], "modify", "修改后的内容")
    service.scan("u1")
    assert len(sent) == before

def test_old_code_cannot_approve_modified_content(env):
    service, db, sent, _, _ = env
    task = create(env)
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.scan("u1")
    changed = service.action("u1", task["id"], "modify", "新内容")
    assert changed["approval_code"] is None
    service.owner_command("u1", "同意 7859")
    assert not [x for x in sent if x[0] == "ZhangSan"]

def test_colleague_delay_updates_deadline(monkeypatch, env):
    from services import delegation_parser
    service, _, _, _, _ = env
    task = create(env); service.scan("u1"); service.action("u1", task["id"], "approve")
    due = NOW + timedelta(days=1)
    monkeypatch.setattr(delegation_parser, "parse_delay", lambda _: due)
    service.colleague_reply("u1", "ZhangSan", "延期到明天上午")
    task = service.get_task("u1", task["id"])
    assert task["task_status"] == "delayed"
    assert task["due_at"] == due.isoformat()
    assert task["next_followup_at"] is None

def test_recovery_after_task_update_still_notifies_owner(env):
    service, db, sent, current, _ = env
    task = create(env); service.scan("u1"); service.action("u1", task["id"], "approve")
    db.rows["delegation_outbox"] = [r for r in db.rows["delegation_outbox"] if r["kind"] != "notice"]
    dispatch = next(r for r in db.rows["delegation_outbox"] if r["kind"] == "dispatch")
    dispatch["applied"] = False
    before = len(sent)
    service.drain("u1"); service.drain("u1")
    assert any("已下达" in text for _, text in sent[before:])

def test_disabled_colleague_cancels_pending_delivery(env):
    service, _, sent, current, colleague = env
    task = create(env); service.scan("u1")
    service.sender = None
    service.action("u1", task["id"], "approve")
    service.save_colleague("u1", {"active":False}, colleague["id"])
    service.sender = lambda recipient,text: sent.append((recipient,text)) or "sent"
    service.scan("u1")
    assert not [x for x in sent if x[0] == "ZhangSan"]
NOW = datetime(2026, 10, 4, 1, tzinfo=timezone.utc)

class Query:
    def __init__(self, db, table):
        self.db, self.name, self.filters = db, table, []
        self.mode, self.payload, self.cap = "select", None, 1000
    def select(self, *_): return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def order(self, *_, **__): return self
    def limit(self, n): self.cap = n; return self
    def range(self, start, end): self.start, self.cap = start, end - start + 1; return self
    def insert(self, data): self.mode, self.payload = "insert", data; return self
    def update(self, data): self.mode, self.payload = "update", data; return self
    def execute(self):
        rows = self.db.rows.setdefault(self.name, [])
        if self.mode == "insert":
            row = deepcopy(self.payload)
            if self.name == "delegation_outbox" and any(r["operation_key"] == row["operation_key"] for r in rows):
                raise ValueError("duplicate")
            if self.name == "delegation_command_contexts" and any(
                    r["owner_user_id"] == row["owner_user_id"] and r["actor_userid"] == row["actor_userid"] for r in rows):
                raise ValueError("duplicate context")
            row.setdefault("id", str(len(rows) + 1))
            rows.append(row)
            return SimpleNamespace(data=[deepcopy(row)])
        scope = "space_id" if self.name.startswith("private_message") else "owner_user_id"
        assert any(k == scope for k, _ in self.filters), "scope filter missing"
        matches = [r for r in rows if all(r.get(k) == v for k, v in self.filters)]
        matches = matches[getattr(self, "start", 0):getattr(self, "start", 0)+self.cap]
        if self.mode == "update":
            for row in matches: row.update(deepcopy(self.payload))
        return SimpleNamespace(data=deepcopy(matches))

class DB:
    def __init__(self): self.rows = {}
    def table(self, name): return Query(self, name)

@pytest.fixture
def env():
    db, sent, current = DB(), [], [NOW]
    def send(recipient, text):
        sent.append((recipient, text))
        return "sent"
    service = DelegationService(db, send, lambda _: "Owner", lambda: current[0])
    colleague = service.save_colleague("u1", {"name": "张三", "wecom_userid": "ZhangSan"})
    return service, db, sent, current, colleague

def create(env):
    service, _, _, _, colleague = env
    return service.create_task("u1", {"colleague_id": colleague["id"], "content": "整理数据",
        "scheduled_at": NOW.isoformat(), "due_at": None})

def test_scheduled_task_only_requests_owner_approval(env):
    service, db, sent, _, _ = env
    task = create(env)
    service.scan("u1")
    assert [x[0] for x in sent] == ["Owner"]
    assert service.get_task("u1", task["id"])["approval_status"] == "pending_approval"

def test_repeated_approval_sends_once(env):
    service, _, sent, _, _ = env
    task = create(env)
    service.scan("u1")
    service.action("u1", task["id"], "approve")
    service.action("u1", task["id"], "approve")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 1
    assert service.get_task("u1", task["id"])["delivery_status"] == "sent"

def test_cannot_approve_before_scheduled_time(env):
    service, _, sent, current, _ = env
    current[0] -= timedelta(minutes=1)
    task = create(env)
    with pytest.raises(DelegationError): service.action("u1", task["id"], "approve")
    assert sent == []

def test_bare_approval_is_ambiguous_with_two_pending(env):
    service, _, sent, _, _ = env
    create(env); create(env); service.scan("u1")
    result = service.owner_command("u1", "同意")
    assert "1." in result and "2." in result and "短码" not in result
    assert not [x for x in sent if x[0] == "ZhangSan"]

def test_modified_task_requires_fresh_approval(env):
    service, _, sent, _, _ = env
    task = create(env); service.scan("u1")
    service.action("u1", task["id"], "modify", "新的内容")
    assert not [x for x in sent if x[0] == "ZhangSan"]
    service.action("u1", task["id"], "approve")
    assert "新的内容" in [x[1] for x in sent if x[0] == "ZhangSan"][0]

def test_reply_cancels_future_followups(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1"); service.action("u1", task["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "收到")
    current[0] += timedelta(hours=2); service.scan("u1")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 1
    assert service.get_task("u1", task["id"])["task_status"] == "acknowledged"

def test_two_followups_then_pause_even_next_day(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1"); service.action("u1", task["id"], "approve")
    current[0] += timedelta(minutes=30); service.scan("u1"); service.scan("u1")
    current[0] += timedelta(minutes=59); service.scan("u1")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 2
    current[0] += timedelta(minutes=1); service.scan("u1")
    current[0] += timedelta(days=1); service.scan("u1")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 3
    assert service.get_task("u1", task["id"])["task_status"] == "unresponsive"

def test_foreign_owner_and_foreign_colleague_cannot_change_task(env):
    service, _, sent, _, _ = env
    task = create(env)
    with pytest.raises(DelegationError): service.get_task("u2", task["id"])
    assert service.colleague_reply("u1", "Other", "完成") is None
    assert service.get_task("u1", task["id"])["task_status"] == "not_started"

def test_expired_approval_never_dispatches(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1")
    current[0] += timedelta(hours=24); service.scan("u1")
    with pytest.raises(DelegationError): service.action("u1", task["id"], "approve")
    assert not [x for x in sent if x[0] == "ZhangSan"]

def test_unknown_delivery_result_is_not_retried(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1")
    def uncertain(recipient, text):
        sent.append((recipient, text)); return "uncertain" if recipient == "ZhangSan" else "sent"
    service.sender = uncertain
    service.action("u1", task["id"], "approve")
    current[0] += timedelta(minutes=10); service.scan("u1")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 1
    assert service.get_task("u1", task["id"])["delivery_status"] == "uncertain"

def test_definite_failure_retries_once(env):
    service, _, sent, current, _ = env
    task = create(env); service.scan("u1")
    def failed(recipient, text):
        sent.append((recipient, text)); return "failed" if recipient == "ZhangSan" else "sent"
    service.sender = failed
    service.action("u1", task["id"], "approve")
    current[0] += timedelta(minutes=1); service.scan("u1")
    current[0] += timedelta(minutes=1); service.scan("u1")
    assert len([x for x in sent if x[0] == "ZhangSan"]) == 2
    assert service.get_task("u1", task["id"])["delivery_status"] == "failed"

def test_stale_sending_after_restart_pauses_without_resend(env):
    service, db, sent, current, _ = env
    task = create(env); service.scan("u1")
    db.rows["delegation_outbox"].append({"id": "stale", "owner_user_id": "u1", "task_id": task["id"],
        "operation_key": "dispatch:stale", "recipient_userid": "ZhangSan", "content": "task",
        "kind": "dispatch", "status": "sending", "attempts": 1,
        "updated_at": NOW.isoformat(), "applied": False})
    current[0] += timedelta(minutes=6); service.scan("u1")
    assert not [x for x in sent if x[0] == "ZhangSan"]
    assert service.get_task("u1", task["id"])["delivery_status"] == "uncertain"
