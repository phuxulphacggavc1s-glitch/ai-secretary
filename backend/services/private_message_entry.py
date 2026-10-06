"""独立企业微信私人留言入口，正文不能回退到负责人业务。"""
from threading import RLock

from config import WECOM_PRIVATE_MESSAGES_ENABLED
from database import supabase
from services.private_message_policy import PrivateMessageError, as_time, is_private_request, parse_command
from services.private_message_service import PrivateMessageService
from services.wecom_delivery import bound_user_ids

_lock = RLock()


def get_service():
    from services.private_message_delivery import send_private_text
    return PrivateMessageService(supabase, send_private_text if WECOM_PRIVATE_MESSAGES_ENABLED else None)


def reply(userid, text):
    from services.private_message_delivery import send_private_text
    send_private_text(userid, text)


def find_actor(service, userid):
    actors = []
    for space in bound_user_ids():
        try:
            actors.append((space, service.participant(space, userid)))
        except PrivateMessageError:
            continue
    if not actors:
        raise PrivateMessageError("当前账号未开通私人留言")
    if len(actors) != 1:
        raise PrivateMessageError("无法唯一确定你的留言空间，请联系管理员")
    return actors[0]


def delegation_pending(service, space, userid):
    colleagues = (service.db.table("colleagues").select("id").eq("owner_user_id", space)
                  .eq("wecom_userid", userid).eq("active", True).limit(10).execute().data)
    if not colleagues:
        return False
    tasks = (service.db.table("delegated_tasks").select("id").eq("owner_user_id", space)
             .in_("colleague_id", [p["id"] for p in colleagues]).eq("delivery_status", "sent")
             .eq("task_status", "awaiting_reply").limit(1).execute().data)
    return bool(tasks)


def reserve(service, space, userid, msg_id):
    existing = (service.query("private_message_inbound", space).eq("msg_id", str(msg_id))
                .limit(1).execute().data)
    if existing:
        return False
    try:
        service.insert("private_message_inbound", space, {
            "msg_id": str(msg_id), "sender_userid": userid, "status": "processing",
        })
        return True
    except Exception:
        existing = (service.query("private_message_inbound", space).eq("msg_id", str(msg_id))
                    .limit(1).execute().data)
        if existing:
            return False
        raise


def finish(service, space, userid, msg_id, status):
    (service.db.table("private_message_inbound").update({
        "status": status, "updated_at": service.clock().isoformat()})
     .eq("space_id", space).eq("sender_userid", userid).eq("msg_id", str(msg_id)).execute())


def handle_private_message(userid, text, msg_id):
    text = str(text or "").strip()
    strong = (is_private_request(text) or text.startswith(("回复：", "回复:"))
              or text == "取消选择")
    if not WECOM_PRIVATE_MESSAGES_ENABLED:
        if strong:
            reply(userid, "私人留言尚未启用，正文没有进入待办或委派记录。")
            return True
        return False
    command = parse_command(text)
    if not strong and not text.isdigit() and not (command and command["operation"] == "ack"):
        return False
    with _lock:
        try:
            service = get_service()
            space, actor = find_actor(service, userid)
        except PrivateMessageError as exc:
            if strong:
                reply(userid, str(exc))
                return True
            return False
        except Exception:
            if strong:
                reply(userid, "私人留言暂不可用，正文未交给普通秘书，请联系管理员。")
                return True
            return False
        if not strong:
            if text.isdigit():
                context = service.context(space, actor)
                if not context:
                    return False
            elif not service.candidates(space, actor, "ack"):
                return False
        try:
            if not reserve(service, space, userid, msg_id):
                return True
            if text == "收到":
                try:
                    conflict = delegation_pending(service, space, userid)
                except Exception:
                    conflict = True
                if conflict:
                    reply(userid, "你同时有待回复委派。确认私人留言请回复“留言收到”；委派请带任务短码，避免确认错对象。")
                    finish(service, space, userid, msg_id, "processed")
                    return True
            response = service.handle(space, actor, text)
            finish(service, space, userid, msg_id, "processed")
            reply(userid, response)
        except PrivateMessageError as exc:
            finish(service, space, userid, msg_id, "processed")
            reply(userid, str(exc))
        except Exception:
            try:
                finish(service, space, userid, msg_id, "failed")
            except Exception:
                pass
            print("private message processing failed; inspect private service state")
            reply(userid, "私人留言处理暂未完成，请发送“我的留言”核对状态，不要连续重复发送正文。")
        return True


def scan_private_messages():
    if not WECOM_PRIVATE_MESSAGES_ENABLED:
        return
    service = get_service()
    for space in bound_user_ids():
        try:
            service.scan(space)
        except Exception:
            print("private message scan failed; inspect private service state")
