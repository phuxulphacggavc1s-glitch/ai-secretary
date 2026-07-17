# 企业微信任务回复闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户对企业微信任务催办的自然语言回复准确更新被催问任务，同时保证普通聊天、新待办和重复回调不会误改任务。

**Architecture:** 使用 `secretary_outreach` 最近 36 小时内未回复的任务外联作为唯一候选上下文，用独立的三分类器判断 `create_task`、`task_progress` 或 `chat`。新增入站消息收据表实现回调幂等，状态更新沿用 `judge_reply()`，所有任务读取和写入同时过滤 `task_id` 与 `user_id`。

**Tech Stack:** Python 3.14、FastAPI、Supabase、DeepSeek OpenAI-compatible API、pytest、企业微信加密回调

---

## File Map

- Create: `supabase/upgrade_v6_wecom_reply_loop.sql` — 入站消息幂等表。
- Modify: `supabase/schema.sql` — 新安装环境完整结构。
- Create: `backend/services/wecom_inbound.py` — 入站消息预占、完成和失败状态。
- Create: `backend/services/wecom_reply.py` — 待回复外联查询、意图分类、任务状态更新。
- Modify: `backend/routers/wecom.py` — 提取并传递稳定消息 ID。
- Modify: `backend/services/wecom_app.py` — 先处理任务回复，再进入现有聊天/建任务流程。
- Create: `backend/tests/test_wecom_inbound.py` — 回调幂等测试。
- Create: `backend/tests/test_wecom_reply.py` — 回复分类与任务更新测试。
- Modify: `backend/tests/test_wecom_app_v4.py` — 入站编排回归测试。

### Task 1: Add inbound callback receipts

**Files:**
- Create: `supabase/upgrade_v6_wecom_reply_loop.sql`
- Modify: `supabase/schema.sql`
- Create: `backend/tests/test_wecom_inbound_schema.py`

