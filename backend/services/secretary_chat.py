"""秘书对话流：主动开场、意图识别、结合任务与记忆的对话回复。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from database import supabase
from services.ai_parser import parse_task
from services.memory import add_fact, get_memory_context, refresh_user_memory
from services.persona import SECRETARY_PERSONA
from services.secretary import build_briefing


OPENING_SYSTEM_PROMPT = SECRETARY_PERSONA + """
输入是用户今天的任务简报（JSON）和用户记忆（长期画像 + 记住的事实，如果有）。请生成一段"主动开场白"：
1. 先一句自然的问候（结合当前时间段，早上/下午/晚上）。
2. 点出今天最要紧的 1-2 件事（优先级顺序：卡住的 > 等回复超时的 > 逾期的 > 今天要做的）。
3. 如果有需要用户拍板或催办的事，直接问出来，像真秘书那样主动问询。
4. 如果记忆里有可用的洞察（比如某类事经常拖、某个约定的账期快到了），可以善意提一句，但别说教。
5. 全文不超过 120 字。

同时给出 2-4 个用户可能想点的"快捷回复"，每个不超过 12 个字。

只返回 JSON，不要 markdown：
{"message": "开场白", "suggestions": ["快捷回复1", "快捷回复2"]}
"""

CHAT_SYSTEM_PROMPT = SECRETARY_PERSONA + """
你会收到：用户今天的任务简报（JSON）、用户记忆（长期画像 + 记住的事实）、最近的对话记录、用户最新一句话。

第一步，判断用户这句话的意图：
- "create_task"：用户想记一件待办/提醒（例如"明天下午提醒我给客户报价"、"周五要给供应商打款"）。
- "chat"：其他一切——提问、汇报进展、请教建议、闲聊。

第二步：
- 如果是 create_task：reply 留空字符串。
- 如果是 chat：写出秘书回复。要求：
  1. 结合任务简报和记忆给具体、能落地的建议，不要空话。
  2. 回复不超过 150 字，必要时可以反问用户来推进事情。

第三步，判断这句话里有没有"值得长期记住的稳定事实"（人物关系、账期约定、
供应商/客户习惯、平台规则、用户的固定偏好）。有就提炼成一句话（不超过 50 字）
填到 remember；没有就填 null。日常寒暄、一次性信息、任务本身都不算。

只返回 JSON，不要 markdown：
{"intent": "create_task" 或 "chat", "reply": "回复内容", "remember": "值得记住的事实或 null"}
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _client() -> OpenAI:
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def _briefing_context(user_id: str) -> dict:
    briefing = build_briefing(user_id)

    def _names(key: str, limit: int = 3) -> list[str]:
        return [t.get("content", "") for t in (briefing.get(key) or [])[:limit]]

    top = briefing.get("top_priority")
    return {
        "统计": briefing.get("stats"),
        "最优先任务": top.get("content") if top else None,
        "今日任务": _names("today", 5),
        "逾期任务": _names("overdue"),
        "等回复超时": _names("waiting_overdue"),
        "卡住的任务": _names("blocked"),
    }


