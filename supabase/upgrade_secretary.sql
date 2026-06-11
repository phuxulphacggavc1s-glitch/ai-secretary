alter table public.tasks drop constraint if exists tasks_status_check;

alter table public.tasks add constraint tasks_status_check
  check (status in ('pending', 'in_progress', 'done'));

alter table public.tasks add column if not exists progress_note text;
alter table public.tasks add column if not exists last_checkin_at timestamp with time zone;
alter table public.tasks add column if not exists snooze_until timestamp with time zone;

create index if not exists idx_tasks_status_user on public.tasks(user_id, status);
