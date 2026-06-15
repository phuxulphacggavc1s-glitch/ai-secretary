from services.ai_parser import parse_task


def test_parse_task_fallback_contains_v2_fields_when_api_key_missing(monkeypatch):
    monkeypatch.setattr("services.ai_parser.DEEPSEEK_API_KEY", None)

    result = parse_task("提醒我跟进客户报价")

    assert result["content"] == "提醒我跟进客户报价"
    assert result["category"] == "其他"
    assert result["goal"] is None
    assert result["success_criteria"] is None
    assert result["related_person"] is None
    assert result["is_complete"] is False
    assert "goal" in result["missing_fields"]
    assert "success_criteria" in result["missing_fields"]
    assert "remind_time" in result["missing_fields"]
    assert result["clarify_question"]

