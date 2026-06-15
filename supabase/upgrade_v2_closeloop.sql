alter table public.tasks add column if not exists goal text;
alter table public.tasks add column if not exists success_criteria text;
alter table public.tasks add column if not exists related_person text;
alter table public.tasks add column if not exists next_action text;
alter table public.tasks add column if not exists next_follow_time timestamptz;
alter table public.tasks add column if not exists priority_level text default 'B'
  check (priority_level in ('S','A','B'));

alter table public.tasks drop constraint if exists tasks_status_check;
alter table public.tasks add constraint tasks_status_check
  check (status in ('pending','in_progress','waiting_response','blocked','done','cancelled'));

update public.tasks set priority_level =
  case when priority = 3 then 'S' when priority = 2 then 'A' else 'B' end
  where priority_level is null;

alter table public.users add column if not exists wecom_webhook text;

create table if not exists public.task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references public.tasks(id) on delete cascade not null,
  user_id uuid references public.users(id) on delete cascade not null,
  event_type text not null,
  from_status text,
  to_status text,
  ai_raw jsonb,
  note text,
  created_at timestamptz default now()
);
create index if not exists idx_task_events_task on public.task_events(task_id, created_at desc);
alter table public.task_events enable row level security;
drop policy if exists "Users see own task_events" on public.task_events;
create policy "Users see own task_events" on public.task_events for all using (auth.uid() = user_id);

create index if not exists idx_tasks_followup on public.tasks(next_follow_time, status)
  where status not in ('done','cancelled');
