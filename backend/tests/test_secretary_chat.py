from services.secretary_chat import _fallback_chat, _fallback_opening


def test_fallback_chat_detects_task_intent():
    result = _fallback_chat("user-1", "明天下午提醒我给客户报价")
    assert result["intent"] == "create_task"


def test_fallback_chat_defaults_to_chat_intent():
    result = _fallback_chat("user-1", "今天先做什么好")
    assert result["intent"] == "chat"
    assert result["reply"]


def test_fallback_opening_mentions_top_priority():
    context = {
        "统计": {"today_total": 3, "overdue": 1},
        "最优先任务": "给客户报价",
    }
    opening = _fallback_opening(context)
    assert "给客户报价" in opening["message"]
    assert opening["suggestions"]
