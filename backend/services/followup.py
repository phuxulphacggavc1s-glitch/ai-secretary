from __future__ import annotations

from datetime import datetime, timedelta
import json

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from constants import EventType, TaskStatus
from database import supabase
from services.wecom import build_reminder_markdown, resolve_mentioned_mobiles, resolve_webhook, send_wecom


JUDGE_SYSTEM_PROMPT = """你是结果导向的秘书督办助手。

你需要根据任务上下文和用户最新回复，判断任务状态。

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
                "goal": task.get("goal"),
                "success_criteria": task.get("success_criteria"),
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
        result["ai_raw"] = {"source": "fallback", "error": str(exc), "reply_text": reply_text}
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
    return (base + timedelta(days=1)).isoformat()


def scan_followups() -> None:
    now = _now().isoformat()
    result = (
        supabase.table("tasks")
        .select("*")
        .lte("next_follow_time", now)
        .neq("status", TaskStatus.DONE.value)
        .neq("status", TaskStatus.CANCELLED.value)
        .execute()
    )

    for task in result.data or []:
        sent = send_wecom(
            resolve_webhook(task["user_id"]),
            build_reminder_markdown(task),
            mentioned_mobiles=resolve_mentioned_mobiles(task["user_id"]),
        )
        next_follow_time = _postpone_follow_time(task.get("next_follow_time"))
        if sent:
            supabase.table("task_events").insert(
                {
                    "task_id": task["id"],
                    "user_id": task["user_id"],
                    "event_type": EventType.REMINDER_SENT.value,
                    "note": "followup reminder sent",
                }
            ).execute()
        supabase.table("tasks").update(
            {"next_follow_time": next_follow_time}
        ).eq("id", task["id"]).eq("user_id", task["user_id"]).execute()
        supabase.table("task_events").insert(
            {
                "task_id": task["id"],
                "user_id": task["user_id"],
                "event_type": EventType.FOLLOW_GENERATED.value,
                "note": f"next_follow_time postponed to {next_follow_time}",
            }
        ).execute()


def escalate_s_level() -> None:
    now = _now().isoformat()
    result = (
        supabase.table("tasks")
        .select("*")
        .eq("priority_level", "S")
        .lte("remind_time", now)
        .neq("status", TaskStatus.DONE.value)
        .neq("status", TaskStatus.CANCELLED.value)
        .execute()
    )
    for task in result.data or []:
        sent = send_wecom(
            resolve_webhook(task["user_id"]),
            build_reminder_markdown(task),
            mentioned_mobiles=resolve_mentioned_mobiles(task["user_id"]),
        )
        if sent:
            supabase.table("task_events").insert(
                {
                    "task_id": task["id"],
                    "user_id": task["user_id"],
                    "event_type": EventType.REMINDER_SENT.value,
                    "note": "S级任务晚间二次提醒",
                }
            ).execute()
