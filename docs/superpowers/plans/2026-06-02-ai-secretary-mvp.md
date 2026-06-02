# AI Secretary MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full-stack Chinese AI Secretary MVP from `AGENTS.md`.

**Architecture:** React authenticates with Supabase and calls FastAPI using bearer tokens. FastAPI verifies users through Supabase, calls DeepSeek for parsing and reports, writes tasks/reports to Supabase, and runs APScheduler jobs for reminders and daily summaries.

**Tech Stack:** React 18, Vite, TailwindCSS, Supabase JS, Axios, FastAPI, Pydantic, Supabase Python, OpenAI-compatible DeepSeek client, Resend, APScheduler.

---

### Task 1: Backend Foundation

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/database.py`
- Create: `backend/models/schemas.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/test_ai_parser.py`

- [ ] Write tests for config defaults and AI parser fallback.
- [ ] Run `python -m pytest backend/tests -q` and confirm expected failures before production code exists.
- [ ] Implement config, lazy Supabase client, schemas, and parser fallback.
- [ ] Run backend tests again and confirm pass.

### Task 2: Backend API and Services

**Files:**
- Create: `backend/auth.py`
- Create: `backend/routers/tasks.py`
- Create: `backend/routers/reports.py`
- Create: `backend/services/email_service.py`
- Create: `backend/services/reminder.py`
- Create: `backend/services/daily_report.py`
- Create: `backend/main.py`

- [ ] Implement auth token verification with Supabase.
- [ ] Implement task parse/create/list/update/delete endpoints.
- [ ] Implement daily report endpoint.
- [ ] Implement reminder and daily summary jobs with defensive error handling.
- [ ] Run `python -m compileall backend`.

### Task 3: Frontend Application

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/supabase.js`
- Create: `frontend/src/api.js`
- Create: `frontend/src/hooks/useAuth.js`
- Create: `frontend/src/hooks/useTasks.js`
- Create: `frontend/src/pages/Login.jsx`
- Create: `frontend/src/pages/Home.jsx`
- Create: `frontend/src/pages/Tasks.jsx`
- Create: `frontend/src/components/TaskInput.jsx`
- Create: `frontend/src/components/TaskCard.jsx`
- Create: `frontend/src/components/TaskList.jsx`
- Create: `frontend/src/components/ParsePreview.jsx`
- Create: `frontend/src/components/TimePickerModal.jsx`
- Create: `frontend/src/components/DailyReport.jsx`
- Create: `frontend/src/index.css`

- [ ] Implement Supabase auth and protected routing.
- [ ] Implement task capture, parse preview, manual time selection, task list, and daily report UI.
- [ ] Run `npm install` if network is available, then `npm run build`.

### Task 4: Setup Docs

**Files:**
- Create: `supabase/schema.sql`
- Create: `backend/.env.example`
- Create: `frontend/.env.local.example`
- Modify: `README.md`
- Create: `.gitignore`

- [ ] Add exact Supabase SQL from `AGENTS.md`.
- [ ] Add env examples without secrets.
- [ ] Update README with setup and run steps.

### Self-Review

- Spec coverage: login, parsing, confirmation, task CRUD, reminders, daily summary, Chinese UI, mobile-first frontend, and setup docs are covered.
- Placeholder scan: no implementation placeholders are intentionally left in code-facing tasks.
- Type consistency: frontend and backend use `raw_input`, `content`, `category`, `remind_time`, `priority`, and `status` consistently with `AGENTS.md`.