- [ ] **Step 1: Write the failing migration contract test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wecom_inbound_migration_has_unique_msg_id_and_rls():
    sql = (ROOT / "supabase" / "upgrade_v6_wecom_reply_loop.sql").read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "create table if not exists public.wecom_inbound_messages" in lowered
    assert "msg_id text not null unique" in lowered
    assert "user_id uuid" in lowered
    assert "enable row level security" in lowered
    assert "idx_wecom_inbound_user_created" in sql
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest backend/tests/test_wecom_inbound_schema.py -q`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Add the migration and mirror it in `schema.sql`**

```sql
create table if not exists public.wecom_inbound_messages (
  id uuid primary key default gen_random_uuid(),
  msg_id text not null unique,
  user_id uuid references public.users(id) on delete cascade not null,
  wecom_userid text not null,
  content text not null,
  status text not null default 'processing'
    check (status in ('processing', 'processed', 'failed')),
  failure_reason text,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_wecom_inbound_user_created
  on public.wecom_inbound_messages(user_id, created_at desc);

alter table public.wecom_inbound_messages enable row level security;
drop policy if exists "own wecom inbound messages" on public.wecom_inbound_messages;
create policy "own wecom inbound messages"
  on public.wecom_inbound_messages for all using (auth.uid() = user_id);
```

- [ ] **Step 4: Run the migration contract tests**

Run: `python -m pytest backend/tests/test_wecom_inbound_schema.py backend/tests/test_outreach_schema.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the migration**

```bash
git add supabase/upgrade_v6_wecom_reply_loop.sql supabase/schema.sql backend/tests/test_wecom_inbound_schema.py
git commit -m "feat: add wecom inbound receipts"
```

### Task 2: Make callback processing idempotent

**Files:**
- Create: `backend/services/wecom_inbound.py`
- Create: `backend/tests/test_wecom_inbound.py`

- [ ] **Step 1: Write failing receipt lifecycle tests**

```python
from services import wecom_inbound


def test_reserve_inbound_rejects_existing_message(monkeypatch):
    class Query:
        def select(self, _cols): return self
        def eq(self, _col, _value): return self
        def limit(self, _value): return self
        def execute(self): return type("R", (), {"data": [{"id": "existing"}]})()

    monkeypatch.setattr(
        wecom_inbound,
        "supabase",
        type("DB", (), {"table": lambda _self, _name: Query()})(),
    )

    assert wecom_inbound.reserve_inbound_message(
        "msg-1", "user-1", "User", "完成了"
    ) is False


def test_mark_processed_filters_by_message_and_user(monkeypatch):
    filters = []

    class Query:
        def update(self, _payload): return self
        def eq(self, column, value):
            filters.append((column, value))
            return self
        def execute(self): return type("R", (), {"data": [{"id": "receipt-1"}]})()

    monkeypatch.setattr(
        wecom_inbound,
        "supabase",
        type("DB", (), {"table": lambda _self, _name: Query()})(),
    )

    wecom_inbound.mark_inbound_processed("msg-1", "user-1")

    assert ("msg_id", "msg-1") in filters
    assert ("user_id", "user-1") in filters
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_wecom_inbound.py -q`

Expected: FAIL because `services.wecom_inbound` does not exist.

- [ ] **Step 3: Implement receipt functions**

```python
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
        created = supabase.table("wecom_inbound_messages").insert({
            "msg_id": msg_id,
            "user_id": user_id,
            "wecom_userid": wecom_userid,
            "content": content,
            "status": "processing",
        }).execute()
        return bool(created.data)
    except Exception as exc:
        print(f"reserve inbound failed for {user_id}: {exc}")
        return False


def _finish(msg_id: str, user_id: str, status: str, reason: str | None = None) -> None:
    (
        supabase.table("wecom_inbound_messages")
        .update({
            "status": status,
            "failure_reason": reason,
            "processed_at": _now_iso(),
        })
        .eq("msg_id", msg_id)
        .eq("user_id", user_id)
        .execute()
    )


def mark_inbound_processed(msg_id: str, user_id: str) -> None:
    _finish(msg_id, user_id, "processed")


def mark_inbound_failed(msg_id: str, user_id: str, reason: str) -> None:
    _finish(msg_id, user_id, "failed", reason[:500])
```

- [ ] **Step 4: Run receipt tests**

Run: `python -m pytest backend/tests/test_wecom_inbound.py -q`

Expected: PASS.

- [ ] **Step 5: Commit receipt handling**

```bash
git add backend/services/wecom_inbound.py backend/tests/test_wecom_inbound.py
git commit -m "feat: deduplicate wecom callbacks"
```

### Task 3: Classify replies against a pending task outreach

**Files:**
- Create: `backend/services/wecom_reply.py`
- Create: `backend/tests/test_wecom_reply.py`

- [ ] **Step 1: Write failing fallback-classifier tests**

```python
from services import wecom_reply


def test_fallback_classifier_separates_task_progress_new_task_and_chat(monkeypatch):
    monkeypatch.setattr(wecom_reply, "DEEPSEEK_API_KEY", None)

    assert wecom_reply.classify_reply("完成了", {"content": "给客户报价"}) == "task_progress"
    assert wecom_reply.classify_reply("明天下午提醒我发货", {"content": "给客户报价"}) == "create_task"
    assert wecom_reply.classify_reply("今天先做什么？", {"content": "给客户报价"}) == "chat"
    assert wecom_reply.classify_reply("好的", {"content": "给客户报价"}) == "clarify"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_wecom_reply.py::test_fallback_classifier_separates_task_progress_new_task_and_chat -q`

Expected: FAIL because `services.wecom_reply` does not exist.

- [ ] **Step 3: Implement the classifier**

Define an AI prompt that returns only `{"intent":"create_task|task_progress|chat|clarify"}` and validate the returned value. Implement this deterministic fallback before adding the AI call:

```python
VALID_INTENTS = {"create_task", "task_progress", "chat", "clarify"}
CREATE_KEYWORDS = ("提醒我", "记一下", "记个", "别忘了", "新增待办")
PROGRESS_KEYWORDS = (
    "完成", "搞定", "已联系", "等回复", "下周回复", "明天回复",
    "卡住", "缺资料", "延期", "正在做", "继续推进", "别催",
)


def _fallback_classify(text: str) -> str:
    if any(word in text for word in CREATE_KEYWORDS):
        return "create_task"
    if any(word in text for word in PROGRESS_KEYWORDS):
        return "task_progress"
    if text.strip() in {"好", "好的", "知道了", "收到"}:
        return "clarify"
    return "chat"
```

`classify_reply(text, task)` uses DeepSeek when configured and returns `_fallback_classify(text)` on any invalid output or exception.

- [ ] **Step 4: Run classifier tests**

Run: `python -m pytest backend/tests/test_wecom_reply.py -q`

Expected: the classifier test PASS; later processor tests are added in Task 4.

- [ ] **Step 5: Commit the classifier**

```bash
git add backend/services/wecom_reply.py backend/tests/test_wecom_reply.py
git commit -m "feat: classify wecom task replies"
```

### Task 4: Update the exact task linked to the outreach

**Files:**
- Modify: `backend/services/wecom_reply.py`
- Modify: `backend/tests/test_wecom_reply.py`

- [ ] **Step 1: Add failing processor tests**

Add fake Supabase tables that record filters and updates. Cover these exact cases:

```python
def test_process_pending_reply_marks_exact_task_done(monkeypatch):
    # Arrange a sent task_followup for user-1/task-1 and two tasks in the fake DB.
    # Stub classify_reply -> task_progress and judge_reply -> done.
    result = wecom_reply.process_pending_task_reply("user-1", "完成了")
    assert result["handled"] is True
    assert result["task_id"] == "task-1"
    assert result["status"] == "done"
    assert ("user_id", "user-1") in recorded_task_filters
    assert ("id", "task-1") in recorded_task_filters


def test_process_pending_reply_does_not_consume_new_task(monkeypatch):
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "create_task")
    assert wecom_reply.process_pending_task_reply(
        "user-1", "明天下午提醒我发货"
    ) is None


def test_process_pending_reply_clarifies_without_update(monkeypatch):
    monkeypatch.setattr(wecom_reply, "classify_reply", lambda _text, _task: "clarify")
    result = wecom_reply.process_pending_task_reply("user-1", "好的")
    assert result == {
        "handled": True,
        "reply": "你是在回复刚才这项任务的进展吗？请告诉我：完成了、等回复、卡住了，或者需要延期。",
    }
    assert recorded_task_updates == []
```

- [ ] **Step 2: Run processor tests and verify RED**

Run: `python -m pytest backend/tests/test_wecom_reply.py -q`

Expected: FAIL because `process_pending_task_reply` is missing.

- [ ] **Step 3: Implement pending outreach lookup and exact update**

Implement `get_pending_task_outreach(user_id, now=None)` using:

```python
cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=36)
result = (
    supabase.table("secretary_outreach")
    .select("id, task_id, kind, content, created_at")
    .eq("user_id", user_id)
    .eq("status", "sent")
    .in_("kind", ["task_followup", "s_escalation"])
    .gte("created_at", cutoff.isoformat())
    .order("created_at", desc=True)
    .limit(1)
    .execute()
)
```

Implement `process_pending_task_reply(user_id, text)`:

1. Load the pending outreach using the user filter.
2. Load its task with `.eq("id", task_id).eq("user_id", user_id)`.
3. Return `None` for `create_task` or `chat`.
4. Return the fixed clarification message for `clarify` without any update.
5. For “别催”, set `followup_paused=True`, mark the outreach replied, and return confirmation.
6. Otherwise call `judge_reply`, reject statuses outside `TaskStatus`, update only the exact user task, insert `AI_JUDGE` event, and mark the exact outreach `replied` with both `.eq("id", outreach_id)` and `.eq("user_id", user_id)`.
7. For `done`, explicitly set `next_follow_time=None`; never call `ensure_next_follow` after a terminal status.

- [ ] **Step 4: Run reply and existing follow-up tests**

Run: `python -m pytest backend/tests/test_wecom_reply.py backend/tests/test_followup.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the processor**

```bash
git add backend/services/wecom_reply.py backend/tests/test_wecom_reply.py
git commit -m "feat: close wecom task reply loop"
```

### Task 5: Integrate receipt and reply processing into the callback

**Files:**
- Modify: `backend/routers/wecom.py`
- Modify: `backend/services/wecom_app.py`
- Modify: `backend/tests/test_wecom_app_v4.py`

- [ ] **Step 1: Write failing orchestration tests**

Add tests that call `handle_incoming_text("User", text, "msg-1")` with monkeypatched mapping, receipt and reply services:

```python
def test_duplicate_message_stops_before_chat(monkeypatch):
    monkeypatch.setattr(wecom_app, "resolve_supabase_user_id", lambda _wid: "user-1")
    monkeypatch.setattr(wecom_app, "reserve_inbound_message", lambda *args: False)
    monkeypatch.setattr(wecom_app, "chat", lambda *_args: (_ for _ in ()).throw(AssertionError("must not chat")))

    wecom_app.handle_incoming_text("User", "完成了", "msg-1")


def test_task_reply_sends_processor_response_and_skips_chat(monkeypatch):
    sent = []
    monkeypatch.setattr(wecom_app, "resolve_supabase_user_id", lambda _wid: "user-1")
    monkeypatch.setattr(wecom_app, "reserve_inbound_message", lambda *args: True)
    monkeypatch.setattr(
        wecom_app,
        "process_pending_task_reply",
        lambda _uid, _text: {"handled": True, "reply": "收到，已标记完成。"},
    )
    monkeypatch.setattr(wecom_app, "send_app_text", lambda _wid, content: sent.append(content) or True)

    wecom_app.handle_incoming_text("User", "完成了", "msg-1")

    assert sent == ["收到，已标记完成。"]
```

- [ ] **Step 2: Run orchestration tests and verify RED**

Run: `python -m pytest backend/tests/test_wecom_app_v4.py -q`

Expected: FAIL because `handle_incoming_text` accepts only two arguments and has no receipt/reply flow.

- [ ] **Step 3: Pass a stable message ID from the router**

In `routers/wecom.py`, extract `MsgId` and `CreateTime`. For text messages missing `MsgId`, derive a stable fallback:

```python
from hashlib import sha256


def _message_id(message, from_user: str, content: str) -> str:
    msg_id = message.findtext("MsgId")
    if msg_id:
        return msg_id
    create_time = message.findtext("CreateTime") or ""
    raw = f"{from_user}|{create_time}|{content}".encode("utf-8")
    return sha256(raw).hexdigest()
```

Pass the result as the third argument to `handle_incoming_text`.

- [ ] **Step 4: Implement the inbound orchestration**

In `wecom_app.py`:

1. Resolve `user_id` before reserving the message.
2. Return immediately if `reserve_inbound_message(...)` is false.
3. Call `process_pending_task_reply(user_id, text)` before `chat()`.
4. If handled, send its reply and mark the receipt processed.
5. Otherwise run the existing chat/create-task path and mark processed after business handling.
6. On exception, mark failed and send the existing Chinese error response. Do not log message content or secrets.

- [ ] **Step 5: Run phase-two tests**

Run: `python -m pytest backend/tests/test_wecom_inbound.py backend/tests/test_wecom_reply.py backend/tests/test_wecom_app_v4.py backend/tests/test_secretary_chat.py backend/tests/test_followup.py -q`

Expected: PASS.

- [ ] **Step 6: Commit integration**

```bash
git add backend/routers/wecom.py backend/services/wecom_app.py backend/tests/test_wecom_app_v4.py
git commit -m "feat: process wecom replies idempotently"
```

### Task 6: Phase-two verification and stop point

**Files:**
- Modify only if tests reveal a defect in phase-two files.

- [ ] **Step 1: Run full backend tests**

Run: `python -m pytest backend/tests -q`

Expected: all tests PASS.

- [ ] **Step 2: Audit user filters**

Run: `rg -n "table\(\"tasks\"\)|table\(\"secretary_outreach\"\)|table\(\"wecom_inbound_messages\"\)" backend/services/wecom_reply.py backend/services/wecom_inbound.py`

Expected: every select/update/delete includes `user_id`; task operations also include `task_id`.

- [ ] **Step 3: Manual acceptance after deployment**

Send one real task reminder, then test these four replies one at a time: `完成了`、`客户周五回复`、`缺资料卡住了`、`明天下午提醒我发货`。Verify only the intended task changes and the last phrase creates a new task.

- [ ] **Step 4: Stop for phase-two approval**

Report migration status, test output and the four real-message results. Do not enable AI proactive advice until this loop is proven stable.

