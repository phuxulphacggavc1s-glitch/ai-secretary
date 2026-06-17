from datetime import datetime

import pytest

from services import secretary


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables.get(name, []))


def test_build_briefing_prioritizes_today_overdue_and_checkins(monkeypatch):
    fixed_now = datetime.fromisoformat("2026-06-05T12:00:00+08:00")
    monkeypatch.setattr(secretary, "_now_for_timezone", lambda _timezone: fixed_now)
    monkeypatch.setattr(
        secretary,
        "supabase",
        FakeSupabase(
            {
                "users": [{"id": "user-1", "timezone": "Asia/Shanghai"}],
                "tasks": [
                    {
                        "id": "today-high",
                        "user_id": "user-1",
                        "content": "联系供应商确认补货",
                        "status": "pending",
                        "priority": 3,
                        "remind_time": "2026-06-05T15:00:00+08:00",
                        "created_at": "2026-06-05T08:00:00+08:00",
                        "updated_at": "2026-06-05T08:00:00+08:00",
                    },
                    {
                        "id": "overdue",
                        "user_id": "user-1",
                        "content": "回小红书评论",
                        "status": "pending",
                        "priority": 2,
                        "remind_time": "2026-06-04T09:00:00+08:00",
                        "snooze_until": None,
                        "created_at": "2026-06-04T08:00:00+08:00",
                        "updated_at": "2026-06-04T08:00:00+08:00",
                    },
                    {
                        "id": "doing",
                        "user_id": "user-1",
                        "content": "双11活动方案",
                        "status": "in_progress",
                        "priority": 1,
                        "remind_time": "2026-06-07T09:00:00+08:00",
                        "last_checkin_at": None,
                        "created_at": "2026-06-04T08:00:00+08:00",
                        "updated_at": "2026-06-04T08:00:00+08:00",
                    },
                    {
                        "id": "done-today",
                        "user_id": "user-1",
                        "content": "整理报价单",
                        "status": "done",
                        "priority": 1,
                        "remind_time": "2026-06-05T10:00:00+08:00",
                        "created_at": "2026-06-05T08:00:00+08:00",
                        "updated_at": "2026-06-05T11:00:00+08:00",
                    },
                ],
            }
        ),
    )

    briefing = secretary.build_briefing("user-1")

    assert briefing["stats"]["today_total"] == 2
    assert briefing["stats"]["overdue"] == 1
    assert briefing["stats"]["in_progress"] == 1
    assert briefing["stats"]["done_today"] == 1
    assert briefing["top_priority"]["id"] == "today-high"
    assert [task["id"] for task in briefing["today"]] == ["today-high", "done-today"]
    assert [task["id"] for task in briefing["overdue"]] == ["overdue"]
    assert [task["id"] for task in briefing["checkins"]] == ["doing"]
    assert "今天有 2 件重点，1 件逾期" in briefing["greeting"]


def test_build_briefing_hides_snoozed_overdue(monkeypatch):
    fixed_now = datetime.fromisoformat("2026-06-05T12:00:00+08:00")
    monkeypatch.setattr(secretary, "_now_for_timezone", lambda _timezone: fixed_now)
    monkeypatch.setattr(
        secretary,
        "supabase",
        FakeSupabase(
            {
                "users": [{"id": "user-1", "timezone": "Asia/Shanghai"}],
                "tasks": [
                    {
                        "id": "snoozed",
                        "user_id": "user-1",
                        "content": "给客户报价",
                        "status": "pending",
                        "priority": 3,
                        "remind_time": "2026-06-04T09:00:00+08:00",
                        "snooze_until": "2026-06-06T08:00:00+08:00",
                    }
                ],
            }
        ),
    )

    briefing = secretary.build_briefing("user-1")

    assert briefing["overdue"] == []
    assert briefing["stats"]["overdue"] == 0


def test_build_briefing_hides_postponed_followups_from_overdue(monkeypatch):
    fixed_now = datetime.fromisoformat("2026-06-05T12:00:00+08:00")
    monkeypatch.setattr(secretary, "_now_for_timezone", lambda _timezone: fixed_now)
    monkeypatch.setattr(
        secretary,
        "supabase",
        FakeSupabase(
            {
                "users": [{"id": "user-1", "timezone": "Asia/Shanghai"}],
                "tasks": [
                    {
                        "id": "postponed",
                        "user_id": "user-1",
                        "content": "给客户报价",
                        "status": "pending",
                        "priority": 3,
                        "remind_time": "2026-06-04T09:00:00+08:00",
                        "next_follow_time": "2026-06-06T09:00:00+08:00",
                        "snooze_until": None,
                    },
                    {
                        "id": "still-overdue",
                        "user_id": "user-1",
                        "content": "确认合同",
                        "status": "pending",
                        "priority": 2,
                        "remind_time": "2026-06-04T10:00:00+08:00",
                        "next_follow_time": "2026-06-05T10:00:00+08:00",
                        "snooze_until": None,
                    },
                ],
            }
        ),
    )

    briefing = secretary.build_briefing("user-1")

    assert [task["id"] for task in briefing["overdue"]] == ["still-overdue"]
    assert briefing["stats"]["overdue"] == 1


def test_build_briefing_includes_waiting_overdue_and_blocked(monkeypatch):
    fixed_now = datetime.fromisoformat("2026-06-05T12:00:00+08:00")
    monkeypatch.setattr(secretary, "_now_for_timezone", lambda _timezone: fixed_now)
    monkeypatch.setattr(
        secretary,
        "supabase",
        FakeSupabase(
            {
                "users": [{"id": "user-1", "timezone": "Asia/Shanghai"}],
                "tasks": [
                    {
                        "id": "waiting-late",
                        "user_id": "user-1",
                        "content": "等客户报价",
                        "status": "waiting_response",
                        "priority": 2,
                        "next_follow_time": "2026-06-05T09:00:00+08:00",
                    },
                    {
                        "id": "blocked",
                        "user_id": "user-1",
                        "content": "合同盖章",
                        "status": "blocked",
                        "priority": 3,
                        "next_follow_time": "2026-06-06T09:00:00+08:00",
                    },
                ],
            }
        ),
    )

    briefing = secretary.build_briefing("user-1")

    assert [task["id"] for task in briefing["waiting_overdue"]] == ["waiting-late"]
    assert [task["id"] for task in briefing["blocked"]] == ["blocked"]
    assert briefing["stats"]["waiting_overdue"] == 1
    assert briefing["stats"]["blocked"] == 1


def test_push_morning_briefing_sends_wecom(monkeypatch):
    sent = []

    class FakeUsersQuery:
        def select(self, _columns):
            return self

        def execute(self):
            return type("Result", (), {"data": [{"id": "user-1"}]})()

    class FakeSupabase:
        def table(self, name):
            assert name == "users"
            return FakeUsersQuery()

    monkeypatch.setattr(secretary, "supabase", FakeSupabase())
    monkeypatch.setattr(secretary, "build_briefing", lambda user_id: {
        "greeting": "早上好，今天有 1 件重点，0 件逾期",
        "stats": {"waiting_overdue": 0, "blocked": 0},
        "top_priority": {"content": "跟进报价"},
        "today": [{"content": "跟进报价"}],
        "overdue": [],
        "waiting_overdue": [],
        "blocked": [],
    })
    monkeypatch.setattr(secretary, "resolve_webhook", lambda user_id: "https://example.com")
    monkeypatch.setattr(secretary, "send_wecom", lambda webhook, markdown: sent.append(markdown) or True)

    secretary.push_morning_briefing()

    assert sent
    assert "跟进报价" in sent[0]
