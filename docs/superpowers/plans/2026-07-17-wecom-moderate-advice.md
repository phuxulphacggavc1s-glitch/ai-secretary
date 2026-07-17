# 企业微信适中型主动建议策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在企业微信自建应用中提供有节制的晨间建议、到期跟进、S 级确认和风险晚报，并用确定性规则限制打扰频率。

**Architecture:** 新增纯策略模块判断安静时段、每日上限、任务日限频和晚报冷却，再由外联服务统一执行并记录 `sent` 或 `skipped`。建议生成模块读取现有任务简报和用户记忆；AI 不可用时使用中文确定性模板，是否发送由策略代码决定，不交给模型自由发挥。

**Tech Stack:** Python 3.14、APScheduler、Supabase、DeepSeek OpenAI-compatible API、ZoneInfo、pytest、企业微信自建应用 API

---

## File Map

- Create: `supabase/upgrade_v7_moderate_outreach_policy.sql` — 增加 `skipped` 外联状态。
- Modify: `supabase/schema.sql` — 同步完整状态约束。
- Create: `backend/services/proactive_policy.py` — 安静时段、每日上限、任务限频和冷却判断。
- Create: `backend/services/proactive_advice.py` — 晨间建议与风险晚报生成。
- Modify: `backend/services/outreach.py` — 策略拒绝记录与成功消息写入对话历史。
- Modify: `backend/services/secretary.py` — 使用建议生成器并新增风险晚报任务。
- Modify: `backend/services/followup.py` — 催办和 S 级发送前应用统一策略。
- Modify: `backend/main.py` — 调整 08:30 晨报并增加 19:30 风险晚报。
- Create: `backend/tests/test_proactive_policy.py` — 频率和时段测试。
- Create: `backend/tests/test_proactive_advice.py` — 建议生成和降级测试。
- Modify: `backend/tests/test_outreach.py` — skipped 与对话历史测试。
- Modify: `backend/tests/test_secretary.py` — 晨报/晚报调度测试。

### Task 1: Allow explicit skipped outreach records

**Files:**
- Create: `supabase/upgrade_v7_moderate_outreach_policy.sql`
- Modify: `supabase/schema.sql`
- Create: `backend/tests/test_proactive_policy_schema.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_policy_migration_allows_skipped_outreach():
    sql = (ROOT / "supabase" / "upgrade_v7_moderate_outreach_policy.sql").read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "drop constraint if exists secretary_outreach_status_check" in lowered
    assert "'skipped'" in lowered
    assert "add constraint secretary_outreach_status_check" in lowered
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_proactive_policy_schema.py -q`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Add the status migration**

```sql
alter table public.secretary_outreach
  drop constraint if exists secretary_outreach_status_check;

alter table public.secretary_outreach
  add constraint secretary_outreach_status_check
  check (status in ('pending', 'sent', 'failed', 'replied', 'expired', 'skipped'));
```

Update the `secretary_outreach.status` check in `supabase/schema.sql` with the same values.

- [ ] **Step 4: Run schema contract tests**

Run: `python -m pytest backend/tests/test_proactive_policy_schema.py backend/tests/test_outreach_schema.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the migration**

```bash
git add supabase/upgrade_v7_moderate_outreach_policy.sql supabase/schema.sql backend/tests/test_proactive_policy_schema.py
git commit -m "feat: record skipped secretary outreach"
```

### Task 2: Implement deterministic moderate-contact policy

**Files:**
- Create: `backend/services/proactive_policy.py`
- Create: `backend/tests/test_proactive_policy.py`

- [ ] **Step 1: Write failing pure-rule tests**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from services import proactive_policy


TZ = ZoneInfo("Asia/Shanghai")


def test_quiet_hours_block_outreach():
    decision = proactive_policy.evaluate_static_rules(
        kind="task_followup",
        now=datetime(2026, 7, 17, 21, 5, tzinfo=TZ),
        sent_today=0,
        same_task_sent_today=False,
        task_replied_today=False,
        last_sent_at=None,
    )
    assert decision == {"allowed": False, "reason": "安静时段"}


def test_fifth_daily_message_is_blocked():
    decision = proactive_policy.evaluate_static_rules(
        kind="morning_briefing",
        now=datetime(2026, 7, 17, 8, 30, tzinfo=TZ),
        sent_today=4,
        same_task_sent_today=False,
        task_replied_today=False,
        last_sent_at=None,
    )
    assert decision == {"allowed": False, "reason": "今日主动消息已达4条"}


def test_same_task_followup_is_limited_but_s_escalation_can_pass():
    now = datetime(2026, 7, 17, 20, 0, tzinfo=TZ)
    blocked = proactive_policy.evaluate_static_rules(
        kind="task_followup", now=now, sent_today=1,
        same_task_sent_today=True, task_replied_today=False, last_sent_at=None,
    )
    allowed = proactive_policy.evaluate_static_rules(
        kind="s_escalation", now=now, sent_today=1,
        same_task_sent_today=True, task_replied_today=False, last_sent_at=None,
    )
    assert blocked["allowed"] is False
    assert allowed["allowed"] is True


def test_s_escalation_stops_after_valid_reply():
    decision = proactive_policy.evaluate_static_rules(
        kind="s_escalation",
        now=datetime(2026, 7, 17, 20, 0, tzinfo=TZ),
        sent_today=1,
        same_task_sent_today=True,
        task_replied_today=True,
        last_sent_at=None,
    )
    assert decision == {"allowed": False, "reason": "该任务今天已有有效回复"}
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_proactive_policy.py -q`

