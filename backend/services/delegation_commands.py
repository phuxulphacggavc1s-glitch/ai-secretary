"""Authenticated, versioned code-free task selections."""
from datetime import timedelta
from uuid import uuid4

from services.delegation import DelegationError
from services.delegation_policy import as_time, approval_expired, parse_command, classify_reply
from services.private_message_policy import PrivateMessageError
from services.wecom_menu import MENU_LOCK, expire_other_menu


def enabled_colleague(service, owner, userid):
    matches = [c for c in service.list_colleagues(owner)
               if c["wecom_userid"].lower() == userid.lower()]
    if not matches:
        return None
    if len(matches) != 1 or not matches[0].get("active", True):
        raise DelegationError("当前账号未获准处理这些任务")
    return matches[0]


def authorize(service, owner, userid, owner_mode):
    if not isinstance(userid, str) or not 1 <= len(userid) <= 64:
        raise DelegationError("无法确认当前操作账号")
    if owner_mode:
        expected = service.owner_lookup(owner)
        if not expected or expected.lower() != userid.lower():
            raise DelegationError("只有本空间负责人可以批准或修改任务")
        return None
    return enabled_colleague(service, owner, userid)


def context(service, owner, userid):
    rows = (service.query("delegation_command_contexts", owner)
            .eq("actor_userid", userid.lower()).limit(1).execute().data)
    return rows[0] if rows else None


def claim_context(service, owner, userid, saved):
    now = service.clock().isoformat()
    rows = (service.db.table("delegation_command_contexts")
            .update({"expires_at": now, "updated_at": now, "version": saved["version"] + 1})
            .eq("owner_user_id", owner).eq("actor_userid", userid.lower())
            .eq("id", saved["id"]).eq("version", saved["version"]).execute().data)
    return bool(rows)


def eligible(service, owner, userid, operation, parameters, owner_mode):
    if owner_mode:
        states = ["pending_approval"] if operation == "approve" else ["scheduled", "pending_approval"]
        tasks = [t for state in states for t in service.rows("delegated_tasks", owner, approval_status=state)]
        if operation == "approve":
            tasks = [t for t in tasks if t.get("approval_requested_at") and not approval_expired(t, service.clock())]
        else:
            tasks = [t for t in tasks if t["delivery_status"] not in ("sending", "sent", "uncertain")
                     and t["task_status"] != "cancelled"]
    else:
        colleague = enabled_colleague(service, owner, userid)
        if not colleague:
            return []
        tasks = service.rows("delegated_tasks", owner, colleague_id=colleague["id"])
        tasks = [t for t in tasks if t["task_status"] not in ("completed", "cancelled")
                 and (t["delivery_status"] == "sent" or
                      (parameters.get("receipt_proof") and t["approval_status"] == "approved"
                       and t["delivery_status"] in ("sending", "uncertain")))]
    code = parameters.get("code")
    if code:
        tasks = [t for t in tasks if t.get("approval_code") == code]
    return sorted(tasks, key=lambda t: (t["created_at"], t["id"]), reverse=True)


