from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from database import supabase


DEFAULT_TIMEZONE = "Asia/Shanghai"


def _parse_datetime(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _now_for_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def _get_user_timezone(user_id: str) -> str:
    result = supabase.table("users").select("timezone").eq("id", user_id).execute()
    if result.data:
        return result.data[0].get("timezone") or DEFAULT_TIMEZONE
    return DEFAULT_TIMEZONE


def _in_today(dt: datetime | None, today_start: datetime, tomorrow_start: datetime) -> bool:
    if not dt:
        return False
    return today_start <= dt < tomorrow_start


def _sort_key(task: dict):
    remind_at = _parse_datetime(task.get("remind_time"))
    return (-(task.get("priority") or 1), remind_at or datetime.max.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE)))


def _should_check_in(task: dict, now: datetime, today_start: datetime) -> bool:
    if task.get("status") != "in_progress":
        return False

    created_at = _parse_datetime(task.get("created_at")) or _parse_datetime(task.get("updated_at"))
    if created_at and created_at.date() == now.date():
        return False

    last_checkin_at = _parse_datetime(task.get("last_checkin_at"))
    remind_at = _parse_datetime(task.get("remind_time"))

    if remind_at and remind_at.date() == now.date():
        first_threshold = datetime.combine(now.date(), time(11, 30), tzinfo=now.tzinfo)
        second_threshold = datetime.combine(now.date(), time(17, 0), tzinfo=now.tzinfo)
        if now >= second_threshold:
            return not last_checkin_at or last_checkin_at < second_threshold
        if now >= first_threshold:
            return not last_checkin_at or last_checkin_at < first_threshold
        return False

    return not last_checkin_at or last_checkin_at < today_start


def build_briefing(user_id: str) -> dict:
    timezone_name = _get_user_timezone(user_id)
    now = _now_for_timezone(timezone_name)
    today_start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    tomorrow_start = today_start + timedelta(days=1)

    result = supabase.table("tasks").select("*").eq("user_id", user_id).execute()
    tasks = result.data or []

    today_tasks = [
        task
        for task in tasks
        if task.get("status") != "done"
        and _in_today(_parse_datetime(task.get("remind_time")), today_start, tomorrow_start)
    ]
    done_today = [
        task
        for task in tasks
        if task.get("status") == "done"
        and _in_today(_parse_datetime(task.get("updated_at")), today_start, tomorrow_start)
    ]
    overdue = []
    for task in tasks:
        remind_at = _parse_datetime(task.get("remind_time"))
        snooze_until = _parse_datetime(task.get("snooze_until"))
        if (
            task.get("status") != "done"
            and remind_at
            and remind_at < now
            and (not snooze_until or snooze_until <= now)
        ):
            overdue.append(task)

    in_progress = [task for task in tasks if task.get("status") == "in_progress"]
    checkins = [task for task in in_progress if _should_check_in(task, now, today_start)]
    sorted_today = sorted(today_tasks + done_today, key=_sort_key)
    top_priority_candidates = sorted([task for task in tasks if task.get("status") != "done"], key=_sort_key)

    stats = {
        "today_total": len(today_tasks) + len(done_today),
        "overdue": len(overdue),
        "in_progress": len(in_progress),
        "done_today": len(done_today),
    }
    greeting = f"早上好，今天有 {stats['today_total']} 件重点，{stats['overdue']} 件逾期"

    return {
        "greeting": greeting,
        "stats": stats,
        "top_priority": top_priority_candidates[0] if top_priority_candidates else None,
        "today": sorted_today,
        "overdue": sorted(overdue, key=_sort_key),
        "checkins": sorted(checkins, key=_sort_key),
    }