Expected: FAIL because `services.proactive_policy` does not exist.

- [ ] **Step 3: Implement pure static rules**

```python
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Shanghai"
DAILY_LIMIT = 4


def evaluate_static_rules(
    *, kind: str, now: datetime, sent_today: int,
    same_task_sent_today: bool, task_replied_today: bool,
    last_sent_at: datetime | None,
) -> dict:
    if now.time() < time(8, 0) or now.time() >= time(21, 0):
        return {"allowed": False, "reason": "安静时段"}
    if sent_today >= DAILY_LIMIT:
        return {"allowed": False, "reason": "今日主动消息已达4条"}
    if task_replied_today and kind == "s_escalation":
        return {"allowed": False, "reason": "该任务今天已有有效回复"}
    if same_task_sent_today and kind == "task_followup":
        return {"allowed": False, "reason": "该任务今天已跟进"}
    if kind == "evening_review" and last_sent_at and now - last_sent_at < timedelta(hours=3):
        return {"allowed": False, "reason": "距离上次主动联系不足3小时"}
    return {"allowed": True, "reason": None}
```

- [ ] **Step 4: Add database-backed policy lookup with user filters**

Implement `evaluate_outreach(user_id, kind, task_id=None, now=None)`:

1. Read the user timezone from `users` with `.eq("id", user_id)`; fall back to `Asia/Shanghai`.
2. Convert local day start/end to UTC ISO timestamps.
3. Count only `sent` and `replied` outreach for that user today.
4. If `task_id` is present, query the same user and task for today’s `task_followup`/`s_escalation` records.
5. Query the same user’s latest successful outreach for evening cooldown.
6. Pass those values into `evaluate_static_rules`.

All `users` and `secretary_outreach` reads must include the explicit current-user filter.

- [ ] **Step 5: Run policy tests**

Run: `python -m pytest backend/tests/test_proactive_policy.py -q`

Expected: PASS, including fake-database assertions that `user_id`/`id` filters are present.

- [ ] **Step 6: Commit the policy**

```bash
git add backend/services/proactive_policy.py backend/tests/test_proactive_policy.py
git commit -m "feat: enforce moderate outreach policy"
```

### Task 3: Enforce policy in the audited sender

**Files:**
- Modify: `backend/services/outreach.py`
- Modify: `backend/tests/test_outreach.py`

- [ ] **Step 1: Write failing skipped and history tests**

```python
def test_policy_denial_records_skipped_without_sending(monkeypatch):
    monkeypatch.setattr(
        outreach, "evaluate_outreach",
        lambda **_kwargs: {"allowed": False, "reason": "今日主动消息已达4条"},
    )
    monkeypatch.setattr(
        outreach, "send_app_text",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not send")),
    )

    result = outreach.send_secretary_message("user-1", "晨报", "morning_briefing")

    assert result == {
        "sent": False,
        "outreach_id": "outreach-1",
        "reason": "今日主动消息已达4条",
        "skipped": True,
    }
    assert outreach_rows[0]["status"] == "skipped"


def test_successful_outreach_is_saved_to_chat_history(monkeypatch):
    monkeypatch.setattr(
        outreach, "evaluate_outreach",
        lambda **_kwargs: {"allowed": True, "reason": None},
    )
    result = outreach.send_secretary_message("user-1", "先处理客户报价。", "morning_briefing")
    assert result["sent"] is True
    assert secretary_message_rows == [{
        "user_id": "user-1", "role": "secretary", "content": "先处理客户报价。"
    }]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_outreach.py -q`

