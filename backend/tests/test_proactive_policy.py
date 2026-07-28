from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services import proactive_policy


TZ = ZoneInfo("Asia/Shanghai")


def _decision(**overrides):
    values = {
        "kind": "task_followup",
        "now": datetime(2026, 7, 29, 10, 0, tzinfo=TZ),
        "sent_today": 0,
        "same_task_sent_today": False,
        "task_replied_today": False,
        "last_sent_at": None,
        "explicit_reminder": False,
    }
    values.update(overrides)
    return proactive_policy.evaluate_static_rules(**values)


def test_quiet_hours_block_proactive_followup():
    assert _decision(now=datetime(2026, 7, 29, 21, 5, tzinfo=TZ)) == {
        "allowed": False,
        "reason": "安静时段",
    }


def test_fifth_daily_message_is_blocked():
    assert _decision(sent_today=4) == {
        "allowed": False,
        "reason": "今日主动消息已达4条",
    }


def test_different_tasks_cannot_bypass_three_hour_cooldown():
    now = datetime(2026, 7, 29, 10, 0, tzinfo=TZ)
    assert _decision(last_sent_at=now - timedelta(hours=2)) == {
        "allowed": False,
        "reason": "距离上次主动联系不足3小时",
    }


def test_same_task_followup_is_limited_to_once_per_day():
    assert _decision(same_task_sent_today=True) == {
        "allowed": False,
        "reason": "该任务今天已跟进",
    }


def test_explicit_reminder_is_allowed_during_quiet_hours():
    now = datetime(2026, 7, 29, 1, 15, tzinfo=TZ)
    assert _decision(
        now=now,
        sent_today=4,
        same_task_sent_today=True,
        last_sent_at=now - timedelta(minutes=1),
        explicit_reminder=True,
    ) == {"allowed": True, "reason": None}


def test_s_escalation_stops_after_valid_reply():
    assert _decision(kind="s_escalation", task_replied_today=True) == {
        "allowed": False,
        "reason": "该任务今天已有有效回复",
    }

class Result:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def in_(self, _column, _values):
        return self

    def gte(self, _column, _value):
        return self

    def lt(self, _column, _value):
        return self

    def order(self, _column, desc=False):
        return self

    def execute(self):
        return Result(self.rows)


class FakeSupabase:
    def __init__(self, outreach_rows):
        self.users = FakeQuery([{"timezone": "Asia/Shanghai"}])
        self.outreach = FakeQuery(outreach_rows)

    def table(self, name):
        if name == "users":
            return self.users
        if name == "secretary_outreach":
            return self.outreach
        raise AssertionError(name)


def test_evaluate_outreach_reads_only_current_user_history(monkeypatch):
    db = FakeSupabase(
        [
            {
                "task_id": "task-1",
                "kind": "task_followup",
                "status": "sent",
                "sent_at": "2026-07-29T01:00:00+00:00",
                "created_at": "2026-07-29T01:00:00+00:00",
                "replied_at": None,
            }
        ]
    )
    monkeypatch.setattr(proactive_policy, "supabase", db)

    result = proactive_policy.evaluate_outreach(
        user_id="user-1",
        kind="task_followup",
        task_id="task-1",
        now=datetime(2026, 7, 29, 10, 0, tzinfo=TZ),
    )

    assert result == {"allowed": False, "reason": "该任务今天已跟进"}
    assert ("id", "user-1") in db.users.filters
    assert ("user_id", "user-1") in db.outreach.filters
