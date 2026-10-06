# Private Scheduled WeCom Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. In this workspace use available bounded worker tools and parent-led integration; unavailable named execution skills are not installed.

**Goal:** Four allowlisted users exchange private text messages immediately or at any future time without visible codes or owner approval.

**Architecture:** Separate participant-scoped service and six private tables. Persist draft confirmation and menu choices, use versioned updates and unique outbound operations, and intercept private commands before existing delegation/personal handlers. Keep sender and recipient content out of legacy inbound records and AI requests.

**Tech Stack:** Existing Python FastAPI, Supabase, APScheduler, httpx, pytest; no new frontend or AI integration.

## Task 1: Policy and Code-Free Selection

Files: create backend/services/private_message_policy.py and backend/tests/test_private_message_policy.py.

- [x] Write failing tests for explicit date/time, relative time, immediate mode, recipient matching, malformed time, past time and byte limits.
- [x] Run backend/.venv/Scripts/python.exe -m pytest backend/tests/test_private_message_policy.py -q -p no:cacheprovider; expect missing module before implementation.
- [x] Implement PrivateMessageError, parse_request(text, participants, now), parse_time(text, now), parse_command(text), and is_private_request(text).
- [x] Separate the header from body at the first non-clock colon. Return recipient_id, content, delivery_mode, scheduled_at; keep body unchanged. Use local datetime/ZoneInfo and finite explicit syntax; reject ambiguity instead of using AI.
- [x] No visible message code field or output. Commands: 确认发送, 我的留言, 查看留言, 取消留言, 修改留言：内容, 改时留言：时间, 回复留言：内容, 留言收到; temporary numeric choices only with valid actor context.
- [x] Verify tests:
```python
def test_body_is_preserved_without_ai():
    result = parse_request("明天9点给甲留言：订单备注不要改写", PARTICIPANTS, NOW)
    assert result["content"] == "订单备注不要改写"
    assert result["scheduled_at"].endswith("+00:00")
```

## Task 2: Migration and Schema Security

Files: create supabase/upgrade_v8_private_messages.sql and backend/tests/test_private_message_schema.py.

- [x] Write static migration tests and, if local PostgreSQL is available, execute the migration in a disposable test database; otherwise report that live DDL is not validated.
- [x] SQL in one transaction; six tables with UUID ids, space_id referencing public.users(id), timestamps and unique(space_id,id).
- [x] participants: wecom_userid, name, aliases text[], active; unique(space_id,wecom_userid) plus case-insensitive uniqueness; immutable id/space_id/wecom_userid.
- [x] threads: participant_a, participant_b, canonical a < b; same-space participant FKs, unique(space_id,participant_a,participant_b).
- [x] messages: thread_id, sender_id, recipient_id, content, delivery_mode (immediate/scheduled), scheduled_at nullable, status (draft/scheduled/sending/sent/failed/uncertain/cancelled/expired), version default0, confirmed_at, sent_at, acknowledged_at, failure_code, created_at, updated_at. Sender differs from recipient; require recipient/sender same space and members of thread using database constraint/trigger.
- [x] outbox: message_id, recipient_id, kind (delivery/notice/receipt), operation_key unique, status (pending/sending/sent/failed/uncertain/cancelled), attempts0..2, applied defaultfalse, error_code, created_at, updated_at.
- [x] inbound: msg_id, sender_userid, status(processing/processed/failed), created_at, updated_at; unique(space_id,msg_id), no content column.
- [x] contexts: actor_id, operation, candidates jsonb (ids+versions), parameters jsonb, expires_at, version default0, created_at, updated_at; unique(space_id,actor_id).
- [x] Enable RLS on all six, revoke all anon/authenticated, grant CRUD service_role only; no authenticated owner-read policy. Add due/status and thread indexes. No personal identities or production seed data.
- [x] Test no short-code fields and no private content in inbound/context candidate lists:
```python
def test_private_tables_are_not_client_readable():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "revoke all" in sql.lower()
    assert "approval_code" not in sql
    assert "wecom_inbound_messages" not in sql
```

## Task 3: Safe Delivery Adapter

Files: create backend/services/private_message_delivery.py and backend/tests/test_private_message_delivery.py; narrow safe-log change in wecom_delivery.py only if necessary.

- [x] Define frozen DeliveryResult(status, error_code=None). send_private_text(userid, content) returns sent/failed/uncertain, never raw API responses or URLs.
- [x] Use existing get_access_token; empty credentials/invalid agentId/over2048-byte payload fail before message/send. Disable platform content-based duplicate checking (enable_duplicate_check=0) so independently confirmed identical notes are not swallowed; rely on persistent operation keys and conditional queue claims for replay prevention.
- [x] Parse official errcode, invaliduser, unlicenseduser. Refresh expired token once; do not retry an ambiguous accepted request.
- [x] Connect failures are definite failed; timeout after connecting/invalid JSON/HTTP5xx are uncertain. HTTP429 is definite rejected. Sanitized error codes only.
- [x] Tests:
```python
def test_timeout_is_uncertain_and_does_not_repeat(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(module.httpx, "post", post)
    assert send_private_text("User", "正文").status == "uncertain"
    assert len(calls) == 1
```

## Task 4: Private Service, Context and Persistent Outbox

Files: create backend/services/private_message_service.py, backend/services/private_message_queue.py and backend/tests/test_private_message_service.py with an in-memory query double that verifies space filters.

