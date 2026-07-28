"""企业微信自建应用回调消息的业务处理。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from constants import EventType, PRIORITY_INT_MAP
from database import supabase
from services.followup import ensure_next_follow
from services.secretary_chat import chat
from services.wecom_delivery import resolve_supabase_user_id, send_app_text
from services.wecom_inbound import mark_inbound_failed, mark_inbound_processed, reserve_inbound_message
from services.wecom_reply import process_pending_task_reply


DEFAULT_TIMEZONE = "Asia/Shanghai"


def format_remind_time(value: str | None) -> str:
    if not value:
        return "没识别到具体时间，暂未设提醒——需要的话回我一句「明天上午9点提醒」重新记一条"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
        local_time = parsed.astimezone(ZoneInfo(DEFAULT_TIMEZONE))
        return f"提醒时间 {local_time:%Y-%m-%d %H:%M}"
    except (TypeError, ValueError):
        return f"提醒时间 {value[:16].replace('T', ' ')}"


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


def handle_incoming_text(wecom_userid: str, text: str, msg_id: str) -> None:
    """后台任务：处理企业微信消息，并把秘书回复推回去。"""
    text = (text or "").strip()[:500]
    if not text:
        return

    user_id = resolve_supabase_user_id(wecom_userid)
    if not user_id:
        send_app_text(
            wecom_userid,
            f"你的企业微信账号（{wecom_userid}）还没绑定 AI 秘书。"
            "请在服务器 WECOM_APP_USER_MAP 环境变量里加上映射后重启服务。",
        )
        return

    if not reserve_inbound_message(msg_id, user_id, wecom_userid, text):
        return

    try:
        handled = process_pending_task_reply(user_id, text)
        if handled and handled.get("handled"):
            send_app_text(wecom_userid, handled["reply"])
            mark_inbound_processed(msg_id, user_id)
            return

        result = chat(user_id, text)

        if result.get("intent") == "create_task" and result.get("parsed"):
            task = _create_task_from_parsed(user_id, result["parsed"])
            if task:
                remind_text = format_remind_time(task.get("remind_time"))
                reply = (
                    f"✅ 已记下：{task['content']}"
                    f"（{task.get('category', '其他')} · {task.get('priority_level', 'B')}级）\n"
                    f"{remind_text}"
                )
            else:
                reply = "这条待办没记成功，请再说一遍。"
        else:
            reply = result.get("reply") or "我在，你说。"

        send_app_text(wecom_userid, reply)
        mark_inbound_processed(msg_id, user_id)
    except Exception as exc:
        print(f"wecom message processing failed for {wecom_userid}: {exc}")
        try:
            mark_inbound_failed(msg_id, user_id, str(exc))
        except Exception as receipt_exc:
            print(f"wecom receipt update failed for {wecom_userid}: {receipt_exc}")
        send_app_text(wecom_userid, "刚才处理出错了，稍后再试一次。")