def get_recent_messages(user_id: str, limit: int = 30) -> list[dict]:
    result = (
        supabase.table("secretary_messages")
        .select("id, role, content, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    messages = result.data or []
    messages.reverse()
    return messages


def save_message(user_id: str, role: str, content: str) -> dict | None:
    result = (
        supabase.table("secretary_messages")
        .insert({"user_id": user_id, "role": role, "content": content})
        .execute()
    )
    return result.data[0] if result.data else None


def _last_secretary_message_at(user_id: str) -> datetime | None:
    result = (
        supabase.table("secretary_messages")
        .select("created_at")
        .eq("user_id", user_id)
        .eq("role", "secretary")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    try:
        return datetime.fromisoformat(result.data[0]["created_at"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return None


def _fallback_opening(context: dict) -> dict:
    stats = context.get("统计") or {}
    parts = [f"今天有 {stats.get('today_total', 0)} 件事"]
    if stats.get("overdue"):
        parts.append(f"{stats['overdue']} 件已逾期，建议先处理")
    top = context.get("最优先任务")
    if top:
        parts.append(f"最要紧的是：{top}")
    return {
        "message": "，".join(parts) + "。",
        "suggestions": ["今天先做什么？", "帮我记个待办"],
    }


def generate_opening(user_id: str) -> dict:
    """生成主动开场白。3 小时内已开过口就不重复打扰。"""
    last_at = _last_secretary_message_at(user_id)
    if last_at and _now() - last_at < timedelta(hours=3):
        return {"message": None, "suggestions": [], "skipped": True}

    context = _briefing_context(user_id)
    memory = get_memory_context(user_id)
    if memory["profile_text"] is None:
        # 首次使用时懒加载生成一次用户画像，之后每周日自动刷新
        try:
            if refresh_user_memory(user_id):
                memory = get_memory_context(user_id)
        except Exception as exc:
            print(f"lazy memory refresh failed for {user_id}: {exc}")

    opening = None
    if DEEPSEEK_API_KEY:
        try:
            now_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %A")
            payload = json.dumps(
                {
                    "当前时间": now_local,
                    "任务简报": context,
                    "用户记忆": {
                        "长期画像": memory["profile_text"] or "暂无",
                        "记住的事实": memory["facts"] or "暂无",
                    },
                },
                ensure_ascii=False,
            )
            response = _client().chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": OPENING_SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
                ],
                temperature=0.6,
                max_tokens=400,
            )
            opening = json.loads(_strip_json_text(response.choices[0].message.content or ""))
        except Exception as exc:
            print(f"generate_opening ai failed for {user_id}: {exc}")

    if not opening or not opening.get("message"):
        opening = _fallback_opening(context)

    saved = save_message(user_id, "secretary", opening["message"])
    return {
        "message": opening["message"],
        "suggestions": opening.get("suggestions") or [],
        "message_id": saved.get("id") if saved else None,
    }


def _fallback_chat(user_id: str, text: str) -> dict:
    task_keywords = ["提醒我", "记一下", "记个", "别忘了", "待办"]
    if any(keyword in text for keyword in task_keywords):
        return {"intent": "create_task", "reply": ""}
    return {
        "intent": "chat",
        "reply": "收到。AI 服务暂时不可用，我先把这句记在对话里，稍后你可以再问我一次。",
    }


def chat(user_id: str, text: str) -> dict:
    """处理用户一句话：识别意图，是记待办还是对话。"""
    save_message(user_id, "user", text)

    judged = None
    if DEEPSEEK_API_KEY:
        try:
            context = _briefing_context(user_id)
            memory = get_memory_context(user_id)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in get_recent_messages(user_id, limit=10)
            ]
            payload = json.dumps(
                {
                    "任务简报": context,
                    "用户记忆": {
                        "长期画像": memory["profile_text"] or "暂无",
                        "记住的事实": memory["facts"] or "暂无",
                    },
                    "最近对话": history,
                    "用户最新一句话": text,
                },
                ensure_ascii=False,
            )
            response = _client().chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
                ],
                temperature=0.5,
                max_tokens=500,
            )
            judged = json.loads(_strip_json_text(response.choices[0].message.content or ""))
        except Exception as exc:
            print(f"chat ai failed for {user_id}: {exc}")

    if not judged or judged.get("intent") not in {"create_task", "chat"}:
        judged = _fallback_chat(user_id, text)

    remember = judged.get("remember")
    if remember and isinstance(remember, str) and remember.lower() != "null":
        try:
            add_fact(user_id, remember)
        except Exception as exc:
            print(f"add_fact from chat failed for {user_id}: {exc}")

    if judged["intent"] == "create_task":
        parsed = parse_task(text)
        ack = "这条我帮你整理成待办了，确认一下内容和时间。"
        save_message(user_id, "secretary", ack)
        return {"intent": "create_task", "reply": ack, "parsed": parsed}

    reply = judged.get("reply") or "我在，你说。"
    save_message(user_id, "secretary", reply)
    return {"intent": "chat", "reply": reply}
