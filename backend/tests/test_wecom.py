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
