from services import wecom_reply


def test_fallback_classifier_separates_task_progress_new_task_and_chat(monkeypatch):
    monkeypatch.setattr(wecom_reply, "DEEPSEEK_API_KEY", None)

    task = {"content": "给客户报价"}
    assert wecom_reply.classify_reply("完成了", task) == "task_progress"
    assert wecom_reply.classify_reply("明天下午提醒我发货", task) == "create_task"
    assert wecom_reply.classify_reply("今天先做什么？", task) == "chat"
    assert wecom_reply.classify_reply("好的", task) == "clarify"


class FakeReplyQuery:
    def __init__(self, db, table_name):
        self.db = db
        self.table_name = table_name
        self.mode = "select"

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.db.filters.setdefault(self.table_name, []).append((column, value))
        return self

    def in_(self, column, value):
        self.db.filters.setdefault(self.table_name, []).append((column, value))
        return self

    def gte(self, column, value):
        self.db.filters.setdefault(self.table_name, []).append((column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, _value):
        return self

    def update(self, payload):
        self.mode = "update"
        self.db.updates.setdefault(self.table_name, []).append(payload)
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.db.inserts.setdefault(self.table_name, []).append(payload)
        return self

    def execute(self):
        if self.table_name == "secretary_outreach":
            return type("R", (), {"data": [self.db.outreach]})()
        if self.table_name == "tasks":
            return type("R", (), {"data": [self.db.task]})()
        return type("R", (), {"data": [{"id": "event-1"}]})()


class FakeReplyDB:
    def __init__(self):
        self.outreach = {
            "id": "outreach-1",
            "task_id": "task-1",
            "kind": "task_followup",
            "content": "请跟进报价",
            "created_at": "2026-07-18T08:00:00+00:00",
        }
        self.task = {
            "id": "task-1",
            "user_id": "user-1",
            "content": "给客户报价",
            "status": "in_progress",
        }
        self.filters = {}
        self.updates = {}
        self.inserts = {}

    def table(self, table_name):
        return FakeReplyQuery(self, table_name)


def _reply_db(monkeypatch):
    db = FakeReplyDB()
    monkeypatch.setattr(wecom_reply, "supabase", db)
    return db


def test_process_pending_reply_marks_exact_task_done(monkeypatch):
    db = _reply_db(monkeypatch)
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "task_progress")
    monkeypatch.setattr(
        wecom_reply,
        "judge_reply",
        lambda _task, _text: {
            "new_status": "done",
            "progress_note": "已完成报价",
            "next_action": None,
            "next_follow_time": None,
            "ai_raw": {"source": "test"},
        },
    )

    result = wecom_reply.process_pending_task_reply("user-1", "完成了")

    assert result["handled"] is True
    assert result["task_id"] == "task-1"
    assert result["status"] == "done"
    assert ("user_id", "user-1") in db.filters["tasks"]
    assert ("id", "task-1") in db.filters["tasks"]
    assert db.updates["tasks"][0]["status"] == "done"
    assert db.updates["tasks"][0]["next_follow_time"] is None
    assert ("user_id", "user-1") in db.filters["secretary_outreach"]
    assert ("id", "outreach-1") in db.filters["secretary_outreach"]


def test_process_pending_reply_does_not_consume_new_task(monkeypatch):
    db = _reply_db(monkeypatch)
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "create_task")

    assert wecom_reply.process_pending_task_reply(
        "user-1", "明天下午提醒我发货"
    ) is None
    assert db.updates.get("tasks") is None


def test_process_pending_reply_clarifies_without_update(monkeypatch):
    db = _reply_db(monkeypatch)
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "clarify")

    result = wecom_reply.process_pending_task_reply("user-1", "好的")

    assert result == {
        "handled": True,
        "reply": "你是在回复刚才这项任务的进展吗？请告诉我：完成了、等回复、卡住了，或者需要延期。",
    }
    assert db.updates.get("tasks") is None
    assert db.updates.get("secretary_outreach") is None


def test_process_pending_reply_pauses_followups(monkeypatch):
    db = _reply_db(monkeypatch)
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "task_progress")

    result = wecom_reply.process_pending_task_reply("user-1", "别催了")

    assert result == {"handled": True, "reply": "好的，这项任务先不催你了。"}
    assert db.updates["tasks"][0] == {"followup_paused": True}
