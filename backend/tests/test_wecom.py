from services import wecom


def test_send_wecom_returns_false_when_webhook_missing():
    assert wecom.send_wecom(None, "## test") is False


def test_build_reminder_markdown_contains_core_fields():
    markdown = wecom.build_reminder_markdown(
        {
            "id": "task-1",
            "content": "给客户报价",
            "goal": "拿到客户确认",
            "remind_time": "2026-06-16T15:00:00+08:00",
            "status": "waiting_response",
        }
    )

    assert "给客户报价" in markdown
    assert "拿到客户确认" in markdown
    assert "waiting_response" in markdown
    assert "/tasks" in markdown
    assert "TODO" not in markdown
    assert markdown.endswith(")")


def test_resolve_mentioned_mobiles_uses_email_map(monkeypatch):
    class FakeUsersQuery:
        def select(self, _columns):
            return self

        def eq(self, _column, _value):
            return self

        def execute(self):
            return type("Result", (), {"data": [{"email": "USER@example.com"}]})()

    class FakeSupabase:
        def table(self, name):
            assert name == "users"
            return FakeUsersQuery()

    monkeypatch.setattr(wecom, "WECOM_PHONE_MAP_JSON", '{"user@example.com":"13800138000"}')
    monkeypatch.setattr(wecom, "supabase", FakeSupabase())

    assert wecom.resolve_mentioned_mobiles("user-1") == ["13800138000"]
