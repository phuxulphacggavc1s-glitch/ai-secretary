"""企业微信与调度器的委派入口。"""
from config import WECOM_DELEGATION_ENABLED
from database import supabase
from services.delegation import DelegationService, DelegationError
from services.delegation_parser import is_delegation_request, parse_delegation
from services.wecom_delivery import bound_user_ids, resolve_supabase_user_id, resolve_wecom_userid, send_delegation_text, send_app_text
from services.wecom_inbound import reserve_inbound_message, mark_inbound_processed, mark_inbound_failed

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

def handle_delegation_message(userid, text, msg_id):
    owner = resolve_supabase_user_id(userid)
    if not WECOM_DELEGATION_ENABLED:
        if owner and is_delegation_request(text):
            send_app_text(userid, "委派功能尚未启用，请先完成数据库升级并开启发送。")
            return True
        return False
    service = get_service()
    if owner:
        from services.delegation_policy import parse_command
        if not parse_command(text) and not is_delegation_request(text):
            return False
    else:
        owners = [uid for uid in bound_user_ids()
                  if service.query("colleagues", uid).eq("wecom_userid", userid).eq("active", True).limit(1).execute().data]
        if not owners:
            return False
        if len(owners) != 1:
            send_app_text(userid, "这个账号关联了多位负责人，请联系负责人确认任务。")
            return True
        owner = owners[0]
    if not reserve_inbound_message(msg_id, owner, userid, text):
        return True
    try:
        if resolve_supabase_user_id(userid) == owner:
            reply = service.owner_command(owner, text)
            if reply is None and is_delegation_request(text):
                parsed = parse_delegation(text, service.list_colleagues(owner))
                task = service.create_task(owner, parsed)
                reply = (f"【已安排委派｜{task['approval_code']}】\n{task['content']}\n"
                         f"下达时间：{service.time_text(task['scheduled_at'])}\n到点会先请你批准。")
            if reply is None:
                # 此处只接管明确的委派命令，避免普通“确认”落入任务创建。
                reply = "没有待批准的委派任务。"
        else:
            reply = service.colleague_reply(owner, userid, text, msg_id) or "暂时没有需要你回复的委派任务。"
        send_app_text(userid, reply)
        mark_inbound_processed(msg_id, owner)
    except DelegationError as exc:
        send_app_text(userid, str(exc))
        mark_inbound_processed(msg_id, owner)
    except Exception:
        mark_inbound_failed(msg_id, owner, "delegation processing failed")
        send_app_text(userid, "委派处理失败，请稍后查看任务状态再操作。")
    return True
