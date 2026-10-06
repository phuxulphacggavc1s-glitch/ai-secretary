from copy import deepcopy
from datetime import timedelta
import pytest

from services.delegation import DelegationError
from test_delegation import env, create, NOW


def task(env, content="订单1024需要核对", future=False):
    service, _, _, _, colleague = env
    return service.create_task("u1", {
        "colleague_id": colleague["id"], "content": content,
        "scheduled_at": (NOW + timedelta(hours=1) if future else NOW).isoformat(),
    })


def context(env, userid):
    return next(r for r in env[1].rows["delegation_command_contexts"] if r["actor_userid"] == userid.lower())


def ready(env, count=2):
    service = env[0]
    tasks = [task(env, f"核对订单{1024 + n}") for n in range(count)]
    service.scan("u1")
    return tasks


def test_new_tasks_have_no_code_or_generator(env):
    item = task(env)
    assert item["approval_code"] is None
    assert not hasattr(env[0], "new_code")


def test_legacy_task_templates_keep_body_digits_but_remove_controls(env):
    service, db, sent, current, _ = env
    item = task(env, "订单7859，数量1024，不要改写数字")
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.scan("u1")
    service.owner_command("u1", "批准任务")
    current[0] += timedelta(minutes=30)
    service.scan("u1")
    assert [u for u, _ in sent].count("ZhangSan") == 2
    for _, text in sent:
        assert "｜7859" not in text and "同意 7859" not in text and "7859 收到" not in text
    assert any("订单7859，数量1024，不要改写数字" in text for _, text in sent)


def test_formal_tasks_still_wait_for_due_owner_approval(env):
    item = task(env)
    env[0].scan("u1")
    assert env[0].get_task("u1", item["id"])["approval_status"] == "pending_approval"
    assert not [u for u, _ in env[2] if u == "ZhangSan"]


def test_owner_menu_is_actor_scoped_versioned_and_claimed_once(env):
    service, _, sent, _, _ = env
    items = ready(env)
    menu = service.owner_command("u1", "批准任务", userid="OWNER")
    assert "1." in menu and "2." in menu and "短码" not in menu
    saved = deepcopy(context(env, "owner"))
    assert saved["operation"] == "approve"
    assert saved["expires_at"] == (NOW + timedelta(minutes=10)).isoformat()
    assert all(set(c) == {"id", "version"} for c in saved["candidates"])
    result = service.owner_command("u1", "1", userid="Owner")
    assert "下达" in result
    assert len([u for u, _ in sent if u == "ZhangSan"]) == 1
    service.owner_command("u1", "1", userid="Owner")
    assert len([u for u, _ in sent if u == "ZhangSan"]) == 1
    assert sum(service.get_task("u1", t["id"])["approval_status"] == "approved" for t in items) == 1


@pytest.mark.parametrize("operation", ["取消任务", "修改任务：重新核对订单"])
def test_owner_can_select_scheduled_tasks_without_codes(env, operation):
    service = env[0]
    items = [task(env, "第一条", True), task(env, "第二条", True)]
    menu = service.owner_command("u1", operation)
    assert "1." in menu and "2." in menu
    service.owner_command("u1", "1")
    changed = service.get_task("u1", context(env, "Owner")["candidates"][0]["id"])
    assert changed["approval_status"] == "cancelled" if operation == "取消任务" else changed["content"] == "重新核对订单"
    assert not [u for u, _ in env[2] if u == "ZhangSan"]


def test_modified_version_cannot_be_approved_by_old_menu(env):
    service = env[0]
    ready(env)
    service.owner_command("u1", "批准任务")
    selected = deepcopy(context(env, "Owner")["candidates"][0])
    service.action("u1", selected["id"], "modify", "未经旧选择授权的新内容")
    response = service.owner_command("u1", "1")
    assert "变化" in response or "重新" in response
    assert not [u for u, _ in env[2] if u == "ZhangSan"]


