"""AI 秘书主动消息的统一发送与审计入口。"""
from __future__ import annotations

from datetime import datetime, timezone

from database import supabase
from services.proactive_policy import evaluate_outreach
from services.wecom_delivery import resolve_wecom_userid, send_app_text


VALID_KINDS = {
    "morning_briefing",
    "task_followup",
    "s_escalation",
    "evening_review",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_secretary_message(
    user_id: str,
    content: str,
    kind: str,
    task_id: str | None = None,
    explicit_reminder: bool = False,
) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"unsupported outreach kind: {kind}")

    decision = evaluate_outreach(
        user_id=user_id,
        kind=kind,
        task_id=task_id,
        explicit_reminder=explicit_reminder,
    )
    if not decision["allowed"]:
        return {
            "sent": False,
            "outreach_id": None,
            "reason": decision["reason"],
            "skipped": True,
        }

    wecom_userid = resolve_wecom_userid(user_id)
    created = supabase.table("secretary_outreach").insert(
        {
            "user_id": user_id,
            "task_id": task_id,
            "kind": kind,
            "content": content,
            "status": "pending",
            "wecom_userid": wecom_userid,
        }
    ).execute()
    outreach_id = created.data[0]["id"] if created.data else None
    if not outreach_id:
        return {
            "sent": False,
            "outreach_id": None,
            "reason": "外联记录创建失败",
        }

    sent = bool(wecom_userid and send_app_text(wecom_userid, content))
    reason = None
    if not sent:
        reason = "企业微信发送失败" if wecom_userid else "企业微信账号未绑定"

    (
        supabase.table("secretary_outreach")
        .update(
            {
                "status": "sent" if sent else "failed",
                "sent_at": _now_iso() if sent else None,
                "failure_reason": reason,
            }
        )
        .eq("id", outreach_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {
        "sent": sent,
        "outreach_id": outreach_id,
        "reason": reason,
    }
