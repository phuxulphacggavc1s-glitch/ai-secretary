"""Deterministic limits for proactive secretary messages."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from database import supabase


DEFAULT_TIMEZONE = "Asia/Shanghai"
DAILY_LIMIT = 4
COOLDOWN = timedelta(hours=3)


def evaluate_static_rules(
    *,
    kind: str,
    now: datetime,
    sent_today: int,
    same_task_sent_today: bool,
    task_replied_today: bool,
    last_sent_at: datetime | None,
    explicit_reminder: bool = False,
) -> dict:
    if explicit_reminder:
        return {"allowed": True, "reason": None}
    if now.time() < time(8, 0) or now.time() >= time(21, 0):
        return {"allowed": False, "reason": "安静时段"}
    if sent_today >= DAILY_LIMIT:
        return {"allowed": False, "reason": "今日主动消息已达4条"}
    if task_replied_today and kind == "s_escalation":
        return {"allowed": False, "reason": "该任务今天已有有效回复"}
    if same_task_sent_today and kind == "task_followup":
        return {"allowed": False, "reason": "该任务今天已跟进"}
    if kind != "s_escalation" and last_sent_at and now - last_sent_at < COOLDOWN:
        return {"allowed": False, "reason": "距离上次主动联系不足3小时"}
    return {"allowed": True, "reason": None}


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _user_timezone(user_id: str) -> ZoneInfo:
    result = supabase.table("users").select("timezone").eq("id", user_id).execute()
    timezone_name = result.data[0].get("timezone") if result.data else DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def evaluate_outreach(
    *,
    user_id: str,
    kind: str,
    task_id: str | None = None,
    now: datetime | None = None,
    explicit_reminder: bool = False,
) -> dict:
    if explicit_reminder:
        return {"allowed": True, "reason": None}

    user_timezone = _user_timezone(user_id)
    current = _parse_datetime(now or datetime.now(timezone.utc))
    local_now = current.astimezone(user_timezone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    result = (
        supabase.table("secretary_outreach")
        .select("task_id,kind,status,sent_at,replied_at,created_at")
        .eq("user_id", user_id)
        .in_("status", ["sent", "replied"])
        .gte("created_at", day_start.astimezone(timezone.utc).isoformat())
        .lt("created_at", day_end.astimezone(timezone.utc).isoformat())
        .order("created_at", desc=True)
        .execute()
    )
    rows = result.data or []
    same_task_rows = [row for row in rows if task_id and row.get("task_id") == task_id]
    sent_times = [
        parsed
        for parsed in (
            _parse_datetime(row.get("sent_at") or row.get("created_at")) for row in rows
        )
        if parsed is not None
    ]
    last_sent_at = max(sent_times).astimezone(user_timezone) if sent_times else None

    return evaluate_static_rules(
        kind=kind,
        now=local_now,
        sent_today=len(rows),
        same_task_sent_today=any(
            row.get("kind") == "task_followup" for row in same_task_rows
        ),
        task_replied_today=any(
            row.get("status") == "replied" or row.get("replied_at")
            for row in same_task_rows
        ),
        last_sent_at=last_sent_at,
        explicit_reminder=False,
    )
