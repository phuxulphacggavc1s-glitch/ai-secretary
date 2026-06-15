create extension if not exists "pgcrypto";

create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique,
  nickname text,
  timezone text default 'Asia/Shanghai',
  created_at timestamp with time zone default now()
);

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  content text not null,
  category text default '其他',
  remind_time timestamp with time zone,
  status text default 'pending' check (status in ('pending', 'in_progress', 'waiting_response', 'blocked', 'done', 'cancelled')),
  reminded boolean default false,
  priority int default 1 check (priority in (1, 2, 3)),
  priority_level text default 'B' check (priority_level in ('S','A','B')),
  ai_summary text,
  progress_note text,
  goal text,
  success_criteria text,
  related_person text,
  next_action text,
  next_follow_time timestamp with time zone,
  last_checkin_at timestamp with time zone,
  snooze_until timestamp with time zone,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create index idx_tasks_user_id on public.tasks(user_id);
create index idx_tasks_status_user on public.tasks(user_id, status);
create index idx_tasks_remind on public.tasks(remind_time, status, reminded)
  where remind_time is not null and status = 'pending' and reminded = false;
create index idx_tasks_followup on public.tasks(next_follow_time, status)
  where status not in ('done','cancelled');

create table public.task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references public.tasks(id) on delete cascade not null,
  user_id uuid references public.users(id) on delete cascade not null,
  event_type text not null,
  from_status text,
  to_status text,
  ai_raw jsonb,
  note text,
  created_at timestamp with time zone default now()
);
create index idx_task_events_task on public.task_events(task_id, created_at desc);

create table public.daily_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  report_date date not null,
  content text,
  done_count int default 0,
  pending_count int default 0,
  created_at timestamp with time zone default now(),
  unique(user_id, report_date)
);

alter table public.tasks enable row level security;
alter table public.daily_reports enable row level security;
alter table public.users enable row level security;
alter table public.task_events enable row level security;

create policy "Users can only see own tasks"
  on public.tasks for all using (auth.uid() = user_id);

create policy "Users can only see own reports"
  on public.daily_reports for all using (auth.uid() = user_id);

create policy "Users can see own profile"
  on public.users for all using (auth.uid() = id);

create policy "Users see own task_events"
  on public.task_events for all using (auth.uid() = user_id);