def test_context_expiry_and_foreign_owner_cannot_authorize(env):
    service, _, sent, current, _ = env
    ready(env)
    service.owner_command("u1", "同意")
    with pytest.raises(DelegationError):
        service.owner_command("u1", "1", userid="Stranger")
    current[0] += timedelta(minutes=10)
    result = service.owner_command("u1", "1")
    assert "过期" in result or "重新" in result
    assert not [u for u, _ in sent if u == "ZhangSan"]


def test_context_claim_race_cannot_execute_second_choice(monkeypatch, env):
    service = env[0]
    ready(env)
    service.owner_command("u1", "同意")
    from services import delegation_commands as commands
    original = commands.claim_context
    def lost_claim(*args):
        original(*args)
        return False
    monkeypatch.setattr(commands, "claim_context", lost_claim)
    response = service.owner_command("u1", "1")
    assert "处理" in response or "变化" in response
    assert not [u for u, _ in env[2] if u == "ZhangSan"]


def test_legacy_code_works_only_until_content_is_modified(env):
    service, db, sent, _, _ = env
    item = task(env)
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.scan("u1")
    changed = service.action("u1", item["id"], "modify", "新正文")
    assert changed["approval_code"] is None
    service.owner_command("u1", "同意 7859")
    assert not [u for u, _ in sent if u == "ZhangSan"]
    service.owner_command("u1", "批准任务")
    assert len([u for u, _ in sent if u == "ZhangSan"]) == 1


def test_legacy_uncoded_approval_still_requires_due_time(env):
    service, db, sent, _, _ = env
    item = task(env, future=True)
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.owner_command("u1", "同意 7859")
    service.scan("u1")
    assert service.get_task("u1", item["id"])["approval_status"] == "scheduled"
    assert sent == []


def test_multiple_colleague_replies_use_only_own_tasks_and_versions(env):
    service = env[0]
    items = ready(env)
    for item in items:
        service.action("u1", item["id"], "approve")
    menu = service.colleague_reply("u1", "zhangsan", "任务收到", "ack-start")
    assert "1." in menu and "2." in menu
    saved = deepcopy(context(env, "zhangsan"))
    assert saved["operation"] == "reply"
    service.colleague_reply("u1", "ZhangSan", "1", "ack-choice")
    chosen = saved["candidates"][0]["id"]
    assert service.get_task("u1", chosen)["task_status"] == "acknowledged"
    untouched = next(i for i in items if i["id"] != chosen)
    assert service.get_task("u1", untouched["id"])["task_status"] == "awaiting_reply"
    service.colleague_reply("u1", "ZhangSan", "1", "ack-choice-repeat")
    assert service.get_task("u1", untouched["id"])["task_status"] == "awaiting_reply"


