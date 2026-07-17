# 企业微信自建应用主动消息统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将晨报、任务催办和 S 级二次提醒统一发送到企业微信自建应用，并为每次主动发送建立按用户隔离的审计记录。

**Architecture:** 把企业微信低层 token/发送能力从 `wecom_app.py` 提取到 `wecom_delivery.py`，由新的 `outreach.py` 统一完成用户反向映射、发送和落库。调度服务只遍历 `WECOM_APP_USER_MAP` 中已绑定的用户，并在每次数据库查询中显式添加 `user_id` 条件。

**Tech Stack:** Python 3.14、FastAPI、Supabase、APScheduler、httpx、pytest、企业微信自建应用 API

---

## File Map

- Create: `supabase/upgrade_v5_wecom_outreach.sql` — 外联记录表及任务暂停字段。
- Modify: `supabase/schema.sql` — 新安装环境的完整结构。
- Create: `backend/services/wecom_delivery.py` — 用户映射、access token、自建应用文本发送。
- Create: `backend/services/outreach.py` — 主动消息发送、记录和失败处理。
- Modify: `backend/services/wecom_app.py` — 改为复用低层发送模块，保留现有入站行为。
- Modify: `backend/services/followup.py` — 按绑定用户发送任务催办和 S 级提醒。
- Modify: `backend/services/secretary.py` — 按绑定用户发送晨报。
- Create: `backend/tests/test_wecom_delivery.py` — 低层发送测试。
- Create: `backend/tests/test_outreach.py` — 外联记录测试。
- Modify: `backend/tests/test_followup.py` — 自建应用催办与用户隔离测试。
- Modify: `backend/tests/test_secretary.py` — 自建应用晨报测试。

### Task 1: Add the outreach database substrate

**Files:**
- Create: `supabase/upgrade_v5_wecom_outreach.sql`
- Modify: `supabase/schema.sql`
- Create: `backend/tests/test_outreach_schema.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wecom_outreach_upgrade_has_rls_indexes_and_pause_flag():
    sql = (ROOT / "supabase" / "upgrade_v5_wecom_outreach.sql").read_text(encoding="utf-8")

    assert "create table if not exists public.secretary_outreach" in sql.lower()
    assert "user_id uuid" in sql.lower()
    assert "task_id uuid" in sql.lower()
    assert "enable row level security" in sql.lower()
    assert "idx_secretary_outreach_user_created" in sql
    assert "followup_paused boolean" in sql.lower()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest backend/tests/test_outreach_schema.py -q`

Expected: FAIL with `FileNotFoundError` for `upgrade_v5_wecom_outreach.sql`.

- [ ] **Step 3: Add the migration**

```sql
alter table public.tasks
  add column if not exists followup_paused boolean not null default false;

create table if not exists public.secretary_outreach (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  task_id uuid references public.tasks(id) on delete cascade,
  kind text not null check (kind in (
    'morning_briefing', 'task_followup', 's_escalation', 'evening_review'
  )),
  content text not null,
  status text not null default 'pending' check (status in (
    'pending', 'sent', 'failed', 'replied', 'expired'
  )),
  wecom_userid text,
  failure_reason text,
  sent_at timestamptz,
  replied_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_secretary_outreach_user_created
  on public.secretary_outreach(user_id, created_at desc);
create index if not exists idx_secretary_outreach_task_status
  on public.secretary_outreach(task_id, status, created_at desc);

alter table public.secretary_outreach enable row level security;
drop policy if exists "own secretary outreach" on public.secretary_outreach;
create policy "own secretary outreach"
  on public.secretary_outreach for all using (auth.uid() = user_id);
```

Append the same table, indexes, RLS policy and `followup_paused` task column to `supabase/schema.sql`.

- [ ] **Step 4: Run the schema contract test and existing schema-sensitive tests**

Run: `python -m pytest backend/tests/test_outreach_schema.py backend/tests/test_schemas.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the database substrate**

```bash
git add supabase/upgrade_v5_wecom_outreach.sql supabase/schema.sql backend/tests/test_outreach_schema.py
git commit -m "feat: add secretary outreach records"
```

### Task 2: Extract self-built app delivery

**Files:**
- Create: `backend/services/wecom_delivery.py`
- Modify: `backend/services/wecom_app.py`
- Create: `backend/tests/test_wecom_delivery.py`

- [ ] **Step 1: Write failing mapping and send tests**

```python
from services import wecom_delivery


