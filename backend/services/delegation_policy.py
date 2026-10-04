"""委派任务的确定性命令、时间和催办规则。"""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

def as_time(value):
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return parsed.astimezone(timezone.utc)

def parse_command(text):
    match = re.fullmatch(r"(同意|确认|取消|不发)(?:\s*(\d{4}))?[。！!]? ", text.strip() + " ")
    if match:
        return ("approve" if match[1] in ("同意", "确认") else "cancel", match[2], None)
    match = re.fullmatch(r"修改(?:\s*(\d{4}))?\s*为\s*(.+)", text.strip(), re.S)
    if match:
        return ("modify", match[1], match[2].strip())
    return None

def classify_reply(text):
    match = re.fullmatch(r"(\d{4})\s+(.+)", text.strip(), re.S)
    code, body = (match[1], match[2].strip()) if match else (None, text.strip())
    if re.fullmatch(r"(已完成|完成了?|做完了|已做完)[。！!]*", body):
        state = "completed"
    elif re.fullmatch(r"(已收到|收到[了]?|好的|已接收)[。！!]*", body):
        state = "acknowledged"
    elif body.startswith(("延期", "推迟")):
        state = "delayed"
    else:
        state = "in_progress"
    return state, body, code

def approval_expired(task, now):
    origin = as_time(task.get("approval_requested_at") or task["scheduled_at"])
    return now >= origin + timedelta(hours=24)

def followup_due(task, now):
    due = as_time(task.get("next_followup_at"))
    if task.get("task_status") != "awaiting_reply" or task.get("followup_count", 0) >= 2:
        return False
    count = task.get("daily_reminder_count", 0)
    if task.get("reminder_count_date") != now.astimezone(SHANGHAI).date().isoformat():
        count = 0
    return bool(due and due <= now and count < 2)

def followup_update(task, now):
    total = task.get("followup_count", 0) + 1
    day = now.astimezone(SHANGHAI).date().isoformat()
    daily = task.get("daily_reminder_count", 0) if task.get("reminder_count_date") == day else 0
    return {
        "followup_count": total,
        "daily_reminder_count": daily + 1,
        "reminder_count_date": day,
        "next_followup_at": (now + timedelta(hours=1)).isoformat() if total == 1 else None,
        "task_status": "awaiting_reply" if total == 1 else "unresponsive",
        "paused_reason": None if total == 1 else "两次催办后仍未回复",
    }