def test_numeric_without_context_is_not_colleague_progress(env):
    service = env[0]
    item = ready(env, 1)[0]
    service.action("u1", item["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "123", "plain-number")
    assert service.get_task("u1", item["id"])["task_status"] == "awaiting_reply"


def test_disabled_colleague_cannot_claim_saved_menu(env):
    service, _, _, _, colleague = env
    for item in ready(env):
        service.action("u1", item["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "任务完成")
    service.save_colleague("u1", {"active": False}, colleague["id"])
    with pytest.raises(DelegationError):
        service.colleague_reply("u1", "ZhangSan", "1")


def test_other_enabled_colleague_cannot_view_or_reply(env):
    service = env[0]
    item = ready(env, 1)[0]
    service.action("u1", item["id"], "approve")
    service.save_colleague("u1", {"name": "李四", "wecom_userid": "LiSi"})
    result = service.colleague_reply("u1", "LiSi", "任务完成")
    assert not result or "订单1024" not in result
    assert service.get_task("u1", item["id"])["task_status"] == "awaiting_reply"


def test_uncertain_delivery_requires_explicit_task_receipt(env):
    service = env[0]
    item = ready(env, 1)[0]
    service.sender = lambda u, b: "uncertain" if u == "ZhangSan" else "sent"
    service.action("u1", item["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "收到")
    assert service.get_task("u1", item["id"])["delivery_status"] == "uncertain"
    service.colleague_reply("u1", "ZhangSan", "任务收到")
    assert service.get_task("u1", item["id"])["delivery_status"] == "sent"


def test_negative_task_receipt_does_not_resolve_uncertain(env):
    service = env[0]
    item = ready(env, 1)[0]
    service.sender = lambda u, b: "uncertain" if u == "ZhangSan" else "sent"
    service.action("u1", item["id"], "approve")
    service.colleague_reply("u1", "ZhangSan", "任务没有收到")
    assert service.get_task("u1", item["id"])["delivery_status"] == "uncertain"


def test_legacy_queued_approval_is_regenerated_at_send_boundary(env):
    service, db, sent, _, _ = env
    item = task(env, "订单7859不能删除")
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    sender, service.sender = service.sender, None
    service.scan("u1")
    row = db.rows["delegation_outbox"][0]
    row["content"] = "【待批准下达｜7859】\n旧模板\n同意 7859"
    service.sender = sender
    service.drain("u1")
    assert "订单7859不能删除" in sent[0][1]
    assert "｜7859" not in sent[0][1] and "同意 7859" not in sent[0][1]
    before = len(sent)
    row["content"] = "【待批准下达｜7859】"
    service.drain("u1")
    assert len(sent) == before


def test_pending_legacy_progress_notice_preserves_body_digits(env):
    service, db, sent, _, _ = env
    item = task(env)
    service.enqueue(item, "notice", "Owner", "【委派进展｜7859】\n张三：订单7859已核对", "reply:old")
    service.drain("u1")
    assert sent[-1][1] == "【委派进展】\n张三：订单7859已核对"


def test_cancel_menu_can_include_disabled_colleague(env):
    service, _, _, _, colleague = env
    task(env, "第一条", True)
    task(env, "第二条", True)
    service.save_colleague("u1", {"active": False}, colleague["id"])
    response = service.owner_command("u1", "取消任务")
    assert "1." in response and "2." in response
    service.owner_command("u1", "1")
    assert sum(t["approval_status"] == "cancelled" for t in service.rows("delegated_tasks", "u1")) == 1


def test_approval_revision_is_rechecked_after_outbox_claim(monkeypatch, env):
    service, db, sent, _, _ = env
    item = task(env, "旧正文不能送出")
    sender, service.sender = service.sender, None
    service.scan("u1")
    original, raced = service.valid_outbound, [False]
    def valid(row, observed):
        result = original(row, observed)
        if result and row["kind"] == "approval" and not raced[0]:
            raced[0] = True
            service.change(observed, {"content": "新正文须重新批准", "approval_revision": 1})
        return result
    monkeypatch.setattr(service, "valid_outbound", valid)
    service.sender = sender
    service.drain("u1")
    assert not sent
    assert db.rows["delegation_outbox"][0]["status"] == "cancelled"
    assert service.get_task("u1", item["id"])["approval_requested_at"] is None


def test_delegation_menu_invalidates_only_actors_private_context(env):
    service, db, _, _, _ = env
    db.rows["private_message_participants"] = [
        {"id": "private-owner", "space_id": "u1", "wecom_userid": "Owner"},
        {"id": "private-other", "space_id": "u1", "wecom_userid": "Other"},
    ]
    db.rows["private_message_contexts"] = [
        {"id": "private-menu", "space_id": "u1", "actor_id": "private-owner", "version": 0,
         "expires_at": (NOW + timedelta(minutes=10)).isoformat()},
        {"id": "other-menu", "space_id": "u1", "actor_id": "private-other", "version": 0,
         "expires_at": (NOW + timedelta(minutes=10)).isoformat()},
    ]
    ready(env)
    service.owner_command("u1", "批准任务", userid="OWNER")
    assert db.rows["private_message_contexts"][0]["expires_at"] == NOW.isoformat()
    assert db.rows["private_message_contexts"][0]["version"] == 1
    assert db.rows["private_message_contexts"][1]["version"] == 0


def test_unmodified_legacy_task_supports_existing_coded_approval_and_receipt(env):
    service, db, sent, _, _ = env
    item = task(env)
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.scan("u1")
    service.owner_command("u1", "同意 7859")
    service.colleague_reply("u1", "ZhangSan", "7859 完成", "legacy-receipt")
    assert service.get_task("u1", item["id"])["task_status"] == "completed"
    assert not any("｜7859" in text or "7859 收到" in text for _, text in sent)


@pytest.mark.parametrize("kind", ["dispatch", "followup"])
def test_legacy_delivery_control_text_is_regenerated_without_resend(env, kind):
    service, db, sent, current, _ = env
    item = task(env, "保留订单7859原文")
    db.rows["delegated_tasks"][0]["approval_code"] = "7859"
    service.scan("u1")
    sender = service.sender
    if kind == "dispatch":
        service.sender = None
        service.action("u1", item["id"], "approve")
    else:
        service.action("u1", item["id"], "approve")
        current[0] += timedelta(minutes=30)
        service.sender = None
        service.scan("u1")
    row = next(r for r in db.rows["delegation_outbox"] if r["kind"] == kind)
    row["content"] = "【旧控制文案｜7859】\n请回复：7859 收到"
    service.sender = sender
    before = len(sent)
    service.drain("u1")
    new_sent = sent[before:]
    body = next(text for u, text in new_sent if u == "ZhangSan")
    assert "保留订单7859原文" in body
    assert "｜7859" not in body and "7859 收到" not in body
    count = sum(u == "ZhangSan" for u, _ in sent)
    service.drain("u1")
    assert sum(u == "ZhangSan" for u, _ in sent) == count


@pytest.mark.parametrize("text", ["批准任务", "取消任务", "修改任务：不应改写"])
def test_colleague_owner_commands_do_not_become_progress(env, text):
    service = env[0]
    item = ready(env, 1)[0]
    service.action("u1", item["id"], "approve")
    result = service.colleague_reply("u1", "ZhangSan", text)
    assert "负责人" in result
    assert service.get_task("u1", item["id"])["task_status"] == "awaiting_reply"


@pytest.mark.parametrize("kind", ["approval", "notice"])
def test_owner_control_outbox_cannot_target_another_account(env, kind):
    service, db, sent, _, _ = env
    item = task(env)
    sender, service.sender = service.sender, None
    if kind == "approval":
        service.scan("u1")
    else:
        service.notify(item, "【已下达】订单1024", "dispatched")
    db.rows["delegation_outbox"][0]["recipient_userid"] = "OtherAccount"
    service.sender = sender
    service.drain("u1")
    assert not sent


def test_only_generated_leading_notice_header_is_rewritten(env):
    service = env[0]
    item = task(env)
    legacy = {"kind": "notice", "content": "【委派进展｜7859】\n张三：【委派进展｜1024】这是正文"}
    assert service.outbound_text(legacy, item) == "【委派进展】\n张三：【委派进展｜1024】这是正文"
    custom = {"kind": "notice", "content": "【用户自定义｜7859】这是正文"}
    assert service.outbound_text(custom, item) == custom["content"]
    created = {"kind": "notice", "content": "【已下达】【委派进展｜7859】这是任务原文"}
    assert service.outbound_text(created, item) == created["content"]


def test_failed_private_menu_invalidation_does_not_create_task_menu(monkeypatch, env):
    service, db, sent, _, _ = env
    ready(env)
    from services import delegation_commands as commands
    from services.private_message_policy import PrivateMessageError
    def fail(*args):
        raise PrivateMessageError("another menu changed")
    monkeypatch.setattr(commands, "expire_other_menu", fail)
    response = service.owner_command("u1", "批准任务")
    assert "重新" in response or "变化" in response
    assert not db.rows.get("delegation_command_contexts")
    assert not [u for u, _ in sent if u == "ZhangSan"]
