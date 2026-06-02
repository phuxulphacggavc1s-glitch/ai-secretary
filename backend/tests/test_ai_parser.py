from services.ai_parser import parse_task


def test_parse_task_falls_back_when_api_key_missing(monkeypatch):
    monkeypatch.setattr("services.ai_parser.DEEPSEEK_API_KEY", None)
    result = parse_task("明天下午提醒我给客户报价")
    assert result["content"] == "明天下午提醒我给客户报价"
    assert result["category"] == "其他"
    assert result["remind_time"] is None
    assert result["is_time_clear"] is False