Expected: FAIL because policy is not evaluated and successful outreach is not written to `secretary_messages`.

- [ ] **Step 3: Integrate policy before delivery**

At the start of `send_secretary_message`, call:

```python
decision = evaluate_outreach(
    user_id=user_id,
    kind=kind,
    task_id=task_id,
)
```

When denied, insert one `secretary_outreach` row with `status="skipped"` and `failure_reason=decision["reason"]`, then return without calling `send_app_text`. When sent successfully, insert this additional row using the user ID:

```python
supabase.table("secretary_messages").insert({
    "user_id": user_id,
    "role": "secretary",
    "content": content,
}).execute()
```

Do not save failed or skipped content as a delivered chat message.

- [ ] **Step 4: Run outreach and chat-history tests**

Run: `python -m pytest backend/tests/test_outreach.py backend/tests/test_secretary_chat.py -q`

Expected: PASS.

- [ ] **Step 5: Commit policy integration**

```bash
git add backend/services/outreach.py backend/tests/test_outreach.py
git commit -m "feat: limit and record proactive messages"
```

### Task 4: Generate concrete morning advice and risk-only evening review

**Files:**
- Create: `backend/services/proactive_advice.py`
- Create: `backend/tests/test_proactive_advice.py`

- [ ] **Step 1: Write failing fallback tests**

```python
from services import proactive_advice


def test_morning_fallback_names_top_task(monkeypatch):
    monkeypatch.setattr(proactive_advice, "DEEPSEEK_API_KEY", None)
    monkeypatch.setattr(proactive_advice, "build_briefing", lambda _uid: {
        "stats": {"today_total": 2, "overdue": 1, "waiting_overdue": 0, "blocked": 0},
        "top_priority": {"content": "给客户报价"},
        "today": [{"content": "给客户报价"}],
        "overdue": [{"content": "确认合同"}],
        "waiting_overdue": [],
        "blocked": [],
    })

    text = proactive_advice.generate_morning_advice("user-1")

    assert "给客户报价" in text
    assert "确认合同" in text
    assert len(text) <= 150


def test_evening_review_returns_none_without_risk(monkeypatch):
    monkeypatch.setattr(proactive_advice, "build_briefing", lambda _uid: {
        "stats": {"overdue": 0, "waiting_overdue": 0, "blocked": 0},
        "overdue": [], "waiting_overdue": [], "blocked": [],
    })
    assert proactive_advice.generate_evening_review("user-1") is None


def test_evening_fallback_lists_only_three_risks(monkeypatch):
    monkeypatch.setattr(proactive_advice, "DEEPSEEK_API_KEY", None)
    monkeypatch.setattr(proactive_advice, "build_briefing", lambda _uid: {
        "stats": {"overdue": 2, "waiting_overdue": 1, "blocked": 1},
        "overdue": [{"content": "任务1"}, {"content": "任务2"}],
        "waiting_overdue": [{"content": "任务3"}],
        "blocked": [{"content": "任务4"}],
    })
    text = proactive_advice.generate_evening_review("user-1")
    assert "任务1" in text and "任务3" in text
    assert "任务4" not in text
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_proactive_advice.py -q`

Expected: FAIL because `services.proactive_advice` does not exist.

- [ ] **Step 3: Implement pure fallback builders**

```python
def _names(items: list[dict], limit: int) -> list[str]:
    return [item.get("content", "未命名任务") for item in items[:limit]]


def _morning_fallback(briefing: dict) -> str:
    top = briefing.get("top_priority") or {}
    top_name = top.get("content") or "先确认今天最重要的一件事"
    overdue = _names(briefing.get("overdue") or [], 1)
    suffix = f"；另外先处理逾期的{overdue[0]}" if overdue else ""
    return f"早上好。今天建议先推进：{top_name}{suffix}。做完后回我进展，我继续帮你盯。"[:150]


def _evening_fallback(briefing: dict) -> str | None:
    risks = (
        _names(briefing.get("overdue") or [], 3)
        + _names(briefing.get("waiting_overdue") or [], 3)
        + _names(briefing.get("blocked") or [], 3)
    )[:3]
    if not risks:
        return None
    return ("晚上帮你收一下尾：" + "、".join(risks) + "还没有结果。建议现在确认下一步或明确延期。")[:150]
```

- [ ] **Step 4: Add AI generation with constrained input**

