# Code-Free Commands and Automatic Notices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Those named skills are not installed here; use bounded existing workers with disjoint ownership and parent-led integration. Steps use checkboxes.

**Goal:** Remove visible/required task shortcodes and route explicitly scheduled messages to once-confirmed, automatic private delivery while retaining formal task approvals.

**Architecture:** Extend the finite private parser; keep formal task lifecycle unchanged. Persist delegation menu ids/versions and coordinate menu ownership with existing private contexts. Keep old data, render pending output code-free at send time, and do not auto-convert old tasks.

**Tech Stack:** Existing FastAPI, Supabase/Postgres, httpx, React/Vite, pytest and Playwright smoke tests.

## Task 1: Message Recognition (Parent)

Files: backend/services/private_message_policy.py; backend/services/delegation_parser.py; backend/tests/test_private_message_policy.py; backend/tests/test_delegation_parser.py.

- [x] Add failing parser and route tests before implementation:
~~~python
text = "1分钟后给谭筱莹发消息提醒他4点下班"
assert is_private_request(text)
assert not is_delegation_request(text)
data = parse_request(text, PEOPLE, NOW)
assert data["content"] == "提醒他4点下班"
assert data["scheduled_at"] == (NOW + timedelta(minutes=1)).isoformat()
~~~
- [x] Run backend/.venv/Scripts/python.exe -m pytest backend/tests/test_private_message_policy.py backend/tests/test_delegation_parser.py -q; observe incorrect route before changes.
- [x] Add deterministic message-intent patterns for 留言/发消息/发送一条消息/发信息/发提醒/发通知 in the request header. Preserve explicit formal-task phrases and negation/personal-reminder guards.
- [x] parse_request separates non-clock colon header/body; otherwise extracts recipient and explicit message marker, keeping the remaining body without AI. Parse time only from the sending header, not clocks in body. Missing time, unknown recipient, empty/long body fail safely; match registered names/aliases or case-insensitive UserID, never fuzzy names.
- [x] Re-run route tests, including personal "提醒我", 已经/不要, task/notice words in body, alias ambiguity, no save/AI/send.

## Task 2: Schema (Volta Worker)

Files: create supabase/upgrade_v9_code_free_commands.sql; backend/tests/test_code_free_schema.py.

- [x] Failing schema tests: approval_code nullable; old rows preserved; multiple null codes allowed; contexts are actor-scoped, candidate JSON only id/version, client roles denied.
- [x] Migration in one transaction. Alter delegated_tasks.approval_code DROP NOT NULL; keep historical checks and unique constraint. No data conversion, delete or feature enabling.
- [x] Create delegation_command_contexts: id UUID, owner_user_id users FK, actor_userid normalized lowercase text1..64, operation approve/cancel/modify/reply, candidates JSON id/version checked by existing private_message_candidates_valid, parameters JSON object, expires_at, version>=0, created_at/updated_at; unique(owner_user_id,actor_userid) and unique(owner_user_id,id).
- [x] RLS, revoke public/anon/authenticated; CRUD service_role only; expiry index. Immutability of id/owner/actor guards against rebinding. No personal seeds.
- [x] Execute v7+v8+v9 and repeated v9 on disposable PostgreSQL only; assert role privileges, null-code inserts and cross-user/context constraints, then stop instance. No production SQL.

## Task 3: Menu Coordination (Parent)

Files: create backend/services/wecom_menu.py; backend/tests/test_wecom_menu.py; modify private_message_service.py/private_message_entry.py and private fake tests.

- [x] Add failing tests for different business menus superseding old numeric choices; actor/space isolation and stale context version.
- [x] Define MENU_LOCK=RLock shared by both callback entries.
~~~python
from threading import RLock
from services.private_message_policy import as_time
MENU_LOCK = RLock()

def expire_other_menu(db, space, userid, source, now):
    if source == "private":
        table, scope_key, actor_key, actor = (
            "delegation_command_contexts", "owner_user_id", "actor_userid", userid.lower())
    elif source == "delegation":
        people = db.table("private_message_participants").select("id,wecom_userid").eq(
            "space_id", space).limit(1000).execute().data
        matches = [p for p in people if p["wecom_userid"].lower() == userid.lower()]
        if len(matches) != 1:
            return
        table, scope_key, actor_key, actor = (
            "private_message_contexts", "space_id", "actor_id", matches[0]["id"])
    else:
        raise ValueError("Unknown menu source")
    rows = db.table(table).select("id,version").eq(scope_key, space).eq(
        actor_key, actor).limit(1).execute().data
    for row in rows:
        db.table(table).update({"expires_at":now.isoformat(), "updated_at":now.isoformat(),
                               "version":row["version"]+1}).eq(scope_key, space).eq(
            actor_key, actor).eq("id", row["id"]).eq("version", row["version"]).execute()

