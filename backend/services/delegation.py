"""委派任务审批、状态与持久化出站队列。"""
from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4
from services.delegation_policy import SHANGHAI, as_time, approval_expired, followup_due, followup_update

class DelegationError(ValueError):
    pass

class DelegationService:
    def __init__(self, db, sender, owner_lookup, clock=None):
        self.db, self.sender, self.owner_lookup = db, sender, owner_lookup
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def query(self, table, owner):
        return self.db.table(table).select("*").eq("owner_user_id", owner)

    def rows(self, table, owner, **filters):
        rows, offset = [], 0
        while True:
            query = self.query(table, owner)
            for key, value in filters.items():
                query = query.eq(key, value)
            page = query.order("created_at").range(offset, offset + 499).execute().data or []
            rows.extend(page)
            if len(page) < 500: return rows
            offset += 500

    def update(self, table, owner, row_id, data):
        return self.db.table(table).update(data).eq("owner_user_id", owner).eq("id", row_id).execute().data

    def change(self, task, data):
        version = task.get("version", 0)
        data = dict(data, version=version + 1, updated_at=self.clock().isoformat())
        rows = (self.db.table("delegated_tasks").update(data).eq("owner_user_id", task["owner_user_id"])
                .eq("id", task["id"]).eq("version", version).execute().data)
        return rows[0] if rows else None

    def event(self, task, kind, note="", actor="system"):
        self.db.table("delegated_task_events").insert({
            "owner_user_id": task["owner_user_id"], "task_id": task["id"],
            "actor_type": actor, "event_type": kind, "note": note[:2000],
        }).execute()

    def list_colleagues(self, owner):
        return self.rows("colleagues", owner)

    def save_colleague(self, owner, data, colleague_id=None):
        clean = {k: data[k] for k in ("name", "wecom_userid", "aliases", "active") if k in data}
        for key in ("name", "wecom_userid"):
            if key in clean:
                clean[key] = clean[key].strip()
                if not clean[key]: raise DelegationError("姓名和企业微信账号不能为空")
        if colleague_id:
            rows = self.query("colleagues", owner).eq("id", colleague_id).limit(1).execute().data
            if not rows: raise DelegationError("同事不存在")
            if "wecom_userid" in clean and clean["wecom_userid"] != rows[0]["wecom_userid"]:
                raise DelegationError("账号不能更换，请停用后新增同事")
            return self.update("colleagues", owner, colleague_id, dict(clean, updated_at=self.clock().isoformat()))[0]
        if not clean.get("name") or not clean.get("wecom_userid"): raise DelegationError("请填写姓名和企业微信账号")
        if self.query("colleagues", owner).eq("wecom_userid", clean["wecom_userid"]).limit(1).execute().data:
            raise DelegationError("这个企业微信账号已添加")
        return self.db.table("colleagues").insert(dict(clean, owner_user_id=owner, active=True)).execute().data[0]

    def get_task(self, owner, task_id):
        rows = self.query("delegated_tasks", owner).eq("id", task_id).limit(1).execute().data
        if not rows: raise DelegationError("委派任务不存在")
        return rows[0]

    def list_tasks(self, owner):
        colleagues = {c["id"]: c for c in self.list_colleagues(owner)}
        return [dict(t, colleague=colleagues.get(t["colleague_id"])) for t in self.rows("delegated_tasks", owner)]

    def events(self, owner, task_id):
        self.get_task(owner, task_id)
        return self.query("delegated_task_events", owner).eq("task_id", task_id).order("created_at").execute().data

    def create_task(self, owner, data):
        cols = self.query("colleagues", owner).eq("id", data.get("colleague_id")).limit(1).execute().data
        if not cols or not cols[0].get("active", True): raise DelegationError("请选择已启用的同事")
        content = (data.get("content") or "").strip()
        scheduled, due = as_time(data.get("scheduled_at")), as_time(data.get("due_at"))
        if not content or len(content) > 1000 or not scheduled: raise DelegationError("请填写任务内容和明确的下达时间")
        if len(content.encode("utf-8")) > 1200:
            raise DelegationError("任务内容过长，请缩短到400字以内")
        if scheduled < self.clock() - timedelta(minutes=1): raise DelegationError("下达时间不能早于当前时间")
        if due and due < scheduled: raise DelegationError("截止时间不能早于下达时间")
        now = self.clock().isoformat()
        row = dict(id=str(uuid4()), owner_user_id=owner, colleague_id=cols[0]["id"], content=content,
            scheduled_at=scheduled.isoformat(), due_at=due.isoformat() if due else None,
            approval_code=None, approval_code_history=[], approval_status="scheduled", delivery_status="not_sent",
            task_status="not_started", approval_revision=0, approval_requested_at=None, approval_reminded_at=None,
            sent_at=None, next_followup_at=None, followup_count=0, daily_reminder_count=0,
            reminder_count_date=None, last_colleague_reply_at=None, paused_reason=None, version=0,
            created_at=now, updated_at=now)
        task = self.db.table("delegated_tasks").insert(row).execute().data[0]
        self.event(task, "created", content, "owner")
        return task

    def colleague(self, task):
        rows = self.query("colleagues", task["owner_user_id"]).eq("id", task["colleague_id"]).limit(1).execute().data
        if not rows or not rows[0].get("active", True): raise DelegationError("接收同事已停用")
        return rows[0]

    def time_text(self, value):
        return as_time(value).astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M") if value else "未设置"

    def approval_text(self, task):
        return (f"【待批准下达】\n接收人：{self.colleague(task)['name']}\n"
                f"任务：{task['content']}\n截止：{self.time_text(task.get('due_at'))}\n"
                "回复：批准任务 / 取消任务 / 修改任务：新内容")

    def dispatch_text(self, task):
        return (f"【AI秘书代发任务】\n任务：{task['content']}\n"
                f"截止：{self.time_text(task.get('due_at'))}\n"
                "请回复：任务收到 / 任务完成 / 任务延期到具体时间 / 任务进展：内容")

    def followup_text(self, task):
        return f"【AI秘书跟进】\n{task['content']}\n请回复：任务收到 / 任务完成 / 任务进展：内容"

    def outbound_text(self, row, task):
        if row["kind"] in ("approval", "approval_reminder"):
            return self.approval_text(task)
        if row["kind"] == "dispatch":
            return self.dispatch_text(task)
        if row["kind"] == "followup":
            return self.followup_text(task)
        # Only the generated leading control header is rewritten, never body digits.
        return re.sub(r"^【(委派进展|委派过期|委派异常|已下达|委派未回复)｜[0-9]{4}】",
                      r"【\1】", row["content"], count=1)

    def enqueue(self, task, kind, recipient, text, suffix=""):
        if not recipient: raise DelegationError("负责人尚未绑定企业微信账号")
        owner, key = task["owner_user_id"], f"{task['id']}:{kind}:{suffix}"
        rows = self.query("delegation_outbox", owner).eq("operation_key", key).limit(1).execute().data
        if rows: return rows[0]
        try:
            return self.db.table("delegation_outbox").insert(dict(
                owner_user_id=owner, task_id=task["id"], operation_key=key, recipient_userid=recipient,
                content=text, kind=kind, status="pending", attempts=0, applied=False,
                updated_at=self.clock().isoformat())).execute().data[0]
        except Exception:
            rows = self.query("delegation_outbox", owner).eq("operation_key", key).limit(1).execute().data
            if rows: return rows[0]
            raise

    def notify(self, task, text, suffix):
        return self.enqueue(task, "notice", self.owner_lookup(task["owner_user_id"]), text, suffix)

    def action(self, owner, task_id, action, content=None, expected_version=None):
        task, now = self.get_task(owner, task_id), self.clock()
        if expected_version is not None and task["version"] != expected_version:
            raise DelegationError("任务状态或内容已变化，请重新选择")
        if action == "approve":
            if task["approval_status"] == "approved": return task
            if task["approval_status"] != "pending_approval" or not task.get("approval_requested_at"):
                raise DelegationError("任务尚未到批准时间，或已经取消/过期")
            if approval_expired(task, now): raise DelegationError("批准请求已过期，请重新安排")
            colleague = self.colleague(task)
            changed = self.change(task, dict(approval_status="approved", delivery_status="sending", approved_at=now.isoformat()))
            if changed:
                self.event(changed, "approved", actor="owner")
                self.enqueue(changed, "dispatch", colleague["wecom_userid"], self.dispatch_text(changed))
        elif action == "cancel":
            if task["delivery_status"] in ("sending", "sent", "uncertain"):
                raise DelegationError("任务已进入发送流程，不能取消下达；可直接联系同事")
            changed = self.change(task, dict(approval_status="cancelled", task_status="cancelled", next_followup_at=None))
            if changed: self.event(changed, "cancelled", actor="owner")
        elif action == "modify":
            if task["approval_status"] not in ("scheduled", "pending_approval"): raise DelegationError("只有待批准任务可以修改")
            content = (content or "").strip()
            if not content or len(content) > 1000: raise DelegationError("任务内容不能为空，最多1000字")
            if len(content.encode("utf-8")) > 1200:
                raise DelegationError("任务内容过长，请缩短到400字以内")
            changed = self.change(task, dict(content=content, approval_revision=task["approval_revision"] + 1,
                                            approval_requested_at=None, approval_reminded_at=None,
                                            approval_code=None,
                                            approval_code_history=[*(task.get("approval_code_history") or []),
                                                                   *([task["approval_code"]] if task.get("approval_code") else [])]))
            if changed:
                self.event(changed, "modified", content, "owner")
                if changed["approval_status"] == "pending_approval":
                    self.enqueue(changed, "approval", self.owner_lookup(owner), self.approval_text(changed), str(changed["approval_revision"]))
        elif action in ("complete", "reopen"):
            if task["delivery_status"] != "sent": raise DelegationError("尚未成功下达")
            changed = self.change(task, dict(task_status="completed" if action == "complete" else "in_progress",
                                            next_followup_at=None, paused_reason=None))
            if changed: self.event(changed, action, actor="owner")
        else: raise DelegationError("不支持这个操作")
        if expected_version is not None and not changed:
            raise DelegationError("任务状态或内容已变化，请重新选择")
        self.drain(owner)
        return self.get_task(owner, task_id)

    def owner_command(self, owner, text, userid=None):
        from services.delegation_commands import owner_command
        return owner_command(self, owner, text, userid)

    def colleague_reply(self, owner, userid, text, msg_id=None):
        from services.delegation_commands import colleague_reply
        return colleague_reply(self, owner, userid, text, msg_id)

    def record_colleague_reply(self, owner, userid, task_id, state, body, msg_id,
                               expected_version, receipt_proof):
        task = self.get_task(owner, task_id)
        colleague = self.colleague(task)
        if colleague["wecom_userid"].lower() != userid.lower():
            raise DelegationError("当前账号无权回复这条任务")
        if task["version"] != expected_version or task["task_status"] in ("completed", "cancelled"):
            raise DelegationError("任务状态已变化，请重新选择")
        if task["delivery_status"] != "sent":
            if (not receipt_proof or task["approval_status"] != "approved"
                    or task["delivery_status"] not in ("sending", "uncertain")):
                raise DelegationError("任务尚未成功下达，请先明确核对收到状态")
        delayed_due = None
        if state == "delayed":
            from services.delegation_parser import parse_delay
            delayed_due = parse_delay(body)
            if delayed_due and (delayed_due <= self.clock() or delayed_due < as_time(task["scheduled_at"])):
                delayed_due = None
        changed = self.change(task, dict(task_status=state, last_colleague_reply_at=self.clock().isoformat(),
                                        next_followup_at=None, paused_reason=None,
                                        **({"due_at": delayed_due.isoformat()} if delayed_due else {}),
                                        **({"delivery_status": "sent", "sent_at": self.clock().isoformat()}
                                           if task["delivery_status"] != "sent" else {})))
        if not changed:
            raise DelegationError("任务状态正在变化，请重新选择")
        self.event(changed, "colleague_reply", body, "colleague")
        self.notify(changed, f"【委派进展】\n{colleague['name']}：{body}",
                    f"reply:{msg_id or changed['version']}")
        self.drain(owner)
        if state == "delayed" and not delayed_due:
            return "已记录延期并同步负责人，请回复：任务延期到具体日期和时间。"
        return "已记录，并同步给负责人。"

    def scan(self, owner):
        now = self.clock()
        self.drain(owner)
        for task in self.rows("delegated_tasks", owner):
            try:
                approval = task["approval_status"]
                if approval in ("scheduled", "pending_approval") and approval_expired(task, now):
                    changed = self.change(task, dict(approval_status="expired", paused_reason="批准请求已过期"))
                    if changed:
                        self.event(changed, "expired")
                        self.notify(changed, f"【委派过期】未获批准，任务没有下达。", "expired")
                    continue
                if approval == "scheduled" and as_time(task["scheduled_at"]) <= now:
                    changed = self.change(task, dict(approval_status="pending_approval"))
                    if changed: self.enqueue(changed, "approval", self.owner_lookup(owner), self.approval_text(changed), str(changed["approval_revision"]))
                elif approval == "pending_approval":
                    if not task.get("approval_requested_at"):
                        self.enqueue(task, "approval", self.owner_lookup(owner), self.approval_text(task), str(task["approval_revision"]))
                    elif not task.get("approval_reminded_at") and now >= as_time(task["approval_requested_at"]) + timedelta(minutes=30):
                        self.enqueue(task, "approval_reminder", self.owner_lookup(owner), self.approval_text(task), str(task["approval_revision"]))
                elif approval == "approved" and task["delivery_status"] == "sending":
                    self.enqueue(task, "dispatch", self.colleague(task)["wecom_userid"], self.dispatch_text(task))
                if task["delivery_status"] == "sent" and followup_due(task, now):
                    self.enqueue(task, "followup", self.colleague(task)["wecom_userid"],
                                 self.followup_text(task),
                                 str(task["followup_count"] + 1))
            except DelegationError as exc: self.change(task, dict(paused_reason=str(exc)))
        self.drain(owner)

    def valid_outbound(self, row, task):
        if row["kind"] in ("approval", "approval_reminder", "notice"):
            owner_userid = self.owner_lookup(task["owner_user_id"])
            if not owner_userid or owner_userid.lower() != str(row["recipient_userid"]).lower():
                return False
        if row["kind"] in ("dispatch", "followup"):
            try:
                if self.colleague(task)["wecom_userid"] != row["recipient_userid"]: return False
            except DelegationError:
                return False
        kind = row["kind"]
        if kind in ("approval", "approval_reminder"):
            return (task["approval_status"] == "pending_approval"
                    and not approval_expired(task, self.clock())
                    and row["operation_key"] == f"{task['id']}:{kind}:{task['approval_revision']}")
        if kind == "dispatch": return task["approval_status"] == "approved" and task["delivery_status"] == "sending"
        if kind == "followup":
            return followup_due(task, self.clock()) and row["operation_key"].endswith(f":{task['followup_count'] + 1}")
        return True

    def drain(self, owner):
        if self.sender is None:
            return
        for row in self.rows("delegation_outbox", owner, applied=False):
            task = self.get_task(owner, row["task_id"])
            if row["status"] == "sending":
                if self.clock() - as_time(row["updated_at"]) >= timedelta(minutes=5):
                    self.update("delegation_outbox", owner, row["id"], dict(status="uncertain"))
                    row["status"] = "uncertain"
                else: continue
            if row["status"] == "pending":
                if not self.valid_outbound(row, task):
                    if row["kind"] == "dispatch" and task["delivery_status"] == "sending":
                        changed = self.change(task, dict(delivery_status="failed", paused_reason="接收同事已停用，未下达"))
                        if changed:
                            self.event(changed, "dispatch_cancelled", "接收同事已停用")
                            self.notify(changed, f"【委派异常】接收同事已停用，任务未下达。", "colleague-disabled")
                    self.update("delegation_outbox", owner, row["id"], dict(status="cancelled", applied=True))
                    continue
                claimed = (self.db.table("delegation_outbox").update(dict(status="sending", attempts=row["attempts"] + 1,
                           updated_at=self.clock().isoformat())).eq("owner_user_id", owner).eq("id", row["id"])
                           .eq("status", "pending").execute().data)
                if not claimed: continue
                row = claimed[0]
                task = self.get_task(owner, row["task_id"])
                if not self.valid_outbound(row, task):
                    if row["kind"] == "dispatch" and task["delivery_status"] == "sending":
                        changed = self.change(task, dict(delivery_status="failed", paused_reason="接收同事已停用，未下达"))
                        if changed:
                            self.event(changed, "dispatch_cancelled", "接收同事已停用")
                            self.notify(changed, "【委派异常】接收同事已停用，任务未下达。", "colleague-disabled")
                    self.update("delegation_outbox", owner, row["id"], dict(status="cancelled", applied=True))
                    continue
                try:
                    result = self.sender(row["recipient_userid"], self.outbound_text(row, task))
                    status = result if result in ("sent", "failed", "uncertain") else "uncertain"
                except Exception: status = "uncertain"
                if status == "failed" and row["attempts"] < 2: status = "pending"
                self.update("delegation_outbox", owner, row["id"], dict(status=status, updated_at=self.clock().isoformat()))
                row["status"] = status
            if row["status"] in ("sent", "failed", "uncertain") and not row.get("applied"): self.apply_delivery(row)

    def apply_delivery(self, row):
        owner = row["owner_user_id"]
        task = self.get_task(owner, row["task_id"])
        now, kind, status = self.clock(), row["kind"], row["status"]
        stale_approval = (kind in ("approval", "approval_reminder") and
                          row["operation_key"] != f"{task['id']}:{kind}:{task['approval_revision']}")
        answered_followup = (kind == "followup" and task["task_status"] != "awaiting_reply"
                             and not (status == "sent" and task["task_status"] == "unresponsive"))
        if stale_approval or answered_followup:
            self.update("delegation_outbox", owner, row["id"], dict(applied=True))
            return
        updates = {}
        if status == "sent":
            if (kind == "approval" and task["approval_status"] == "pending_approval" and not task.get("approval_requested_at")
                    and row["operation_key"] == f"{task['id']}:approval:{task['approval_revision']}"):
                updates = dict(approval_requested_at=now.isoformat(), paused_reason=None)
            elif (kind == "approval_reminder" and not task.get("approval_reminded_at")
                  and task["approval_status"] == "pending_approval"
                  and row["operation_key"] == f"{task['id']}:approval_reminder:{task['approval_revision']}"):
                updates = dict(approval_reminded_at=now.isoformat())
            elif kind == "dispatch" and task["delivery_status"] == "sending":
                updates = dict(delivery_status="sent", task_status="awaiting_reply", sent_at=now.isoformat(),
                               next_followup_at=(now + timedelta(minutes=30)).isoformat())
            elif kind == "followup" and task["task_status"] == "awaiting_reply":
                if int(row["operation_key"].rsplit(":", 1)[1]) == task["followup_count"] + 1:
                    updates = followup_update(task, now)
        elif kind != "notice" and not (kind == "dispatch" and task["delivery_status"] == "sent"):
            updates = dict(paused_reason="发送结果不确定，请先确认是否收到" if status == "uncertain" else "发送失败")
            if kind == "dispatch": updates["delivery_status"] = status
            elif kind == "followup": updates.update(next_followup_at=None, task_status="unresponsive")
        if updates:
            changed = self.change(task, updates)
            if not changed: return
            self.event(changed, f"{kind}_{status}", updates.get("paused_reason") or "")
            if status != "sent":
                self.notify(changed, f"【委派异常】{updates['paused_reason']}，已暂停自动发送。",
                            row["operation_key"] + ":error")
            elif kind == "dispatch":
                self.notify(changed, f"【已下达】{task['content']}", "dispatched")
            elif kind == "followup" and changed["task_status"] == "unresponsive":
                self.notify(changed, f"【委派未回复】已催办两次，仍未收到回复，自动催办已暂停。", "unresponsive")
        # 出站成功后本地状态写入和通知入队之间崩溃，也能补齐负责人回执。
        if status == "sent" and kind == "dispatch" and self.get_task(owner, task["id"])["delivery_status"] == "sent":
            self.notify(task, f"【已下达】{task['content']}", "dispatched")
        if status == "sent" and kind == "followup" and self.get_task(owner, task["id"])["task_status"] == "unresponsive":
            self.notify(task, f"【委派未回复】已催办两次，自动催办已暂停。", "unresponsive")
        self.update("delegation_outbox", owner, row["id"], dict(applied=True))
