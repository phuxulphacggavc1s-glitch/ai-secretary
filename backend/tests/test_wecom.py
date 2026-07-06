from services import wecom


def test_send_wecom_returns_false_when_webhook_missing():
    assert wecom.send_wecom(None, "## test") is False


def test_send_wecom_sends_text_mention_after_markdown(monkeypatch):
    payloads = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 0, "errmsg": "ok"}

    def fake_post(_url, json, timeout):
        payloads.append(json)
        return Response()

    monkeypatch.setattr(wecom.httpx, "post", fake_post)

    assert wecom.send_wecom("https://example.com", "## test", mentioned_mobiles=["13231252391"]) is True
    assert payloads[0]["msgtype"] == "markdown"
    assert payloads[1] == {
        "msgtype": "text",
        "text": {
            "content": "AI秘书提醒：请查看上一条督办消息并及时处理。",
            "mentioned_mobile_list": ["13231252391"],
        },
    }


def test_build_reminder_markdown_contains_core_fields():
    markdown = wecom.build_reminder_markdown(
        {
            "id": "task-1",
            "content": "给客户报价",
            "remind_time": "2026-06-16T15:00:00+08:00",
            "status": "waiting_response",
        }
    )

    assert "给客户报价" in markdown
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