def delegation_context_active(db, owner, userid, now):
    rows = db.table("delegation_command_contexts").select("id,expires_at").eq(
        "owner_user_id", owner).eq("actor_userid", userid.lower()).limit(1).execute().data
    return bool(rows and as_time(rows[0]["expires_at"]) > now)
~~~
- [x] Private menu calls expire_other_menu(...,"private",clock()) before writing its menu. Delegation menu calls the same helper with "delegation".
- [x] Private numeric routing yields to a valid delegation menu only when its own context is expired; otherwise it retains current context validation. Bare 收到 ambiguity prompts task-specific or private-specific commands, never shortcodes.
- [x] Missing new schema fails closed for private payloads; never fall through to AI/legacy content storage.

## Task 4: Formal Task Commands and Templates (Ramanujan Worker)

Files: backend/services/delegation.py; delegation_policy.py; delegation_entry.py; delegation_delivery.py; create delegation_commands.py if needed; backend/tests/test_delegation.py/test_delegation_entry.py/test_delegation_delivery.py/test_code_free_delegation.py.

- [x] Add failing tests for all templates/entry success without codes; multiple approve/modify/cancel/colleague-reply candidates; stale menus; recipient/owner isolation; legacy approval unchanged.
- [x] New create_task stores approval_code=None and no code generation; modified content clears historical visible code and invalidates old approval revision. Old explicit coded commands may be accepted solely for existing unmodified legacy records, never displayed or required.
- [x] Command contexts use only actor_userid.lower(), current authenticated owner lookup or validated colleague identity. Single eligible record direct; multi menu shows name/content excerpt/time and ordinal. 10min TTL, choose verifies task version/eligibility and claims context by id/version before action.
- [x] Formal approval stays pending_approval until owner explicitly agrees. Add task-specific commands (任务收到/任务完成/任务进展/批准任务) to avoid private ambiguity; ordinary replies only with unique task or explicit menu selection.
- [x] Retain existing received/complete/delay/followup behavior, no negative-text false acknowledgements. Resolve uncertain dispatch by the intended colleague's definite reply and explicit target selection, not bare guessed text.
- [x] Strip shortcode interpolation from approval, dispatch, followup, owner notification and creation responses. Before sending a persisted legacy outbox item, render code-free control text against its verified revision; preserve task body digits verbatim. Do not resend successful items or alter scheduling.
- [x] Disable platform content-equality duplicate checking for separate legitimate identical tasks, matching private adapter policy; rely on existing persistent unique operation claims and uncertainty pause. Add duplicate-identical-message regression.
- [x] Use MENU_LOCK in callback handling and expire_other_menu on delegation menu creation. Numeric private menu should not reach colleague progress handling.
- [x] Re-run existing/new delegation regressions; adapt obsolete generated-code expectations into version/context tests without dropping authorization/recovery coverage.

## Task 5: UI and Integration (Ramanujan UI; Parent Integration)

Files: frontend/src/pages/Delegations.jsx; frontend/tests/delegations.smoke.cjs; backend/tests/test_private_message_entry.py; backend/tests/test_delegation_parser.py; new integration tests.

- [x] Add UI assertion that old record with approval_code1234 does not display it; preserve row-id buttons and list states.
- [x] Remove only the code badge, keeping colleague/status/layout/actions. Build and test desktop1280x900 and mobile375x812 with mocked auth/API.
- [x] End-to-end mock callback test: natural message -> private draft; no delegated_tasks/legacy body/AI; confirmation once -> schedule; at due -> recipient once, never approval; formal "下达任务" -> pending approval only.
- [x] Tests for code-free multi choices across both domains, disabled/unknown member, no new permission scope, old task remains unapproved, repeated callback no duplicates.

## Task 6: Verify, Review and Rollout

Files: docs/wecom-code-free-notices-rollout.md; approved spec and this plan statuses.

- [x] Run complete backend tests with mocks and disposable schema only. Never import main against live .env or post real messages.
- [x] Run npm run build and Playwright smoke from existing helper/runtime; stop required test server when finished. No new library/framework/dependency updates.
- [x] Independent review: scope, private body isolation, menu arbitration, CAS, legacy outbox rendering, no spontaneous pending-task auto send.
- [x] Record known existing Python3.14/OpenAI/Pydantic warnings, no false claim of live e2e.
- [x] Preserve preexisting AGENTS.md/setup-manual changes. Commit only feature paths after passing tests.
- [x] Document migration-before-code order, backup, backend/frontend deployment and rollback; no production DB writes or real sends in local implementation. Reverify official WeCom/Supabase docs for platform parameters and instructions. Existing private/delegation switches remain unchanged.

## Outcome

Local implementation complete. Backend: 501 passed (44 existing warnings). Frontend build and desktop/mobile mocked smoke passed; screenshots inspected. Disposable PostgreSQL migration and permissions validated; test services stopped. Independent review findings fixed and rechecked. No production migration/deployment, actual messages or AI requests; those remain separate rollout steps.
