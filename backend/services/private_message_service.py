"""双人私人留言及当前用户的无短码选择菜单。"""
from datetime import timedelta
from uuid import uuid4

from services.wecom_menu import expire_other_menu

from services.private_message_policy import (
    PrivateMessageError, as_time, parse_command, parse_request, parse_time,
    utcnow, validate_content, SHANGHAI,
)


class PrivateMessageService:
    def __init__(self, db, sender=None, clock=utcnow):
        self.db, self.sender, self.clock = db, sender, clock

    def query(self, table, space):
        return self.db.table(table).select("*").eq("space_id", space)

    def rows(self, table, space):
        return self.query(table, space).limit(1000).execute().data

    def participant(self, space, userid):
        matches = [p for p in self.rows("private_message_participants", space)
                   if p["wecom_userid"].lower() == str(userid).lower() and p["active"]]
        if len(matches) != 1:
            raise PrivateMessageError("你尚未获准使用私人留言")
        return matches[0]

    def member(self, space, pid, active=True):
        rows = self.query("private_message_participants", space).eq("id", pid).limit(1).execute().data
        if not rows or (active and not rows[0]["active"]):
            raise PrivateMessageError("留言参与人已停用或不存在")
        return rows[0]

    def actor(self, space, actor):
        if not isinstance(actor, dict):
            return self.participant(space, actor)
        current = self.member(space, actor["id"])
        if actor.get("space_id") != space or not actor.get("active"):
            raise PrivateMessageError("你尚未获准使用私人留言")
        return current

    def insert(self, table, space, data):
        now = self.clock().isoformat()
        payload = {"id": str(uuid4()), "space_id": space, "created_at": now, "updated_at": now, **data}
        return self.db.table(table).insert(payload).execute().data[0]

    def change(self, message, values):
        payload = {**values, "version": message["version"] + 1, "updated_at": self.clock().isoformat()}
        rows = (self.db.table("private_messages").update(payload).eq("space_id", message["space_id"])
                .eq("id", message["id"]).eq("version", message["version"])
                .eq("status", message["status"]).execute().data)
        return rows[0] if rows else None

    def system_message(self, space, mid):
        rows = self.query("private_messages", space).eq("id", mid).limit(1).execute().data
        if not rows:
            raise PrivateMessageError("留言不存在")
        return rows[0]

    def visible_message(self, space, actor, mid):
        actor = self.actor(space, actor)
        rows = (self.query("private_messages", space).eq("id", mid)
                .eq("sender_id", actor["id"]).limit(1).execute().data)
        if not rows:
            rows = (self.query("private_messages", space).eq("id", mid)
                    .eq("recipient_id", actor["id"]).eq("status", "sent").limit(1).execute().data)
        if not rows:
            raise PrivateMessageError("留言不存在或你没有查看权限")
        return rows[0]

    def visible(self, space, actor):
        own = (self.query("private_messages", space).eq("sender_id", actor["id"])
               .order("created_at", desc=True).limit(100).execute().data)
        incoming = (self.query("private_messages", space).eq("recipient_id", actor["id"]).eq("status", "sent")
                    .order("created_at", desc=True).limit(100).execute().data)
        return sorted({m["id"]: m for m in [*own, *incoming]}.values(),
                      key=lambda m: m["created_at"], reverse=True)

    def create_draft(self, space, actor, data, thread_id=None):
        target = self.member(space, data["recipient_id"])
        if target["id"] == actor["id"]:
            raise PrivateMessageError("请给其他参与同事留言")
        if thread_id is None:
            a, b = sorted([actor["id"], target["id"]])
            threads = (self.query("private_message_threads", space).eq("participant_a", a)
                       .eq("participant_b", b).limit(1).execute().data)
            if threads:
                thread_id = threads[0]["id"]
            else:
                try:
                    thread_id = self.insert("private_message_threads", space,
                                            {"participant_a": a, "participant_b": b})["id"]
                except Exception:
                    threads = (self.query("private_message_threads", space).eq("participant_a", a)
                               .eq("participant_b", b).limit(1).execute().data)
                    if not threads:
                        raise
                    thread_id = threads[0]["id"]
        else:
            threads = self.query("private_message_threads", space).eq("id", thread_id).limit(1).execute().data
            if not threads or {threads[0]["participant_a"], threads[0]["participant_b"]} != {actor["id"], target["id"]}:
                raise PrivateMessageError("你不能更换留言会话的参与人")
        return self.insert("private_messages", space, {
            "thread_id": thread_id, "sender_id": actor["id"], "recipient_id": target["id"],
            "content": validate_content(data["content"]), "delivery_mode": data["delivery_mode"],
            "scheduled_at": data.get("scheduled_at"), "status": "draft", "version": 0,
            "confirmed_at": None, "sent_at": None, "acknowledged_at": None, "failure_code": None,
        })

    def preview(self, space, message):
        target = self.member(space, message["recipient_id"], active=False)
        when = "确认后立即发送" if message["delivery_mode"] == "immediate" else (
            as_time(message["scheduled_at"]).astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M"))
        return f"【私人留言预览】\n给：{target['name']}\n发送时间：{when}\n{message['content']}\n回复：确认发送 / 修改留言：内容 / 取消留言"

    def candidates(self, space, actor, operation):
        if operation in ("confirm", "cancel", "modify", "retime"):
            states = ["draft"] if operation == "confirm" else ["draft", "scheduled"]
            return (self.query("private_messages", space).eq("sender_id", actor["id"])
                    .in_("status", states).order("created_at", desc=True).limit(100).execute().data)
        if operation == "ack":
            return (self.query("private_messages", space).eq("recipient_id", actor["id"])
                    .eq("status", "sent").is_("acknowledged_at", "null")
                    .order("created_at", desc=True).limit(100).execute().data)
        if operation == "reply":
            threads = []
            for party in ("participant_a", "participant_b"):
                threads.extend(self.query("private_message_threads", space).eq(party, actor["id"])
                               .limit(100).execute().data)
            latest = []
            for thread in threads:
                latest.extend(self.query("private_messages", space).eq("thread_id", thread["id"])
                              .eq("status", "sent").order("created_at", desc=True).limit(1).execute().data)
            return sorted(latest, key=lambda m: m["created_at"], reverse=True)
        rows = self.visible(space, actor)
        return rows[:20]

    def context(self, space, actor):
        rows = (self.query("private_message_contexts", space).eq("actor_id", actor["id"])
                .limit(1).execute().data)
        return rows[0] if rows else None

    def clear_context(self, space, actor, context=None):
        context = context or self.context(space, actor)
        if not context:
            return False
        rows = (self.db.table("private_message_contexts").delete().eq("space_id", space)
                .eq("actor_id", actor["id"]).eq("id", context["id"])
                .eq("version", context["version"]).execute().data)
        return bool(rows)

    def menu(self, space, actor, operation, messages, parameters):
        expire_other_menu(self.db, space, actor["wecom_userid"], "private", self.clock())
        messages = messages[:20]
        saved = {"operation": operation,
                 "candidates": [{"id": m["id"], "version": m["version"]} for m in messages],
                 "parameters": parameters, "expires_at": (self.clock() + timedelta(minutes=10)).isoformat()}
        previous = self.context(space, actor)
        if previous:
            rows = (self.db.table("private_message_contexts").update({
                        **saved, "version": previous["version"] + 1, "updated_at": self.clock().isoformat()})
                    .eq("space_id", space).eq("actor_id", actor["id"]).eq("id", previous["id"])
                    .eq("version", previous["version"]).execute().data)
            if not rows:
                raise PrivateMessageError("选择正在更新，请重新发起操作")
        else:
            self.insert("private_message_contexts", space, {**saved, "actor_id": actor["id"], "version": 0})
        labels = {"confirm": "确认发送", "view": "查看", "cancel": "取消", "modify": "修改",
                  "retime": "改时", "reply": "回复", "ack": "确认收到"}
        lines = [f"请选择要{labels.get(operation, '处理')}的留言，回复本次序号（10分钟有效，最近20条）："]
        budget = (1900 - len(lines[0].encode("utf-8")) - len(messages)) // len(messages)
        for n, m in enumerate(messages, 1):
            other = m["recipient_id"] if m["sender_id"] == actor["id"] else m["sender_id"]
            name = self.member(space, other, active=False)["name"].encode("utf-8")[:24].decode("utf-8", "ignore")
            when = as_time(m["scheduled_at"] or m["created_at"]).astimezone(SHANGHAI).strftime("%m-%d %H:%M")
            prefix, suffix = f"{n}. {name} {when}：", f"（{self.status_text(m)[:8]}）"
            available = min(96, max(0, budget - len((prefix + suffix).encode("utf-8"))))
            summary = m["content"].replace("\n", " ").encode("utf-8")[:available].decode("utf-8", "ignore")
            lines.append(prefix + summary + suffix)
        return "\n".join(lines)

    @staticmethod
    def status_text(message):
        return {"draft": "待你确认", "scheduled": "已定时", "sending": "发送中", "sent": "已发送",
                "failed": "已失败暂停", "uncertain": "结果不确定，已暂停", "cancelled": "已取消",
                "expired": "预览已过期"}.get(message["status"], message["status"])

    def choose(self, space, actor, number):
        context = self.context(space, actor)
        if not context:
            raise PrivateMessageError("没有当前选择菜单，请重新发送留言操作")
        if as_time(context["expires_at"]) <= self.clock():
            self.clear_context(space, actor, context)
            raise PrivateMessageError("这组选项已经过期，请重新发起操作")
        if not 1 <= number <= len(context["candidates"]):
            raise PrivateMessageError("序号不在当前选项中")
        selected = context["candidates"][number - 1]
        message = self.visible_message(space, actor, selected["id"])
        if message["version"] != selected["version"]:
            self.clear_context(space, actor, context)
            raise PrivateMessageError("留言状态已变化，请重新选择")
        if not self.clear_context(space, actor, context):
            raise PrivateMessageError("这个选择已经处理，请查看留言状态")
        return self.perform(space, actor, context["operation"], message, context["parameters"])

    def handle(self, space, actor, text):
        actor = self.actor(space, actor)
        text = str(text or "").strip()
        if text.isdigit():
            return self.choose(space, actor, int(text))
        if text == "取消选择":
            self.clear_context(space, actor)
            return "已取消当前选择，留言本身未取消。"
        command = parse_command(text)
        if not command:
            data = parse_request(text, self.rows("private_message_participants", space), self.clock())
            self.clear_context(space, actor)
            return self.preview(space, self.create_draft(space, actor, data))
        operation = command["operation"]
        parameters = {k: v for k, v in command.items() if k != "operation"}
        if operation in ("modify", "reply"):
            parameters["content"] = validate_content(parameters.get("content"))
        if operation == "retime":
            parameters["delivery_mode"], parameters["scheduled_at"] = parse_time(parameters["content"], self.clock())
        if operation == "reply":
            parameters["delivery_mode"], parameters["scheduled_at"] = parse_time(
                parameters.pop("time_text", None) or "立即发送", self.clock())
        messages = self.candidates(space, actor, operation)
        if not messages:
            return "没有匹配的私人留言。"
        if operation in ("list", "view") or len(messages) > 1:
            return self.menu(space, actor, "view" if operation == "list" else operation, messages, parameters)
        self.clear_context(space, actor)
        return self.perform(space, actor, operation, messages[0], parameters)

    def perform(self, space, actor, operation, message, parameters):
        eligible = {m["id"] for m in self.candidates(space, actor, operation)}
        if message["id"] not in eligible:
            raise PrivateMessageError("这条留言当前不能执行该操作")
        observed_version = message["version"]
        message = self.visible_message(space, actor, message["id"])
        if message["version"] != observed_version:
            raise PrivateMessageError("留言状态已变化，请重新选择")
        now = self.clock()
        if operation == "view":
            source = self.member(space, message["sender_id"], active=False)
            target = self.member(space, message["recipient_id"], active=False)
            return f"【私人留言】{source['name']} → {target['name']}\n{message['content']}\n状态：{self.status_text(message)}"
        if operation == "reply":
            other = message["recipient_id"] if message["sender_id"] == actor["id"] else message["sender_id"]
            data = {"recipient_id": other, **parameters}
            return self.preview(space, self.create_draft(space, actor, data, message["thread_id"]))
        if operation == "ack":
            changed = self.change(message, {"acknowledged_at": now.isoformat()})
            if changed:
                self.enqueue(changed, "receipt")
                self.drain(space)
            return "已确认收到，并同步给留言人。"
        if operation == "confirm":
            if now - as_time(message["created_at"]) >= timedelta(hours=24):
                self.change(message, {"status": "expired"})
                raise PrivateMessageError("预览已经过期，请重新安排留言")
            self.member(space, message["recipient_id"])
            scheduled = now if message["delivery_mode"] == "immediate" else as_time(message["scheduled_at"])
            if scheduled < now:
                raise PrivateMessageError("发送时间已过去，请先改时留言")
            changed = self.change(message, {"status": "scheduled", "confirmed_at": now.isoformat(),
                                            "scheduled_at": scheduled.isoformat(), "failure_code": None})
            if not changed:
                raise PrivateMessageError("留言状态正在变化，请查看后再操作")
            self.scan(space)
            return "已确认，留言将在指定时间发送；发送结果会私下通知你。"
        if operation == "cancel":
            changed = self.change(message, {"status": "cancelled"})
            if not changed:
                raise PrivateMessageError("留言已进入发送或正在变化，未取消")
            return "已取消这条留言。"
        values = {"status": "draft", "confirmed_at": None, "failure_code": None}
        if operation == "modify":
            values["content"] = parameters["content"]
        elif operation == "retime":
            values.update(delivery_mode=parameters["delivery_mode"], scheduled_at=parameters["scheduled_at"])
        changed = self.change(message, values)
        if not changed:
            raise PrivateMessageError("留言状态正在变化，请重新查看")
        return self.preview(space, changed)

    def enqueue(self, message, kind):
        suffix = str(message["version"]) if kind == "delivery" else "result" if kind == "notice" else "ack"
        key = f"{message['id']}:{kind}:{suffix}"
        space = message["space_id"]
        rows = self.query("private_message_outbox", space).eq("operation_key", key).limit(1).execute().data
        if rows:
            return rows[0]
        target = message["recipient_id"] if kind == "delivery" else message["sender_id"]
        try:
            return self.insert("private_message_outbox", space, {
                "message_id": message["id"], "recipient_id": target, "kind": kind,
                "operation_key": key, "status": "pending", "attempts": 0, "applied": False, "error_code": None,
            })
        except Exception:
            rows = self.query("private_message_outbox", space).eq("operation_key", key).limit(1).execute().data
            if rows:
                return rows[0]
            raise

    def scan(self, space):
        from services.private_message_queue import scan
        return scan(self, space)

    def drain(self, space):
        from services.private_message_queue import drain
        return drain(self, space)