- [x] PrivateMessageService(db, sender=None, clock=utcnow). Public methods participant(space, userid), handle(space, actor, text), scan(space), drain(space), visible_message(space, actor, id).
- [x] Access: actor must be active; content queries scope space and sender or sent recipient. Space owner has no implicit privilege. Pending recipient cannot view draft/scheduled body.
- [x] create_draft(space, actor, data, thread_id=None): revalidate target, reject self/unknown/disabled, create/reuse fixed canonical pair, insert one draft with UUID and version0.
- [x] Operations collect eligible candidates for actor. One candidate performs operation; multiple persist only ids+versions in private context and render sender/recipient plus body summary to actor. Context lasts10minutes.
- [x] On numeric choice claim current actor context with version CAS, re-read selected message and match saved version/status before action. Never infer from another user's menu; clear context after use. Edit/re-time return new draft preview and revoke prior confirmation.
- [x] Confirm is own draft CAS to scheduled; immediate stamps clock. Reject draft older24h, scheduled time alreadypast. Repeated input/callback must not enqueue again.
- [x] Reply preserves the fixed two-party thread, selects other actor, creates a new draft. Acknowledgement requires sent recipient and CAS acknowledged_at. Notify other party once.
- [x] Outbox unique key includes message UUID+version+kind. Queue claims pending -> sending, attempts increment. Message sending state prevents concurrent edit/cancel. Reconcile successful delivery to sent; notices independently queued and cannot cause body re-send.
- [x] Definite failure retries once then stops. Uncertain stops immediately. Stale sending over5minutes becomes uncertain. Scheduled messages over15minutes late become failed with TIME_EXPIRED, notify sender but never deliver body.
- [x] tests for only-confirmed delivery, 3rd-party/owner denial, excluded member, multi-candidate selections, version changes, cancellation race, duplicate scan, restart recovery, uncertain, late timeout, receipt/reply and notice failures.
```python
def test_private_message_does_not_deliver_until_confirmed(env):
    service, db, sent, clock = env
    service.handle(SPACE, A, "给乙留言，立即发送：交接")
    assert not sent
    service.handle(SPACE, A, "确认发送")
    assert sum(userid == "B" for userid, body in sent) == 1
```

## Task 5: Entry, Isolation and Scheduler

Files: create backend/services/private_message_entry.py and backend/tests/test_private_message_entry.py; modify backend/services/wecom_app.py, backend/main.py, backend/config.py, backend/.env.example.

- [x] Feature WECOM_PRIVATE_MESSAGES_ENABLED defaultsfalse. Strong 留言 and 确认发送/取消发送 commands are claimed even when disabled/unauthorized and answered without saving body to legacy handlers.
- [x] Resolve participant only across explicitly bound spaces within each explicitly filtered space and match its immutable case-insensitive UserID, not an unfiltered global lookup.
- [x] Numeric choices only claimed with valid private context. Bare 收到/回复 only claimed when private candidates exist; if delegation ambiguity exists prompt explicit 留言收到 / coded委派 reply instead of guessing.
- [x] Separate inbound MsgId insertion and processing state without body. Duplicate callbacks do not mutate twice; generic failures don't print message content.
- [x] Add private handler before legacy text truncation and delegation. Max bytes validation belongs to private policy; unsupported/private-disabled content never falls back into owner storage.
- [x] Add one-minute scheduler max_instances1/coalesce with independent id and gate. No second background process for validation.
- [x] Integration tests assert legacy reserve/create/chat functions never run for private paths and existing delegation still works.
```python
def test_private_text_never_reaches_legacy_chat(monkeypatch):
    monkeypatch.setattr(app_module, "handle_private_message", lambda *args: True)
    monkeypatch.setattr(app_module, "chat", lambda *args: pytest.fail("private body leaked"))
    app_module.handle_incoming_text("Sender", "给乙留言：私密正文", "msg-1")
```

## Task 6: Verification and Rollout

Files: create docs/wecom-private-messages-rollout.md; update approved design status after tests.

- [x] Run complete backend suite with mocks only, no main import against live configured database and no real send.
- [x] Confirm no visible random codes, no private bodies in old tables, no AI request, no auth client read policy, and all menu choices scoped to actor.
- [x] Review migration source and component contracts; execute PostgreSQL tests in a disposable database only, never claim production migration from local results.
- [x] Preserve unrelated AGENTS.md and setup-manual modifications. Commit only this feature after review; production migration, participant registration, deployment, enable and real two-person test remain explicit stages.
- [x] Rollout document links verified WeCom/Supabase official docs. Do not put real credentials/UserIDs in public seed SQL; use user-local deployment seed after separate upgrade authorization.

## Execution Record

2026-10-06: Local implementation and independent review complete. Final backend suite: 373 passed, 44 existing warnings. Regression fixes cover history hiding due/eligible messages, actor-scoped menus, quiet-thread replies, stale versions, uncertain delivery and malformed private commands. SQL was actually validated on disposable PostgreSQL18, including role grants, constraints, repeated migration, immutable identities and case-insensitive UserID uniqueness. All message sends and business data used mocks; no production migration, real WeCom message, or DeepSeek request occurred. No frontend changes. Existing Python3.14/OpenAI/Pydantic and dependency deprecation warnings remain.
