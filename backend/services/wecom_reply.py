from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from constants import EventType, TaskStatus
from database import supabase
from services.followup import judge_reply
from services.persona import SECRETARY_PERSONA


VALID_INTENTS = {"create_task", "task_progress", "chat", "clarify"}
CREATE_KEYWORDS = ("提醒我", "记一下", "记个", "别忘了", "新增待办")
PROGRESS_KEYWORDS = (
    "完成",
    "搞定",
    "已联系",
    "等回复",
    "下周回复",
    "明天回复",
    "卡住",
    "缺资料",
    "延期",
    "正在做",
    "继续推进",
    "别催",
)

CLASSIFY_SYSTEM_PROMPT = SECRETARY_PERSONA + """
你正在处理用户对一条企业微信任务催办的最新回复。
请只判断意图并返回 JSON：
{"intent":"create_task|task_progress|chat|clarify"}

规则：
- create_task：用户要新建一条待办或提醒，不能修改当前任务。
- task_progress：用户在汇报当前任务的完成、等待、卡住、延期或推进进展。
- chat：用户在提问、闲聊或寻求建议，不能修改当前任务。
- clarify：只有“好、好的、收到、知道了”这类无法判断是否在汇报任务的短确认。
"""


def _strip_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _fallback_classify(text: str) -> str:
    if any(word in text for word in CREATE_KEYWORDS):
        return "create_task"
    if any(word in text for word in PROGRESS_KEYWORDS):
        return "task_progress"
    if text.strip() in {"好", "好的", "知道了", "收到"}:
        return "clarify"
    return "chat"


def classify_reply(text: str, task: dict) -> str:
    if not DEEPSEEK_API_KEY:
        return _fallback_classify(text)

    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"任务": task.get("content"), "用户回复": text},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=80,
        )
        result = json.loads(_strip_json_text(response.choices[0].message.content or ""))
        intent = result.get("intent")
        if intent in VALID_INTENTS:
            return intent
    except Exception as exc:
        print(f"wecom reply classification failed: {exc}")

    return _fallback_classify(text)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_pending_task_outreach(user_id: str, now: datetime | None = None) -> dict | None:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=36)
    result = (
        supabase.table("secretary_outreach")
        .select("id, task_id, kind, content, created_at")
        .eq("user_id", user_id)
        .eq("status", "sent")
        .in_("kind", ["task_followup", "s_escalation"])
        .gte("created_at", cutoff.isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _mark_outreach_replied(outreach_id: str, user_id: str) -> None:
    (
        supabase.table("secretary_outreach")
        .update({"status": "replied", "replied_at": _now_iso()})
        .eq("id", outreach_id)
        .eq("user_id", user_id)
        .execute()
    )


def _reply_for_status(status: str) -> str:
    messages = {
        TaskStatus.DONE.value: "收到，已标记完成。",
        TaskStatus.WAITING_RESPONSE.value: "收到，已记为等对方回复，我会按约定继续跟进。",
        TaskStatus.BLOCKED.value: "收到，已标记为卡住。需要我帮你拆下一步吗？",
        TaskStatus.IN_PROGRESS.value: "收到，已更新进展，我会继续跟进。",
    }
    return messages.get(status, "收到，已更新这项任务。")


def process_pending_task_reply(user_id: str, text: str) -> dict | None:
    outreach = get_pending_task_outreach(user_id)
    if not outreach or not outreach.get("task_id"):
        return None

    task_result = (
        supabase.table("tasks")
        .select("*")
        .eq("id", outreach["task_id"])
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not task_result.data:
        return None
    task = task_result.data[0]

    intent = classify_reply(text, task)
    if intent in {"create_task", "chat"}:
        return None
    if intent == "clarify":
        return {
            "handled": True,
            "reply": "你是在回复刚才这项任务的进展吗？请告诉我：完成了、等回复、卡住了，或者需要延期。",
        }

    if "别催" in text:
        (
            supabase.table("tasks")
            .update({"followup_paused": True})
            .eq("id", task["id"])
            .eq("user_id", user_id)
            .execute()
        )
        supabase.table("task_events").insert(
            {
                "task_id": task["id"],
                "user_id": user_id,
                "event_type": EventType.CHECKIN.value,
                "note": "followups paused from wecom reply",
            }
        ).execute()
        _mark_outreach_replied(outreach["id"], user_id)
        return {"handled": True, "reply": "好的，这项任务先不催你了。"}

    judged = judge_reply(task, text)
    status = judged.get("new_status")
    valid_statuses = {item.value for item in TaskStatus}
    if status not in valid_statuses:
        return None

    updates = {
        "status": status,
        "progress_note": judged.get("progress_note"),
        "next_action": judged.get("next_action"),
        "next_follow_time": judged.get("next_follow_time"),
    }
    if status in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}:
        updates["next_follow_time"] = None

    (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task["id"])
        .eq("user_id", user_id)
        .execute()
    )
    supabase.table("task_events").insert(
        {
            "task_id": task["id"],
            "user_id": user_id,
            "event_type": EventType.AI_JUDGE.value,
            "from_status": task.get("status"),
            "to_status": status,
            "ai_raw": judged.get("ai_raw"),
            "note": judged.get("progress_note"),
        }
    ).execute()
    _mark_outreach_replied(outreach["id"], user_id)
    return {
        "handled": True,
        "task_id": task["id"],
        "status": status,
        "reply": _reply_for_status(status),
    }