`generate_morning_advice(user_id)` and `generate_evening_review(user_id)` must call `build_briefing(user_id)` and `get_memory_context(user_id)`. The AI prompt must require concrete next action, maximum 150 Chinese characters, and no invented task. Validate non-empty output; on exception or invalid output use the fallback. Evening returns `None` before calling AI when all three risk lists are empty.

- [ ] **Step 5: Run advice tests**

Run: `python -m pytest backend/tests/test_proactive_advice.py -q`

Expected: PASS.

- [ ] **Step 6: Commit advice generation**

```bash
git add backend/services/proactive_advice.py backend/tests/test_proactive_advice.py
git commit -m "feat: generate proactive secretary advice"
```

### Task 5: Wire morning and evening jobs

**Files:**
- Modify: `backend/services/secretary.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_secretary.py`

- [ ] **Step 1: Write failing job tests**

Add tests that monkeypatch `bound_user_ids()` and generators:

```python
def test_push_morning_uses_generated_advice(monkeypatch):
    monkeypatch.setattr(secretary, "bound_user_ids", lambda: ["user-1"])
    monkeypatch.setattr(secretary, "generate_morning_advice", lambda _uid: "先处理客户报价。")
    monkeypatch.setattr(secretary, "send_secretary_message", fake_sender)
    secretary.push_morning_briefing()
    assert sent == [("user-1", "先处理客户报价。", "morning_briefing", None)]


def test_push_evening_skips_user_without_risk(monkeypatch):
    monkeypatch.setattr(secretary, "bound_user_ids", lambda: ["user-1"])
    monkeypatch.setattr(secretary, "generate_evening_review", lambda _uid: None)
    monkeypatch.setattr(secretary, "send_secretary_message", fake_sender)
    secretary.push_evening_review()
    assert sent == []
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_secretary.py -q`

Expected: FAIL because morning still uses the fixed markdown builder and evening job is missing.

- [ ] **Step 3: Implement the jobs**

```python
def push_morning_briefing() -> None:
    for user_id in bound_user_ids():
        try:
            content = generate_morning_advice(user_id)
            send_secretary_message(user_id, content, "morning_briefing")
        except Exception as exc:
            print(f"Morning briefing failed for {user_id}: {exc}")


def push_evening_review() -> None:
    for user_id in bound_user_ids():
        try:
            content = generate_evening_review(user_id)
            if content:
                send_secretary_message(user_id, content, "evening_review")
        except Exception as exc:
            print(f"Evening review failed for {user_id}: {exc}")
```

In `main.py`, import `push_evening_review`, change the morning cron to hour 8/minute 30, and add evening cron hour 19/minute 30. Keep S-level escalation at 20:00 and memory refresh unchanged.

- [ ] **Step 4: Run job and scheduler tests**

Run: `python -m pytest backend/tests/test_secretary.py backend/tests/test_proactive_advice.py backend/tests/test_proactive_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit scheduler wiring**

```bash
git add backend/services/secretary.py backend/main.py backend/tests/test_secretary.py
git commit -m "feat: schedule moderate secretary advice"
```

### Task 6: Complete phase-three verification

**Files:**
- Modify only if tests expose a defect in files already listed above.

- [ ] **Step 1: Run the complete backend suite**

Run: `python -m pytest backend/tests -q`

Expected: all tests PASS.

- [ ] **Step 2: Verify scheduler times**

Run: `rg -n "morning_briefing|evening_review|s_level_escalation|hour=|minute=" backend/main.py`

Expected: morning `08:30`, evening `19:30`, S-level `20:00`, weekly memory `Sunday 21:00`.

- [ ] **Step 3: Verify no model controls send frequency**

Run: `rg -n "DAILY_LIMIT|安静时段|同一任务|timedelta\(hours=3\)" backend/services/proactive_policy.py`

Expected: all limits are present in deterministic Python code.

- [ ] **Step 4: Verify user isolation**

Run: `rg -n "table\(\"users\"\)|table\(\"tasks\"\)|table\(\"secretary_outreach\"\)" backend/services/proactive_policy.py backend/services/proactive_advice.py backend/services/outreach.py`

Expected: every protected-table read/update uses the current `user_id` or `id` filter.

- [ ] **Step 5: Observe one full workday after deployment**

Record actual sent/skipped outreach rows and confirm: no message during quiet hours, no more than four proactive messages, no duplicate normal follow-up for one task, no evening message when there is no risk, and S-level escalation stops after a valid reply.

- [ ] **Step 6: Stop for final production acceptance**

Report automated tests, one-day observation, any skipped reasons and remaining platform caveats. Do not increase contact frequency until the user explicitly approves based on real usage.

