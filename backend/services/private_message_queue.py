"""私人留言的持久化调度与发送结果恢复。"""
from datetime import timedelta
import re

from services.private_message_policy import PrivateMessageError, as_time, SHANGHAI


def _update(service, row, values):
    rows = (service.db.table("private_message_outbox").update({
                **values, "updated_at": service.clock().isoformat()})
            .eq("space_id", row["space_id"]).eq("id", row["id"])
            .eq("status", row["status"]).eq("attempts", row["attempts"]).execute().data)
    return rows[0] if rows else None


def _fail(service, message, code):
    if message["status"] not in ("scheduled", "sending"):
        return None
    changed = service.change(message, {"status": "failed", "failure_code": code})
    if changed:
        service.enqueue(changed, "notice")
    return changed


def _safe_code(code, fallback):
    code = str(code or "")
    return code if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code) else fallback


def _render(service, message, kind):
    space = message["space_id"]
    source = service.member(space, message["sender_id"], active=False)
    target = service.member(space, message["recipient_id"], active=False)
    if kind == "delivery":
        when = as_time(message["scheduled_at"]).astimezone(SHANGHAI).strftime("%m月%d日 %H:%M")
        return f"【私人留言】\n来自：{source['name']}\n时间：{when}\n{message['content']}\n可回复：留言收到 / 回复留言：内容"
    summary = message["content"].replace("\n", " ")[:32]
    if kind == "receipt":
        return f"【留言回执】{target['name']}已确认收到：{summary}"
    if message["status"] == "sent":
        return f"【留言已发送】给{target['name']}：{summary}"
    if message.get("failure_code") == "TIME_EXPIRED":
        return "定时留言已超过发送时间15分钟，已暂停。请先重新安排时间，再确认发送。"
    if message["status"] == "uncertain":
        return "留言发送结果不确定，已暂停。请先向对方确认是否收到，不要直接重复发送。"
    return "留言发送失败，已暂停并保留记录，无需再取消。请检查收件人权限后重新安排。"


def _valid(service, message, row):
    target = message["recipient_id"] if row["kind"] == "delivery" else message["sender_id"]
    if row["recipient_id"] != target:
        return False
    service.member(row["space_id"], target)
    if row["kind"] == "delivery":
        service.member(row["space_id"], message["sender_id"])
        return (message["status"] == "sending"
                and row["operation_key"] == f"{message['id']}:delivery:{message['version']}")
    if row["kind"] == "receipt":
        return message["status"] == "sent" and bool(message.get("acknowledged_at"))
    return message["status"] in ("sent", "failed", "uncertain")


def _apply(service, row):
    message = service.system_message(row["space_id"], row["message_id"])
    if row["kind"] == "delivery":
        if message["status"] == "sending":
            if row["status"] == "sent":
                changed = service.change(message, {
                    "status": "sent", "sent_at": service.clock().isoformat(), "failure_code": None})
            else:
                changed = service.change(message, {
                    "status": row["status"], "failure_code": row.get("error_code") or "SEND_FAILED"})
            if not changed:
                return
            message = changed
        if message["status"] in ("sent", "failed", "uncertain"):
            service.enqueue(message, "notice")
    _update(service, row, {"applied": True})


def drain(service, space):
    if service.sender is None:
        return
    rows = (service.query("private_message_outbox", space).eq("applied", False)
            .order("created_at").limit(1000).execute().data)
    for row in rows:
        if row["status"] == "sending":
            if service.clock() - as_time(row["updated_at"]) < timedelta(minutes=5):
                continue
            changed = _update(service, row, {"status": "uncertain", "error_code": "STALE_SENDING"})
            if not changed:
                continue
            row = changed
        if row["status"] == "pending":
            message = service.system_message(space, row["message_id"])
            if (row["kind"] == "delivery" and message["status"] == "sending"
                    and service.clock() - as_time(message["scheduled_at"]) > timedelta(minutes=15)):
                if _update(service, row, {"status": "cancelled", "applied": True}):
                    _fail(service, message, "TIME_EXPIRED")
                continue
            try:
                valid = _valid(service, message, row)
            except PrivateMessageError:
                valid = False
            if not valid:
                changed = _update(service, row, {"status": "cancelled", "applied": True})
                if changed and row["kind"] == "delivery":
                    _fail(service, message, "PARTICIPANT_DISABLED")
                continue
            claimed = _update(service, row, {"status": "sending", "attempts": row["attempts"] + 1})
            if not claimed:
                continue
            row = claimed
            try:
                recipient = service.member(space, row["recipient_id"])
                result = service.sender(recipient["wecom_userid"], _render(service, message, row["kind"]))
                outcome = result if isinstance(result, str) else getattr(result, "status", "uncertain")
                error = None if outcome == "sent" else _safe_code(
                    getattr(result, "error_code", None), "SEND_FAILED" if outcome == "failed" else "OUTCOME_UNKNOWN")
                if outcome not in ("sent", "failed", "uncertain"):
                    outcome, error = "uncertain", "OUTCOME_UNKNOWN"
            except Exception:
                outcome, error = "uncertain", "SENDER_EXCEPTION"
            saved = _update(service, row, {"status": outcome, "error_code": error})
            if not saved:
                continue
            row = saved
        if row["status"] == "failed" and row["attempts"] < 2:
            _update(service, row, {"status": "pending"})
            continue
        if row["status"] in ("sent", "failed", "uncertain", "cancelled"):
            _apply(service, row)


def scan(service, space):
    if service.sender is None:
        return
    drain(service, space)
    now = service.clock()
    expired = (service.query("private_messages", space).eq("status", "draft")
               .lte("created_at", (now - timedelta(hours=24)).isoformat())
               .order("created_at").limit(1000).execute().data)
    due = (service.query("private_messages", space).eq("status", "scheduled")
           .lte("scheduled_at", now.isoformat())
           .order("scheduled_at").limit(1000).execute().data)
    sending = (service.query("private_messages", space).eq("status", "sending")
               .order("updated_at").limit(1000).execute().data)
    for message in [*expired, *due, *sending]:
        if message["status"] == "draft" and now - as_time(message["created_at"]) >= timedelta(hours=24):
            service.change(message, {"status": "expired"})
        elif message["status"] == "scheduled" and as_time(message["scheduled_at"]) <= now:
            if now - as_time(message["scheduled_at"]) > timedelta(minutes=15):
                _fail(service, message, "TIME_EXPIRED")
                continue
            try:
                service.member(space, message["sender_id"])
                service.member(space, message["recipient_id"])
            except PrivateMessageError:
                _fail(service, message, "PARTICIPANT_DISABLED")
                continue
            changed = service.change(message, {"status": "sending"})
            if changed:
                service.enqueue(changed, "delivery")
        elif message["status"] == "sending":
            service.enqueue(message, "delivery")
    drain(service, space)