def menu(service, owner, userid, operation, tasks, parameters):
    tasks = tasks[:20]
    try:
        expire_other_menu(service.db, owner, userid, "delegation", service.clock())
    except PrivateMessageError:
        raise DelegationError("另一组选项已变化，请重新发起任务操作") from None
    now = service.clock()
    data = {"operation": operation, "candidates": [
                {"id": t["id"], "version": t["version"]} for t in tasks],
            "parameters": parameters, "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "updated_at": now.isoformat()}
    old = context(service, owner, userid)
    if old:
        rows = (service.db.table("delegation_command_contexts")
                .update({**data, "version": old["version"] + 1})
                .eq("owner_user_id", owner).eq("actor_userid", userid.lower())
                .eq("id", old["id"]).eq("version", old["version"]).execute().data)
        if not rows:
            raise DelegationError("任务选项正在变化，请重新发起操作")
    else:
        service.db.table("delegation_command_contexts").insert({
            **data, "id": str(uuid4()), "owner_user_id": owner,
            "actor_userid": userid.lower(), "version": 0, "created_at": now.isoformat(),
        }).execute()
    labels = {"approve": "批准下达", "cancel": "取消", "modify": "修改", "reply": "回复"}
    lines = [f"请选择要{labels[operation]}的任务，回复本次序号（10分钟有效，最近20条）："]
    budget = (1900 - len(lines[0].encode("utf-8")) - len(tasks)) // len(tasks)
    people = {c["id"]: c for c in service.list_colleagues(owner)}
    for number, task in enumerate(tasks, 1):
        name = people.get(task["colleague_id"], {"name": "同事"})["name"].encode("utf-8")[:24].decode("utf-8", "ignore")
        when = service.time_text(task["scheduled_at"])[5:]
        prefix = f"{number}. {name} {when}："
        summary = task["content"].replace("\n", " ").encode("utf-8")[:min(
            96, max(0, budget - len(prefix.encode("utf-8"))))].decode("utf-8", "ignore")
        lines.append(prefix + summary)
    return "\n".join(lines)


def perform(service, owner, userid, operation, task, parameters, owner_mode, msg_id=None):
    current = {t["id"]: t for t in eligible(service, owner, userid, operation, parameters, owner_mode)}
    observed = current.get(task["id"])
    if not observed or observed["version"] != task["version"]:
        raise DelegationError("任务状态或内容已变化，请重新选择")
    if not owner_mode:
        return service.record_colleague_reply(
            owner, userid, task["id"], parameters["state"], parameters["body"],
            msg_id, task["version"], parameters.get("receipt_proof", False))
    changed = service.action(owner, task["id"], operation, parameters.get("content"),
                             expected_version=task["version"])
    if operation == "modify":
        return service.approval_text(changed)
    if operation == "cancel":
        return "已取消下达。"
    return {"sent": "任务已下达。", "failed": "下达失败，已暂停。",
            "uncertain": "发送结果不确定，已暂停。请先确认同事是否收到。"}.get(
                changed["delivery_status"], "已批准，正在处理下达。")


def choose(service, owner, userid, number, owner_mode, msg_id=None):
    saved = context(service, owner, userid)
    if not saved:
        return "没有当前任务选择菜单，请重新发起任务操作。"
    if as_time(saved["expires_at"]) <= service.clock():
        claim_context(service, owner, userid, saved)
        return "任务选项已经过期，请重新发起操作。"
    if (saved["operation"] == "reply") == owner_mode:
        raise DelegationError("当前菜单不属于这类任务操作")
    if not 1 <= number <= len(saved["candidates"]):
        return "序号不在当前任务选项中。"
    selected = saved["candidates"][number - 1]
    tasks = eligible(service, owner, userid, saved["operation"], saved["parameters"], owner_mode)
    task = next((t for t in tasks if t["id"] == selected["id"]), None)
    if not task or task["version"] != selected["version"]:
        claim_context(service, owner, userid, saved)
        return "任务状态或内容已变化，请重新选择。"
    if not claim_context(service, owner, userid, saved):
        return "这个任务选择已经处理或正在变化，请查看状态。"
    return perform(service, owner, userid, saved["operation"], task,
                   saved["parameters"], owner_mode, msg_id)


def owner_command(service, owner, text, userid=None):
    userid = userid or service.owner_lookup(owner)
    authorize(service, owner, userid, True)
    with MENU_LOCK:
        try:
            if text.strip().isdigit():
                return choose(service, owner, userid, int(text.strip()), True)
            parsed = parse_command(text)
            if not parsed:
                return None
            operation, code, content = parsed
            parameters = {"content": content, "code": code}
            tasks = eligible(service, owner, userid, operation, parameters, True)
            if not tasks:
                return "没有匹配的可操作委派任务。"
            if len(tasks) > 1:
                return menu(service, owner, userid, operation, tasks, parameters)
            old = context(service, owner, userid)
            if old:
                claim_context(service, owner, userid, old)
            return perform(service, owner, userid, operation, tasks[0], parameters, True)
        except DelegationError as exc:
            return str(exc)


def colleague_reply(service, owner, userid, text, msg_id=None):
    colleague = authorize(service, owner, userid, False)
    if not colleague:
        return None
    with MENU_LOCK:
        try:
            if text.strip().isdigit():
                return choose(service, owner, userid, int(text.strip()), False, msg_id)
            if parse_command(text):
                return "只有负责人可以批准、取消或修改委派任务。"
            state, body, code = classify_reply(text)
            proof = state in ("acknowledged", "completed") and (
                text.strip().startswith("任务") or bool(code))
            parameters = {"state": state, "body": body, "code": code, "receipt_proof": proof}
            tasks = eligible(service, owner, userid, "reply", parameters, False)
            if not tasks:
                return None
            if len(tasks) > 1:
                return menu(service, owner, userid, "reply", tasks, parameters)
            old = context(service, owner, userid)
            if old:
                claim_context(service, owner, userid, old)
            return perform(service, owner, userid, "reply", tasks[0], parameters, False, msg_id)
        except DelegationError as exc:
            return str(exc)
