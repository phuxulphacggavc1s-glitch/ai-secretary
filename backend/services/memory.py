"""用户记忆层：定期把任务历史提炼成"用户画像"，让秘书越用越懂用户。"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from database import supabase


MEMORY_SYSTEM_PROMPT = """你是一个 AI 秘书的"记忆整理员"。

输入是某位用户最近 60 天的任务统计和明细摘要。请把它提炼成一段"用户画像"，
供秘书今后跟用户对话时参考，让建议更贴合这个人的实际情况。

要求：
1. 用大白话，不超过 300 字，直接写结论，不要开头语。
2. 重点提炼：他最常处理哪类事、哪类事容易拖延或逾期、做事节奏（比如喜欢集中在什么时候）、
   经常打交道的对象或平台（如客户、供应商、抖音、淘宝）、完成率高低。
3. 如果数据太少不足以下结论，就写"数据还少"并只写能确定的部分。
4. 只输出画像文本本身，不要 JSON、不要 markdown 标题。
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


MAX_FACTS = 15
MAX_FACT_LENGTH = 60


def get_profile_text(user_id: str) -> str | None:
    try:
        result = (
            supabase.table("user_memory")
            .select("profile_text")
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0].get("profile_text")
    except Exception as exc:
        print(f"get_profile_text failed for {user_id}: {exc}")
    return None


def get_memory_context(user_id: str) -> dict:
    """返回完整记忆上下文：长期画像 + 随聊随记的事实清单。"""
    try:
        result = (
            supabase.table("user_memory")
            .select("profile_text, facts")
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "profile_text": row.get("profile_text"),
                "facts": row.get("facts") or [],
            }
    except Exception as exc:
        print(f"get_memory_context failed for {user_id}: {exc}")
    return {"profile_text": None, "facts": []}


def _is_duplicate_fact(fact: str, existing: list[str]) -> bool:
    for item in existing:
        if fact == item or fact in item or item in fact:
            return True
    return False


def add_fact(user_id: str, fact: str) -> bool:
    """随聊随记：追加一条短事实。上限 15 条，超了挤掉最旧的；重复不记。"""
    fact = (fact or "").strip()
    if not fact:
        return False
    if len(fact) > MAX_FACT_LENGTH:
        fact = fact[:MAX_FACT_LENGTH]

    context = get_memory_context(user_id)
    facts = list(context["facts"])
    if _is_duplicate_fact(fact, facts):
        return False

    facts.append(fact)
    if len(facts) > MAX_FACTS:
        facts = facts[-MAX_FACTS:]

    try:
        supabase.table("user_memory").upsert(
            {
                "user_id": user_id,
                "facts": facts,
                "updated_at": _now().isoformat(),
            }
        ).execute()
        return True
    except Exception as exc:
        print(f"add_fact failed for {user_id}: {exc}")
        return False


def _build_task_digest(tasks: list[dict]) -> dict:
    now = _now()
    total = len(tasks)
    done = [t for t in tasks if t.get("status") == "done"]
    overdue = []
    for task in tasks:
        remind_time = task.get("remind_time")
        if not remind_time or task.get("status") in {"done", "cancelled"}:
            continue
        try:
            remind_at = datetime.fromisoformat(remind_time.replace("Z", "+00:00"))
            if remind_at < now:
                overdue.append(task)
        except ValueError:
            continue

    categories = Counter((t.get("category") or "其他") for t in tasks)
    overdue_categories = Counter((t.get("category") or "其他") for t in overdue)
    notes = [t.get("progress_note") for t in tasks if t.get("progress_note")]

    return {
        "总任务数": total,
        "已完成数": len(done),
        "完成率": f"{round(len(done) / total * 100)}%" if total else "无数据",
        "当前逾期数": len(overdue),
        "分类分布": dict(categories),
        "逾期集中的分类": dict(overdue_categories),
        "近期任务内容示例": [t.get("content") for t in tasks[:20]],
        "近期进展备注示例": notes[:10],
    }


def refresh_user_memory(user_id: str) -> bool:
    cutoff = (_now() - timedelta(days=60)).isoformat()
    result = (
        supabase.table("tasks")
        .select("content, category, status, remind_time, progress_note, created_at")
        .eq("user_id", user_id)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    tasks = result.data or []
    if not tasks:
        return False

    digest = _build_task_digest(tasks)
    profile_text = None

    if DEEPSEEK_API_KEY:
        try:
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(digest, ensure_ascii=False)},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            profile_text = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            print(f"refresh_user_memory ai failed for {user_id}: {exc}")

    if not profile_text:
        profile_text = (
            f"最近60天共 {digest['总任务数']} 件任务，完成率 {digest['完成率']}，"
            f"当前逾期 {digest['当前逾期数']} 件。分类分布：{digest['分类分布']}。"
        )

    supabase.table("user_memory").upsert(
        {
            "user_id": user_id,
            "profile_text": profile_text,
            "task_count": digest["总任务数"],
            "updated_at": _now().isoformat(),
        }
    ).execute()
    return True


def refresh_all_memories() -> None:
    """每周定时任务：为所有用户刷新画像。"""
    try:
        result = supabase.table("users").select("id").execute()
    except Exception as exc:
        print(f"refresh_all_memories list users failed: {exc}")
        return
    for user in result.data or []:
        try:
            refresh_user_memory(user["id"])
        except Exception as exc:
            print(f"refresh_user_memory failed for {user['id']}: {exc}")
