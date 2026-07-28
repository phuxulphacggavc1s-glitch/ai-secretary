import pytest

from services import outreach


class Result:
    def __init__(self, data):
        self.data = data


class FakeOutreachTable:
    def __init__(self):
        self.rows = []
        self.pending_update = None
        self.filters = []

    def insert(self, payload):
        row = {"id": "outreach-1", **payload}
        self.rows.append(row)
        return type("InsertQuery", (), {"execute": lambda _self: Result([row])})()

    def update(self, payload):
        self.pending_update = payload
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        self.rows[0].update(self.pending_update)
        return Result([self.rows[0]])


class FakeSupabase:
    def __init__(self, table):
        self.outreach = table

    def table(self, name):
        assert name == "secretary_outreach"
        return self.outreach


def test_send_secretary_message_records_success(monkeypatch):
    table = FakeOutreachTable()
    monkeypatch.setattr(outreach, "supabase", FakeSupabase(table))
    monkeypatch.setattr(
        outreach,
        "evaluate_outreach",
        lambda **_kwargs: {"allowed": True, "reason": None},
        raising=False,
    )
    monkeypatch.setattr(outreach, "resolve_wecom_userid", lambda _uid: "User")
    monkeypatch.setattr(outreach, "send_app_text", lambda _wid, _content: True)

    result = outreach.send_secretary_message(
        "user-1",
        "该跟进客户报价了",
        "task_followup",
        task_id="task-1",
    )

    assert result == {
        "sent": True,
        "outreach_id": "outreach-1",
        "reason": None,
    }
    assert table.rows[0]["status"] == "sent"
    assert table.rows[0]["user_id"] == "user-1"
    assert table.rows[0]["task_id"] == "task-1"
    assert ("id", "outreach-1") in table.filters
    assert ("user_id", "user-1") in table.filters


def test_send_secretary_message_records_missing_mapping(monkeypatch):
    table = FakeOutreachTable()
    monkeypatch.setattr(outreach, "supabase", FakeSupabase(table))
    monkeypatch.setattr(
        outreach,
        "evaluate_outreach",
        lambda **_kwargs: {"allowed": True, "reason": None},
        raising=False,
    )
    monkeypatch.setattr(outreach, "resolve_wecom_userid", lambda _uid: None)

    result = outreach.send_secretary_message(
        "user-1",
        "晨报",
        "morning_briefing",
    )

    assert result == {
        "sent": False,
        "outreach_id": "outreach-1",
        "reason": "企业微信账号未绑定",
    }
    assert table.rows[0]["status"] == "failed"
    assert table.rows[0]["failure_reason"] == "企业微信账号未绑定"


def test_send_secretary_message_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unsupported outreach kind"):
        outreach.send_secretary_message("user-1", "测试", "unknown")


def test_policy_denial_does_not_send_or_create_outreach(monkeypatch):
    table = FakeOutreachTable()
    monkeypatch.setattr(outreach, "supabase", FakeSupabase(table))
    monkeypatch.setattr(
        outreach,
        "evaluate_outreach",
        lambda **_kwargs: {"allowed": False, "reason": "距离上次主动联系不足3小时"},
        raising=False,
    )
    monkeypatch.setattr(
        outreach,
        "send_app_text",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not send")),
    )

    result = outreach.send_secretary_message(
        "user-1",
        "继续跟进",
        "task_followup",
        task_id="task-2",
    )

    assert result == {
        "sent": False,
        "outreach_id": None,
        "reason": "距离上次主动联系不足3小时",
        "skipped": True,
    }
    assert table.rows == []
