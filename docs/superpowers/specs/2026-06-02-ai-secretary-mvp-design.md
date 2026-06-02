# AI Secretary MVP Design

## Scope

Build the web MVP described in `AGENTS.md`: a Chinese AI life secretary with email/password login, natural-language task capture, AI parse preview, editable confirmation, categorized task list, email reminders, and daily summary retrieval.

## Architecture

The app has a React + Vite + Tailwind frontend and a Python FastAPI backend. Supabase provides auth and database storage. The frontend authenticates with Supabase and sends the access token to FastAPI. FastAPI verifies the token through Supabase, parses tasks through DeepSeek, stores confirmed tasks, checks due reminders with APScheduler, and generates daily reports at 21:00 Asia/Shanghai.

## Components

- `backend/config.py`: loads environment settings.
- `backend/database.py`: creates the Supabase service client lazily.
- `backend/services/ai_parser.py`: parses Chinese task input and falls back to a manual task if AI fails.
- `backend/routers/tasks.py`: parse, create, list, update, and delete task endpoints.
- `backend/routers/reports.py`: daily report endpoint.
- `frontend/src/pages`: login, home, and task list pages.
- `frontend/src/components`: task input, cards, parse preview, time picker, and daily report.
- `supabase/schema.sql`: database and RLS setup.

## UX

The first screen after login is the task capture workflow: type one sentence, preview AI result, edit fields, set time if unclear, and save. UI is Chinese, mobile-first, with a white background and indigo primary color.

## Error Handling

Backend AI errors return a fallback parse result instead of crashing. Frontend API calls use `try/catch`, show inline/toast-like errors, redirect unauthorized users through auth state, and keep empty states explicit.

## Testing

Backend tests cover config defaults, parser fallback behavior, and schema validation. Frontend validation is by build where dependencies are available.
