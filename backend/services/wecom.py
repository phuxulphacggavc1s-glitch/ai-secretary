from __future__ import annotations

import json
from typing import Any

import httpx

from config import FRONTEND_URL, WECOM_PHONE_MAP_JSON, WECOM_WEBHOOK_URL
from database import supabase


def _phone_map() -> dict[str, str]:
    try:
        data = json.loads(WECOM_PHONE_MAP_JSON or "{}")
    except json.JSONDecodeError as exc:
        print(f"WECOM_PHONE_MAP_JSON invalid: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(email).lower(): str(mobile) for email, mobile in data.items() if mobile}


def resolve_webhook(user_id: str) -> str | None:
    try:
        result = (
            supabase.table("users")
            .select("wecom_webhook")
            .eq("id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0].get("wecom_webhook") or WECOM_WEBHOOK_URL
    except Exception as exc:
        print(f"resolve_webhook failed for {user_id}: {exc}")
    return WECOM_WEBHOOK_URL


def resolve_mentioned_mobiles(user_id: str) -> list[str] | None:
    phone_map = _phone_map()
    if not phone_map:
        return None

    try:
        result = (
            supabase.table("users")
            .select("email")
            .eq("id", user_id)
            .execute()
        )
        if result.data:
            email = (result.data[0].get("email") or "").lower()
            mobile = phone_map.get(email)
            if mobile:
                return [mobile]
    except Exception as exc:
        print(f"resolve_mentioned_mobiles failed for {user_id}: {exc}")
    return None


def send_wecom(
    webhook: str | None,
    markdown: str,
    mentioned_mobiles: list[str] | None = None,
) -> bool:
    if not webhook:
        print("WECOM webhook missing")
        return False

    payload: dict[str, Any] = {
        "msgtype": "markdown",
        "markdown": {"content": markdown},
    }
    if mentioned_mobiles:
        payload["mentioned_mobile_list"] = mentioned_mobiles

    try:
        response = httpx.post(webhook, json=payload, timeout=10)
        response.raise_for_status()
        markdown_result = response.json()
        if markdown_result.get("errcode") != 0:
            print(f"send_wecom markdown failed: {markdown_result}")
            return False
        if mentioned_mobiles:
            mention_response = httpx.post(
                webhook,
                json={
                    "msgtype": "text",
                    "text": {
                        "content": "AI秘书提醒：请查看上一条督办消息并及时处理。",
                        "mentioned_mobile_list": mentioned_mobiles,
                    },
                },
                timeout=10,
            )
            mention_response.raise_for_status()
            mention_result = mention_response.json()
            if mention_result.get("errcode") != 0:
                print(f"send_wecom mention failed: {mention_result}")
                return False
        return True
    except Exception as exc:
        print(f"send_wecom failed: {exc}")
        return False


def build_reminder_markdown(task: dict) -> str:
    goal = task.get("goal") or "未填写"
    remind_time = task.get("remind_time") or "未设置"
    status = task.get("status") or "pending"
    task_id = task.get("id", "")
    task_link = f"{FRONTEND_URL.rstrip('/')}/tasks"
    if task_id:
        task_link = f"{task_link}?taskId={task_id}"

    return (
        "## AI秘书督办提醒\n"
        f"> 任务：{task.get('content', '未命名任务')}\n"
        f"> 目标：{goal}\n"
        f"> 截止时间：{remind_time}\n"
        f"> 当前状态：{status}\n\n"
        "请直接在应用里回复进展：\n"
        "1 已完成  2 已联系等待回复  3 遇到问题  4 需要延期\n\n"
        f"[打开任务详情]({task_link})"
    )
