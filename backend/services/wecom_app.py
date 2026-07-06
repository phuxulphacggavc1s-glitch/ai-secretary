"""企业微信自建应用：发消息 + 处理用户在企业微信里发来的话（双向对话）。"""
from __future__ import annotations

import json
import time

import httpx

from config import (
    WECOM_APP_AGENT_ID,
    WECOM_APP_SECRET,
    WECOM_APP_USER_MAP,
    WECOM_CORP_ID,
)
from constants import EventType, PRIORITY_INT_MAP
from database import supabase
from services.followup import ensure_next_follow
from services.secretary_chat import chat

QYAPI = "https://qyapi.weixin.qq.com/cgi-bin"

_token_cache = {"token": None, "expires_at": 0.0}


def is_wecom_app_configured() -> bool:
    return bool(WECOM_CORP_ID and WECOM_APP_SECRET and WECOM_APP_AGENT_ID)


def _user_map() -> dict[str, str]:
    try:
        data = json.loads(WECOM_APP_USER_MAP or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as exc:
        print(f"WECOM_APP_USER_MAP invalid: {exc}")
        return {}


def get_access_token(force_refresh: bool = False) -> str | None:
    if not force_refresh and _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    try:
        response = httpx.get(
            f"{QYAPI}/gettoken",
            params={"corpid": WECOM_CORP_ID, "corpsecret": WECOM_APP_SECRET},
            timeout=10,
        )
        result = response.json()
        if result.get("errcode") == 0:
            _token_cache["token"] = result["access_token"]
            _token_cache["expires_at"] = time.time() + int(result.get("expires_in", 7200)) - 200
            return _token_cache["token"]
        print(f"wecom gettoken failed: {result}")
    except Exception as exc:
        print(f"wecom gettoken error: {exc}")
    return None


def send_app_text(wecom_userid: str, content: str) -> bool:
    token = get_access_token()
    if not token:
        return False
    payload = {
        "touser": wecom_userid,
        "msgtype": "text",
        "agentid": int(WECOM_APP_AGENT_ID),
        "text": {"content": content[:2000]},
    }
    try:
        result = httpx.post(f"{QYAPI}/message/send?access_token={token}", json=payload, timeout=10).json()
        if result.get("errcode") in (40014, 42001):
            token = get_access_token(force_refresh=True)
            if not token:
                return False
            result = httpx.post(f"{QYAPI}/message/send?access_token={token}", json=payload, timeout=10).json()
        if result.get("errcode") != 0:
            print(f"wecom send failed: {result}")
            return False
        return True
    except Exception as exc:
        print(f"wecom send error: {exc}")
        return False


def _create_task_from_parsed(user_id: str, parsed: dict) -> dict | None:
    priority_level = parsed.get("priority_level") or "B"
    data = {
        "user_id": user_id,
        "content": parsed.get("content") or "",
        "category": parsed.get("category") or "其他",
        "remind_time": parsed.get("remind_time"),
        "priority": PRIORITY_INT_MAP.get(priority_level, 1),
        "priority_level": priority_level,
    }
    if not data["content"]:
        return None
    data.update(ensure_next_follow(data))
    result = supabase.table("tasks").insert(data).execute()
    if not result.data:
        return None
    task = result.data[0]
    supabase.table("task_events").insert(
        {
            "task_id": task["id"],
            "user_id": user_id,
            "event_type": EventType.CREATED.value,
            "note": "task created via wecom chat",
        }
    ).execute()
    return task


def handle_incoming_text(wecom_userid: str, text: str) -> None:
    """后台任务：处理企业微信里用户发来的一句话，并把秘书回复推回去。"""
    text = (text or "").strip()[:500]
    if not text:
        return

    user_id = _user_map().get(wecom_userid)
    if not user_id:
        send_app_text(
            wecom_userid,
            f"你的企业微信账号（{wecom_userid}）还没绑定 AI 秘书。"
            "请在服务器 WECOM_APP_USER_MAP 环境变量里加上映射后重启服务。",
        )
        return

    try:
        result = chat(user_id, text)
    except Exception as exc:
        print(f"wecom chat failed for {wecom_userid}: {exc}")
        send_app_text(wecom_userid, "刚才处理出错了，稍后再试一次。")
        return

    if result.get("intent") == "create_task" and result.get("parsed"):
        task = _create_task_from_parsed(user_id, result["parsed"])
        if task:
            remind = task.get("remind_time")
            remind_text = f"提醒时间 {remind[:16].replace('T', ' ')}" if remind else "没识别到具体时间，暂未设提醒——需要的话回我一句「明天上午9点提醒」重新记一条"
            reply = f"✅ 已记下：{task['content']}（{task.get('category', '其他')} · {task.get('priority_level', 'B')}级）\n{remind_text}"
        else:
            reply = "这条待办没记成功，请再说一遍。"
    else:
        reply = result.get("reply") or "我在，你说。"

    send_app_text(wecom_userid, reply)
