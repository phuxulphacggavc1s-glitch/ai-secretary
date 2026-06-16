from datetime import datetime

from services import followup


def test_judge_reply_fallback_marks_done(monkeypatch):
    monkeypatch.setattr("services.followup.DEEPSEEK_API_KEY", None)

    result = followup.judge_reply({"content": "给客户报价"}, "已经完成，客户确认了")

    assert result["new_status"] == "done"
    assert result["next_follow_time"] is None


def test_judge_reply_fallback_marks_waiting_response(monkeypatch):
    monkeypatch.setattr("services.followup.DEEPSEEK_API_KEY", None)

    result = followup.judge_reply({"content": "给客户报价"}, "对方说下周给我")

    assert result["new_status"] == "waiting_response"
    assert result["next_follow_time"] is not None


def test_ensure_next_follow_fills_missing_for_non_terminal_task():
    task = {
        "status": "pending",
        "remind_time": "2026-06-20T09:00:00+08:00",
        "next_follow_time": None,
    }

    result = followup.ensure_next_follow(task)

    assert result["next_follow_time"] == "2026-06-20T09:00:00+08:00"


def test_ensure_next_follow_skips_terminal_task():
    task = {
        "status": "done",
        "remind_time": "2026-06-20T09:00:00+08:00",
        "next_follow_time": None,
    }

    assert followup.ensure_next_follow(task) == {}


def test_scan_followups_sends_and_postpones(monkeypatch):
    sent = []
    inserted = []
    updated = []

    class FakeSelectQuery:
        def __init__(self, rows, bucket=None):
            self.rows = rows
            self.bucket = bucket

        def select(self, _columns):
            return self

        def lte(self, _column, _value):
            return self

        def not_(self, _column, _operator, _value):
            return self

        def neq(self, _column, _value):
            return self

        def update(self, payload):
            query = FakeUpdateQuery(self.bucket)
            query.payload = payload
            return query

        def execute(self):
            return type("Result", (), {"data": self.rows})()

    class FakeInsertQuery:
        def __init__(self, bucket):
            self.bucket = bucket

        def insert(self, payload):
            self.bucket.append(payload)
            return self

        def execute(self):
            return type("Result", (), {"data": []})()

    class FakeUpdateQuery:
        def __init__(self, bucket):
            self.bucket = bucket
            self.payload = None

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, _column, _value):
            return self

        def execute(self):
            self.bucket.append(self.payload)
            return type("Result", (), {"data": [self.payload]})()

    class FakeSupabase:
        def table(self, name):
            if name == "tasks":
                return FakeSelectQuery(
                    [
                        {
                            "id": "task-1",
                            "user_id": "user-1",
                            "content": "跟进客户报价",
                            "status": "pending",
                            "next_follow_time": "2026-06-15T08:00:00+08:00",
                        }
                    ],
                    updated,
                )
            if name == "task_events":
                return FakeInsertQuery(inserted)
            raise AssertionError(name)

    monkeypatch.setattr(followup, "supabase", FakeSupabase())
    monkeypatch.setattr(
        followup,
        "send_wecom",
        lambda webhook, markdown, mentioned_mobiles=None: sent.append(mentioned_mobiles) or True,
    )
    monkeypatch.setattr(followup, "resolve_webhook", lambda user_id: "https://example.com")
    monkeypatch.setattr(followup, "resolve_mentioned_mobiles", lambda user_id: ["13800138000"])

    followup.scan_followups()

    assert sent == [["13800138000"]]
    assert [event["event_type"] for event in inserted] == ["reminder_sent", "follow_generated"]
    assert updated[0]["next_follow_time"] != "2026-06-15T08:00:00+08:00"


def test_escalate_s_level_sends_and_logs(monkeypatch):
    sent = []
    inserted = []

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def select(self, _columns):
            return self

        def eq(self, _column, _value):
            return self

        def lte(self, _column, _value):
            return self

        def not_(self, _column, _operator, _value):
            return self

        def neq(self, _column, _value):
            return self

        def insert(self, payload):
            inserted.append(payload)
            return self

        def execute(self):
            return type("Result", (), {"data": self.rows})()

    class FakeSupabase:
        def table(self, name):
            if name == "tasks":
                return FakeQuery(
                    [
                        {
                            "id": "task-s",
                            "user_id": "user-1",
                            "content": "今天必须拿到报价",
                            "status": "pending",
                            "priority_level": "S",
                            "remind_time": "2026-06-15T15:00:00+08:00",
                        }
                    ]
                )
            if name == "task_events":
                return FakeQuery([])
            raise AssertionError(name)

    monkeypatch.setattr(followup, "supabase", FakeSupabase())
    monkeypatch.setattr(
        followup,
        "send_wecom",
        lambda webhook, markdown, mentioned_mobiles=None: sent.append(mentioned_mobiles) or True,
    )
    monkeypatch.setattr(followup, "resolve_webhook", lambda user_id: "https://example.com")
    monkeypatch.setattr(followup, "resolve_mentioned_mobiles", lambda user_id: ["13800138000"])

    followup.escalate_s_level()

    assert sent == [["13800138000"]]
    assert inserted[0]["event_type"] == "reminder_sent"
    assert "S级" in inserted[0]["note"]
