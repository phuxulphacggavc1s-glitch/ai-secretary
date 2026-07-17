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


class Result:
    def __init__(self, data):
        self.data = data


class FakeTaskQuery:
    def __init__(self, rows, updated, filter_log):
        self.rows = rows
        self.updated = updated
        self.filter_log = filter_log
        self.payload = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filter_log.append((column, value))
        return self

    def lte(self, _column, _value):
        return self

    def neq(self, _column, _value):
        return self

    def order(self, _column, desc=False):
        return self

    def limit(self, _value):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            self.updated.append(self.payload)
            return Result([self.payload])
        return Result(self.rows)


class FakeEventQuery:
    def __init__(self, inserted):
        self.inserted = inserted
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.inserted.append(self.payload)
        return Result([self.payload])


class FakeSupabase:
    def __init__(self, tasks):
        self.tasks = tasks
        self.updated = []
        self.inserted = []
        self.filters = []

    def table(self, name):
        if name == "tasks":
            return FakeTaskQuery(self.tasks, self.updated, self.filters)
        if name == "task_events":
            return FakeEventQuery(self.inserted)
        raise AssertionError(name)


def test_scan_followups_uses_bound_user_app_and_postpones_after_success(monkeypatch):
    db = FakeSupabase(
        [
            {
                "id": "task-1",
                "user_id": "user-1",
                "content": "跟进客户报价",
                "status": "pending",
                "priority": 3,
                "next_follow_time": "2026-06-15T08:00:00+08:00",
                "followup_paused": False,
            }
        ]
    )
    sent = []
    monkeypatch.setattr(followup, "supabase", db)
    monkeypatch.setattr(followup, "bound_user_ids", lambda: ["user-1"])
    monkeypatch.setattr(
        followup,
        "send_secretary_message",
        lambda user_id, content, kind, task_id=None: sent.append(
            (user_id, content, kind, task_id)
        )
        or {"sent": True, "outreach_id": "out-1", "reason": None},
    )

    followup.scan_followups()

    assert sent[0][0:1] == ("user-1",)
    assert sent[0][2:] == ("task_followup", "task-1")
    assert "跟进客户报价" in sent[0][1]
    assert ("user_id", "user-1") in db.filters
    assert ("followup_paused", False) in db.filters
    assert db.updated[0]["next_follow_time"] != "2026-06-15T08:00:00+08:00"
    assert [event["event_type"] for event in db.inserted] == [
        "reminder_sent",
        "follow_generated",
    ]


def test_scan_followups_does_not_postpone_after_send_failure(monkeypatch):
    db = FakeSupabase(
        [
            {
                "id": "task-1",
                "user_id": "user-1",
                "content": "跟进客户报价",
                "status": "pending",
                "priority": 3,
                "next_follow_time": "2026-06-15T08:00:00+08:00",
                "followup_paused": False,
            }
        ]
    )
    monkeypatch.setattr(followup, "supabase", db)
    monkeypatch.setattr(followup, "bound_user_ids", lambda: ["user-1"])
    monkeypatch.setattr(
        followup,
        "send_secretary_message",
        lambda *_args, **_kwargs: {
            "sent": False,
            "outreach_id": "out-1",
            "reason": "企业微信发送失败",
        },
    )

    followup.scan_followups()

    assert db.updated == []
    assert db.inserted == []


def test_escalate_s_level_uses_bound_user_app_and_logs(monkeypatch):
    db = FakeSupabase(
        [
            {
                "id": "task-s",
                "user_id": "user-1",
                "content": "今天必须拿到报价",
                "status": "pending",
                "priority": 3,
                "priority_level": "S",
                "remind_time": "2026-06-15T15:00:00+08:00",
                "followup_paused": False,
            }
        ]
    )
    sent = []
    monkeypatch.setattr(followup, "supabase", db)
    monkeypatch.setattr(followup, "bound_user_ids", lambda: ["user-1"])
    monkeypatch.setattr(
        followup,
        "send_secretary_message",
        lambda user_id, content, kind, task_id=None: sent.append(
            (user_id, content, kind, task_id)
        )
        or {"sent": True, "outreach_id": "out-1", "reason": None},
    )

    followup.escalate_s_level()

    assert sent[0][2:] == ("s_escalation", "task-s")
    assert ("user_id", "user-1") in db.filters
    assert db.inserted[0]["event_type"] == "reminder_sent"
    assert "S级" in db.inserted[0]["note"]
