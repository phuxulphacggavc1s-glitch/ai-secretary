"""企业微信与调度器的正式委派任务入口。"""
from config import WECOM_DELEGATION_ENABLED
from database import supabase
from services.delegation import DelegationService, DelegationError
from services.delegation_parser import is_delegation_request, parse_delegation
from services.delegation_policy import parse_command
from services.wecom_delivery import bound_user_ids, resolve_supabase_user_id, resolve_wecom_userid, send_delegation_text, send_app_text
from services.wecom_inbound import reserve_inbound_message, mark_inbound_processed, mark_inbound_failed
from services.wecom_menu import MENU_LOCK


def get_service():
    return DelegationService(supabase, send_delegation_text if WECOM_DELEGATION_ENABLED else None,
                             resolve_wecom_userid)


def scan_delegations():
    if not WECOM_DELEGATION_ENABLED:
        return
    service = get_service()
    for owner in bound_user_ids():
        try:
            service.scan(owner)
        except Exception:
            print("delegation scan failed; check database migration and delivery state")


def resolve_actor(service, userid):
    mapped = resolve_supabase_user_id(userid)
    if mapped:
        expected = service.owner_lookup(mapped)
        if not expected or expected.lower() != userid.lower():
            raise DelegationError("无法确认当前负责人账号")
        return mapped, True
    matches = []
    for owner in bound_user_ids():
        expected = service.owner_lookup(owner)
        if expected and expected.lower() == userid.lower():
            matches.append((owner, True))
            continue
        colleagues = [c for c in service.list_colleagues(owner)
                      if c["wecom_userid"].lower() == userid.lower() and c.get("active", True)]
        if len(colleagues) > 1:
            raise DelegationError("当前账号关联不明确，请联系负责人确认")
        if colleagues:
            matches.append((owner, False))
    if len(matches) > 1:
        raise DelegationError("这个账号关联了多位负责人，请联系负责人确认任务")
    return matches[0] if matches else (None, False)


def handle_delegation_message(userid, text, msg_id):
    text = str(text or "").strip()
    formal = is_delegation_request(text)
    command = parse_command(text)
    if not WECOM_DELEGATION_ENABLED:
        if formal or command or text.startswith("任务"):
            send_app_text(userid, "委派功能尚未启用，请先完成数据库升级并开启发送。")
            return True
        return False
    with MENU_LOCK:
        service = get_service()
        try:
            owner, is_owner = resolve_actor(service, userid)
        except DelegationError as exc:
            send_app_text(userid, str(exc))
            return True
        if not owner:
            return False
        if text.isdigit():
            from services.delegation_commands import context
            if not context(service, owner, userid):
                return False
        elif is_owner and not command and not formal:
            return False
        if not reserve_inbound_message(msg_id, owner, userid, text):
            return True
        try:
            if is_owner:
                response = service.owner_command(owner, text, userid=userid)
                if response is None and formal:
                    parsed = parse_delegation(text, service.list_colleagues(owner))
                    task = service.create_task(owner, parsed)
                    response = (f"【已安排委派】\n{task['content']}\n"
                                f"下达时间：{service.time_text(task['scheduled_at'])}\n到点会先请你批准。")
                if response is None:
                    response = "没有待批准的委派任务。"
            else:
                response = service.colleague_reply(owner, userid, text, msg_id) or "暂时没有需要你回复的委派任务。"
            send_app_text(userid, response)
            mark_inbound_processed(msg_id, owner)
        except DelegationError as exc:
            send_app_text(userid, str(exc))
            mark_inbound_processed(msg_id, owner)
        except Exception:
            mark_inbound_failed(msg_id, owner, "delegation processing failed")
            send_app_text(userid, "委派处理失败，请稍后查看任务状态再操作。")
        return True