def test_bound_users_and_reverse_lookup(monkeypatch):
    monkeypatch.setattr(
        wecom_delivery,
        "WECOM_APP_USER_MAP",
        '{"User":"user-uuid","Colleague":"other-uuid"}',
    )

    assert wecom_delivery.bound_user_ids() == ["user-uuid", "other-uuid"]
    assert wecom_delivery.resolve_wecom_userid("user-uuid") == "User"
    assert wecom_delivery.resolve_supabase_user_id("User") == "user-uuid"


def test_send_app_text_refreshes_expired_token(monkeypatch):
    tokens = iter(["old-token", "new-token"])
    payloads = []

    class Response:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    replies = iter([
        Response({"errcode": 42001}),
        Response({"errcode": 0, "errmsg": "ok"}),
    ])
    monkeypatch.setattr(wecom_delivery, "get_access_token", lambda force_refresh=False: next(tokens))
    monkeypatch.setattr(
        wecom_delivery.httpx,
        "post",
        lambda url, json, timeout: payloads.append(json) or next(replies),
    )
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")

    assert wecom_delivery.send_app_text("User", "测试提醒") is True
    assert payloads[-1]["touser"] == "User"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest backend/tests/test_wecom_delivery.py -q`

Expected: FAIL because `services.wecom_delivery` does not exist.

- [ ] **Step 3: Implement the delivery module**

Move the existing token cache, `get_access_token()` and `send_app_text()` implementation from `wecom_app.py` to `wecom_delivery.py`, then add:

```python
def user_map() -> dict[str, str]:
    try:
        data = json.loads(WECOM_APP_USER_MAP or "{}")
    except json.JSONDecodeError as exc:
        print(f"WECOM_APP_USER_MAP invalid: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(wecom_id): str(user_id) for wecom_id, user_id in data.items()}


def bound_user_ids() -> list[str]:
    return list(dict.fromkeys(user_map().values()))


def resolve_wecom_userid(user_id: str) -> str | None:
    return next((wid for wid, uid in user_map().items() if uid == user_id), None)


def resolve_supabase_user_id(wecom_userid: str) -> str | None:
    return user_map().get(wecom_userid)
```

In `wecom_app.py`, import `resolve_supabase_user_id` and `send_app_text` from `services.wecom_delivery`, remove the duplicated token/mapping code, and keep `send_app_text` imported at module scope so existing callers remain compatible.

- [ ] **Step 4: Run delivery and callback regression tests**

Run: `python -m pytest backend/tests/test_wecom_delivery.py backend/tests/test_wecom_app_v4.py -q`

Expected: PASS. If local `Crypto` is missing, install the locked requirement in the project environment before retrying; do not skip the callback tests in deployment verification.

- [ ] **Step 5: Commit the extraction**

```bash
git add backend/services/wecom_delivery.py backend/services/wecom_app.py backend/tests/test_wecom_delivery.py
git commit -m "refactor: isolate wecom app delivery"
```

### Task 3: Create the audited proactive sender

**Files:**
- Create: `backend/services/outreach.py`
- Create: `backend/tests/test_outreach.py`

- [ ] **Step 1: Write failing success and failure tests**

```python
from services import outreach


class Result:
    def __init__(self, data):
        self.data = data


class FakeOutreachTable:
    def __init__(self):
        self.rows = []
        self.pending_update = None

    def insert(self, payload):
        row = {"id": "outreach-1", **payload}
        self.rows.append(row)
        return type("Insert", (), {"execute": lambda _self: Result([row])})()

    def update(self, payload):
        self.pending_update = payload
        return self

    def eq(self, _column, _value):
        return self

    def execute(self):
        self.rows[0].update(self.pending_update)
        return Result([self.rows[0]])


def test_send_secretary_message_records_success(monkeypatch):
    table = FakeOutreachTable()
    monkeypatch.setattr(outreach, "supabase", type("DB", (), {"table": lambda _s, _n: table})())
    monkeypatch.setattr(outreach, "resolve_wecom_userid", lambda _uid: "User")
    monkeypatch.setattr(outreach, "send_app_text", lambda _wid, _content: True)

    result = outreach.send_secretary_message(
        "user-1", "该跟进客户报价了", "task_followup", task_id="task-1"
    )

    assert result["sent"] is True
    assert table.rows[0]["status"] == "sent"
    assert table.rows[0]["user_id"] == "user-1"


def test_send_secretary_message_records_missing_mapping(monkeypatch):
    table = FakeOutreachTable()
    monkeypatch.setattr(outreach, "supabase", type("DB", (), {"table": lambda _s, _n: table})())
    monkeypatch.setattr(outreach, "resolve_wecom_userid", lambda _uid: None)

    result = outreach.send_secretary_message("user-1", "晨报", "morning_briefing")

    assert result["sent"] is False
    assert table.rows[0]["status"] == "failed"
    assert table.rows[0]["failure_reason"] == "企业微信账号未绑定"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest backend/tests/test_outreach.py -q`

Expected: FAIL because `services.outreach` does not exist.

- [ ] **Step 3: Implement `send_secretary_message`**

```python
from datetime import datetime, timezone

from database import supabase
from services.wecom_delivery import resolve_wecom_userid, send_app_text


VALID_KINDS = {"morning_briefing", "task_followup", "s_escalation", "evening_review"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_secretary_message(
    user_id: str,
    content: str,
    kind: str,
    task_id: str | None = None,
) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"unsupported outreach kind: {kind}")

    wecom_userid = resolve_wecom_userid(user_id)
    row = {
        "user_id": user_id,
        "task_id": task_id,
        "kind": kind,
        "content": content,
        "status": "pending",
        "wecom_userid": wecom_userid,
    }
    created = supabase.table("secretary_outreach").insert(row).execute()
    outreach_id = created.data[0]["id"] if created.data else None
    if not outreach_id:
        return {"sent": False, "outreach_id": None, "reason": "外联记录创建失败"}

    sent = bool(wecom_userid and send_app_text(wecom_userid, content))
    reason = None if sent else ("企业微信发送失败" if wecom_userid else "企业微信账号未绑定")
    update = {
        "status": "sent" if sent else "failed",
        "sent_at": _now_iso() if sent else None,
        "failure_reason": reason,
    }
    (
        supabase.table("secretary_outreach")
        .update(update)
        .eq("id", outreach_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"sent": sent, "outreach_id": outreach_id, "reason": reason}
```

- [ ] **Step 4: Run the outreach tests**

Run: `python -m pytest backend/tests/test_outreach.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the sender**

```bash
git add backend/services/outreach.py backend/tests/test_outreach.py
git commit -m "feat: audit proactive wecom messages"
```

### Task 4: Route follow-ups and S-level escalation through the app

**Files:**
- Modify: `backend/services/followup.py`
- Modify: `backend/tests/test_followup.py`

- [ ] **Step 1: Replace the old webhook expectations with failing app-delivery tests**

Update the two scheduler tests so they monkeypatch `bound_user_ids` to return `["user-1"]`, assert every task query receives `.eq("user_id", "user-1")`, and monkeypatch:

```python
monkeypatch.setattr(
    followup,
    "send_secretary_message",
    lambda user_id, content, kind, task_id=None: sent.append(
        (user_id, content, kind, task_id)
    ) or {"sent": True, "outreach_id": "out-1", "reason": None},
)
```

Assert normal follow-up uses `kind == "task_followup"`, S-level uses `kind == "s_escalation"`, and `task_id` matches the selected task. Add a failure case asserting `next_follow_time` is unchanged when `sent` is false.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest backend/tests/test_followup.py -q`

Expected: FAIL because the service still calls `send_wecom` and scans without a user filter.

- [ ] **Step 3: Implement per-bound-user scanning**

Replace webhook imports with:

```python
from services.outreach import send_secretary_message
from services.wecom_delivery import bound_user_ids
```

Add a plain-text builder:

```python
def build_followup_text(task: dict, s_level: bool = False) -> str:
    prefix = "【S级事项二次确认】" if s_level else "【AI秘书跟进】"
    return (
        f"{prefix}\n{task.get('content', '未命名任务')}\n"
        "现在进展怎么样？直接回复：完成了 / 等对方回复 / 卡住了 / 明天继续。"
    )
```

For each `user_id in bound_user_ids()`, query one due task using `.eq("user_id", user_id)`, exclude terminal and paused tasks, sort by `priority` descending then `next_follow_time` ascending, and call `send_secretary_message`. Only after `result["sent"] is True` may the code postpone `next_follow_time` and insert `REMINDER_SENT`/`FOLLOW_GENERATED` events. Every update must retain `.eq("id", task_id).eq("user_id", user_id)`.

- [ ] **Step 4: Run focused and regression tests**

Run: `python -m pytest backend/tests/test_followup.py backend/tests/test_wecom.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the follow-up migration**

```bash
git add backend/services/followup.py backend/tests/test_followup.py
git commit -m "feat: send followups through wecom app"
```

### Task 5: Route morning briefing through the app

**Files:**
- Modify: `backend/services/secretary.py`
- Modify: `backend/tests/test_secretary.py`

- [ ] **Step 1: Write the failing bound-user morning test**

Replace `test_push_morning_briefing_sends_wecom` with a test that does not provide a global `users` table. Monkeypatch `bound_user_ids()` to `["user-1"]` and assert:

```python
assert sent == [
    ("user-1", expected_content, "morning_briefing", None),
]
```

Also assert the content includes `跟进报价`.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest backend/tests/test_secretary.py::test_push_morning_briefing_sends_wecom -q`

Expected: FAIL because `push_morning_briefing()` still selects all users and calls the webhook sender.

- [ ] **Step 3: Implement bound-user app delivery**

Replace webhook imports with:

```python
from services.outreach import send_secretary_message
from services.wecom_delivery import bound_user_ids
```

Implement:

```python
def push_morning_briefing() -> None:
    for user_id in bound_user_ids():
        try:
            briefing = build_briefing(user_id)
            content = build_morning_briefing_markdown(briefing)
            send_secretary_message(user_id, content, "morning_briefing")
        except Exception as exc:
            print(f"Morning briefing failed for {user_id}: {exc}")
```

Keep `build_briefing()` user filters unchanged.

- [ ] **Step 4: Run phase-one tests**

Run: `python -m pytest backend/tests/test_wecom_delivery.py backend/tests/test_outreach.py backend/tests/test_followup.py backend/tests/test_secretary.py backend/tests/test_wecom_app_v4.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the morning migration**

```bash
git add backend/services/secretary.py backend/tests/test_secretary.py
git commit -m "feat: send morning briefing through wecom app"
```

### Task 6: Phase-one verification and deployment handoff

**Files:**
- Modify only if tests expose a defect in files already listed above.

- [ ] **Step 1: Run the full backend suite**

Run: `python -m pytest backend/tests -q`

Expected: all tests PASS; warnings may include the known Python 3.14/Pydantic compatibility warning, but no collection error or failure.

- [ ] **Step 2: Verify no proactive business path imports the webhook sender**

Run: `rg -n "send_wecom|resolve_webhook|resolve_mentioned_mobiles" backend/services/followup.py backend/services/secretary.py`

Expected: no output.

- [ ] **Step 3: Verify data isolation in scheduler queries**

Run: `rg -n "table\(\"tasks\"\)|table\(\"users\"\)|table\(\"secretary_outreach\"\)" backend/services/followup.py backend/services/secretary.py backend/services/outreach.py`

Expected: every `tasks`, `users`, and `secretary_outreach` read/update path is followed by the appropriate `.eq("user_id", user_id)` or `.eq("id", user_id)` filter; no scheduler-wide `users.select("id")` remains.

- [ ] **Step 4: Record the deployment caveat**

Do not provide enterprise WeChat admin-console steps until the official documentation is reachable and rechecked.

⚠️ 此步骤未经官方文档核实，操作时如遇界面/流程不符，先停下确认，不要硬做。

- [ ] **Step 5: Stop for phase-one approval**

Report changed files, test output, migration filename, and the exact remaining server-side actions. Do not begin phase two until phase one is deployed and a real proactive message is received in the self-built app.

