from __future__ import annotations

from datetime import datetime, timedelta
import json

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from constants import EventType, TaskStatus
from database import supabase
from services.outreach import send_secretary_message
from services.persona import SECRETARY_PERSONA
from services.wecom_delivery import bound_user_ids


JUDGE_SYSTEM_PROMPT = SECRETARY_PERSONA + """
你现在的任务：根据任务上下文和用户最新回复，判断任务状态。
progress_note 和 next_action 用你的人设口吻写，简短直接。

规则：
1. 只有拿到最终结果，才能判定为 done。
2. 明确说对方稍后、明天、下周、过几天回复，判定 waiting_response。
3. 明确说卡住、缺资料、缺权限、被阻塞，判定 blocked。
4. 其它仍在推进中的，判定 in_progress。

只返回 JSON：
{
  "new_status": "waiting_response",
  "progress_note": "对方承诺下周给报价",
  "next_action": "下周跟进报价结果",
  "next_follow_time": "2026-06-22T10:00:00+08:00"
}
"""


def _now() -> datetime:
    return datetime.now().astimezone()


def _strip_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _fallback_judge(reply_text: str) -> dict:
    now = _now()
    if any(keyword in reply_text for keyword in ["完成", "搞定", "拿到", "已收到"]):
        return {
            "new_status": TaskStatus.DONE.value,
            "progress_note": reply_text,
            "next_action": None,
            "next_follow_time": None,
            "ai_raw": {"source": "fallback", "reason": "done_keyword"},
        }
    if any(keyword in reply_text for keyword in ["等", "回头", "下周", "明天再"]):
        return {
            "new_status": TaskStatus.WAITING_RESPONSE.value,
            "progress_note": reply_text,
            "next_action": "按约定时间继续跟进",
            "next_follow_time": (now + timedelta(days=3)).isoformat(),
            "ai_raw": {"source": "fallback", "reason": "waiting_keyword"},
        }
    return {
        "new_status": TaskStatus.IN_PROGRESS.value,
        "progress_note": reply_text,
        "next_action": "继续推进当前事项",
        "next_follow_time": (now + timedelta(days=1)).isoformat(),
        "ai_raw": {"source": "fallback", "reason": "default_progress"},
    }


def judge_reply(task: dict, reply_text: str) -> dict:
    if not DEEPSEEK_API_KEY:
        return _fallback_judge(reply_text)

    prompt = json.dumps(
        {
            "task": {
                "content": task.get("content"),
                "status": task.get("status"),
                "next_follow_time": task.get("next_follow_time"),
            },
            "reply_text": reply_text,
            "now": _now().isoformat(),
        },
        ensure_ascii=False,
    )

    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        text = response.choices[0].message.content or ""
        parsed = json.loads(_strip_json_text(text))
        parsed["ai_raw"] = {"source": "deepseek", "raw": text}
        return parsed
    except Exception as exc:
        result = _fallback_judge(reply_text)
        result["ai_raw"] = {
            "source": "fallback",
            "error": str(exc),
            "reply_text": reply_text,
        }
        return result


def ensure_next_follow(task: dict) -> dict:
    status = task.get("status")
    if status in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}:
        return {}
    if task.get("next_follow_time"):
        return {}
    if task.get("remind_time"):
        return {"next_follow_time": task["remind_time"]}
    return {"next_follow_time": (_now() + timedelta(days=1)).isoformat()}


def _postpone_follow_time(value: str | None) -> str:
    base = datetime.fromisoformat((value or _now().isoformat()).replace("Z", "+00:00"))
    current = _now()
    if base.tzinfo is None and current.tzinfo is not None:
        base = base.replace(tzinfo=current.tzinfo)
    anchor = max(base, current)
    return (anchor + timedelta(days=1)).isoformat()


def _is_recent_explicit_reminder(task: dict, now: datetime) -> bool:
    if task.get("reminded") or not task.get("remind_time"):
        return False
    try:
        remind_at = datetime.fromisoformat(task["remind_time"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if remind_at.tzinfo is None and now.tzinfo is not None:
        remind_at = remind_at.replace(tzinfo=now.tzinfo)
    age = now - remind_at
    return timedelta(0) <= age <= timedelta(minutes=15)


def build_followup_text(task: dict, s_level: bool = False) -> str:
    prefix = "【S级事项二次确认】" if s_level else "【AI秘书跟进】"
    return (
        f"{prefix}\n{task.get('content', '未命名任务')}\n"
        "现在进展怎么样？直接回复：完成了 / 等对方回复 / 卡住了 / 明天继续。"
    )


def _due_followup_for_user(user_id: str, now: str) -> dict | None:
    result = (
        supabase.table("tasks")
        .select("*")
        .eq("user_id", user_id)
        .eq("followup_paused", False)
        .lte("next_follow_time", now)
        .neq("status", TaskStatus.DONE.value)
        .neq("status", TaskStatus.CANCELLED.value)
        .order("next_follow_time", desc=True)
        .order("priority", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def scan_followups() -> None:
    now_value = _now()
    now = now_value.isoformat()
    for user_id in bound_user_ids():
        task = _due_followup_for_user(user_id, now)
        if not task:
            continue

        explicit_reminder = _is_recent_explicit_reminder(task, now_value)
        send_kwargs = {"task_id": task["id"]}
        if explicit_reminder:
            send_kwargs["explicit_reminder"] = True
        delivery = send_secretary_message(
            user_id,
            build_followup_text(task),
            "task_followup",
            **send_kwargs,
        )
        if not delivery["sent"] and not delivery.get("skipped"):
            continue

        next_follow_time = _postpone_follow_time(task.get("next_follow_time"))
        updates = {"next_follow_time": next_follow_time}
        if delivery["sent"] and explicit_reminder:
            updates["reminded"] = True
        (
            supabase.table("tasks")
            .update(updates)
            .eq("id", task["id"])
            .eq("user_id", user_id)
            .execute()
        )
        if delivery["sent"]:
            supabase.table("task_events").insert(
                {
                    "task_id": task["id"],
                    "user_id": user_id,
                    "event_type": EventType.REMINDER_SENT.value,
                    "note": "followup reminder sent via wecom app",
                }
            ).execute()
        followup_note = f"next_follow_time postponed to {next_follow_time}"
        if delivery.get("skipped"):
            followup_note += f"; skipped: {delivery.get('reason')}"
        supabase.table("task_events").insert(
            {
                "task_id": task["id"],
                "user_id": user_id,
                "event_type": EventType.FOLLOW_GENERATED.value,
                "note": followup_note,
            }
        ).execute()


def _due_s_task_for_user(user_id: str, now: str) -> dict | None:
    result = (
        supabase.table("tasks")
        .select("*")
        .eq("user_id", user_id)
        .eq("priority_level", "S")
        .eq("followup_paused", False)
        .lte("remind_time", now)
        .neq("status", TaskStatus.DONE.value)
        .neq("status", TaskStatus.CANCELLED.value)
        .order("priority", desc=True)
        .order("remind_time")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def escalate_s_level() -> None:
    now = _now().isoformat()
    for user_id in bound_user_ids():
        task = _due_s_task_for_user(user_id, now)
        if not task:
            continue

        delivery = send_secretary_message(
            user_id,
            build_followup_text(task, s_level=True),
            "s_escalation",
            task_id=task["id"],
        )
        if not delivery["sent"]:
            continue

        supabase.table("task_events").insert(
            {
                "task_id": task["id"],
                "user_id": user_id,
                "event_type": EventType.REMINDER_SENT.value,
                "note": "S级任务晚间二次提醒（企业微信自建应用）",
            }
        ).execute()
