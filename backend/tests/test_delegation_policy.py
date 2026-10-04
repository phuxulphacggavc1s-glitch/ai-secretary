from datetime import datetime, timedelta, timezone
import pytest
from services import delegation_policy as policy

NOW = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)

def test_commands_need_explicit_approval():
    assert policy.parse_command("同意 1024") == ("approve", "1024", None)
    assert policy.parse_command("取消 1024") == ("cancel", "1024", None)
    assert policy.parse_command("修改 1024 为 明天交数据") == ("modify", "1024", "明天交数据")
    assert policy.parse_command("可能可以") is None
    assert policy.parse_command("我不同意 1024") is None

def test_bare_command_and_code_only_reply():
    assert policy.parse_command("同意") == ("approve", None, None)
    assert policy.classify_reply("1024 完成") == ("completed", "完成", "1024")

@pytest.mark.parametrize("text,state", [
    ("完成", "completed"), ("已完成", "completed"),
    ("没完成", "in_progress"), ("还没完成", "in_progress"),
    ("没有收到", "in_progress"), ("收到", "acknowledged"),
    ("延期到明天下午", "delayed"), ("正在整理", "in_progress"),
])
def test_reply_keywords_do_not_match_negation(text, state):
    assert policy.classify_reply(text)[0] == state

def test_followup_first_after_30_minutes_then_60_minutes():
    task = {"task_status": "awaiting_reply", "sent_at": NOW.isoformat(),
            "next_followup_at": (NOW + timedelta(minutes=30)).isoformat(),
            "followup_count": 0, "daily_reminder_count": 0}
    assert not policy.followup_due(task, NOW + timedelta(minutes=29))
    assert policy.followup_due(task, NOW + timedelta(minutes=30))
    update = policy.followup_update(task, NOW + timedelta(minutes=30))
    assert update["next_followup_at"] == (NOW + timedelta(minutes=90)).isoformat()
    task.update(update)
    assert not policy.followup_due(task, NOW + timedelta(minutes=89))
    assert policy.followup_due(task, NOW + timedelta(minutes=90))
    update = policy.followup_update(task, NOW + timedelta(minutes=90))
    assert update["task_status"] == "unresponsive"
    assert update["next_followup_at"] is None

def test_day_change_does_not_restart_finished_cycle():
    task = {"task_status": "awaiting_reply", "followup_count": 2,
            "daily_reminder_count": 0, "next_followup_at": NOW.isoformat()}
    assert not policy.followup_due(task, NOW + timedelta(days=1))

def test_reply_cancels_followup():
    task = {"task_status": "acknowledged", "followup_count": 0,
            "next_followup_at": NOW.isoformat()}
    assert not policy.followup_due(task, NOW)

def test_approval_expiration_uses_delivered_request_time():
    task = {"scheduled_at": (NOW - timedelta(hours=25)).isoformat(),
            "approval_requested_at": NOW.isoformat()}
    assert not policy.approval_expired(task, NOW)
    assert policy.approval_expired(task, NOW + timedelta(hours=24))
