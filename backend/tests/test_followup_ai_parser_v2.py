from services.ai_parser import parse_task


def test_parse_task_fallback_when_api_key_missing(monkeypatch):
    monkeypatch.setattr("services.ai_parser.DEEPSEEK_API_KEY", None)

    result = parse_task("提醒我跟进客户报价")

    assert result["content"] == "提醒我跟进客户报价"
    assert result["category"] == "其他"
    assert result["is_complete"] is False
    assert result["missing_fields"] == ["remind_time"]
    assert result["clarify_question"]
