from datetime import datetime, timezone

from database import supabase


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reserve_inbound_message(
    msg_id: str,
    user_id: str,
    wecom_userid: str,
    content: str,
) -> bool:
    existing = (
        supabase.table("wecom_inbound_messages")
        .select("id")
        .eq("msg_id", msg_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return False

    try:
        created = supabase.table("wecom_inbound_messages").insert(
            {
                "msg_id": msg_id,
                "user_id": user_id,
                "wecom_userid": wecom_userid,
                "content": content,
                "status": "processing",
            }
        ).execute()
        return bool(created.data)
    except Exception as exc:
        print(f"reserve inbound failed for {user_id}: {exc}")
        return False


def _finish(msg_id: str, user_id: str, status: str, reason: str | None = None) -> None:
    (
        supabase.table("wecom_inbound_messages")
        .update(
            {
                "status": status,
                "failure_reason": reason,
                "processed_at": _now_iso(),
            }
        )
        .eq("msg_id", msg_id)
        .eq("user_id", user_id)
        .execute()
    )


def mark_inbound_processed(msg_id: str, user_id: str) -> None:
    _finish(msg_id, user_id, "processed")


def mark_inbound_failed(msg_id: str, user_id: str, reason: str) -> None:
    _finish(msg_id, user_id, "failed", reason[:500])
