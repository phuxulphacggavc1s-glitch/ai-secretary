from datetime import datetime

from services import summary_report


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def order(self, _column, desc=False):
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self, rows):
        self.query = FakeQuery(rows)

    def table(self, name):
        assert name == "tasks"
        return self.query


def test_build_summary_report_week_counts_and_suggestions(monkeypatch):
    fixed_now = datetime.fromisoformat("2026-06-18T10:00:00+08:00")
    fake_supabase = FakeSupabase(
        [
            {
                "id": "done-1",
                "content": "完成报价单",
                "category": "工作",
                "status": "done",
                "priority_level": "A",
                "remind_time": "2026-06-16T09:00:00+08:00",
                "next_follow_time": None,
                "created_at": "2026-06-16T08:00:00+08:00",
                "updated_at": "2026-06-16T10:00:00+08:00",
            },
            {
                "id": "late-1",
                "content": "跟进客户回款",
                "category": "财务",
                "status": "pending",
                "priority_level": "S",
                "remind_time": "2026-06-17T09:00:00+08:00",
                "next_follow_time": "2026-06-17T12:00:00+08:00",
                "created_at": "2026-06-17T08:00:00+08:00",
                "updated_at": "2026-06-17T08:00:00+08:00",
            },
            {
                "id": "doing-1",
                "content": "整理直播方案",
                "category": "工作",
                "status": "in_progress",
                "priority_level": "B",
                "remind_time": "2026-06-19T09:00:00+08:00",
                "next_follow_time": "2026-06-19T09:00:00+08:00",
                "created_at": "2026-06-18T08:00:00+08:00",
                "updated_at": "2026-06-18T08:00:00+08:00",
            },
        ]
    )
    monkeypatch.setattr(summary_report, "supabase", fake_supabase)
    monkeypatch.setattr(summary_report, "_now", lambda: fixed_now)
    monkeypatch.setattr(summary_report, "_ai_summary", lambda *_args: None)

    report = summary_report.build_summary_report("user-1", "week")

    assert report["period"] == "week"
    assert report["stats"] == {
        "total": 3,
        "done": 1,
        "pending": 1,
        "in_progress": 1,
        "waiting_response": 0,
        "blocked": 0,
        "overdue": 1,
    }
    assert report["category_stats"] == [{"category": "工作", "count": 2}, {"category": "财务", "count": 1}]
    assert report["highlights"] == ["完成报价单"]
    assert report["risks"] == ["跟进客户回款"]
    assert len(report["suggestions"]) == 3
    assert ("eq", "user_id", "user-1") in fake_supabase.query.filters


def test_build_summary_report_rejects_invalid_period():
    try:
        summary_report.build_summary_report("user-1", "year")
    except ValueError as exc:
        assert "period" in str(exc)
    else:
        raise AssertionError("expected ValueError")
