begin;

create table if not exists public.colleagues (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 100),
  wecom_userid text not null check (length(trim(wecom_userid)) between 1 and 100),
  aliases text[] not null default '{}',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_user_id, wecom_userid),
  unique (owner_user_id, id)
);

create table if not exists public.delegated_tasks (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  colleague_id uuid not null,
  content text not null check (length(trim(content)) between 1 and 1000),
  scheduled_at timestamptz not null,
  due_at timestamptz,
  approval_code text not null check (approval_code ~ '^[0-9]{4}$'),
  approval_code_history text[] not null default '{}',
  approval_status text not null default 'scheduled' check (approval_status in ('scheduled','pending_approval','approved','cancelled','expired')),
  delivery_status text not null default 'not_sent' check (delivery_status in ('not_sent','sending','sent','failed','uncertain')),
  task_status text not null default 'not_started' check (task_status in ('not_started','awaiting_reply','acknowledged','in_progress','completed','delayed','unresponsive','cancelled')),
  approval_revision int not null default 0,
  approval_requested_at timestamptz,
  approval_reminded_at timestamptz,
  approved_at timestamptz,
  sent_at timestamptz,
  next_followup_at timestamptz,
  followup_count int not null default 0 check (followup_count between 0 and 2),
  daily_reminder_count int not null default 0 check (daily_reminder_count between 0 and 2),
  reminder_count_date date,
  last_colleague_reply_at timestamptz,
  paused_reason text,
  version int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (owner_user_id, colleague_id) references public.colleagues(owner_user_id, id),
  check (due_at is null or due_at >= scheduled_at),
  unique (owner_user_id, approval_code),
  unique (owner_user_id, id)
);

create table if not exists public.delegated_task_events (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  actor_type text not null check (actor_type in ('owner','colleague','system')),
  event_type text not null,
  note text,
  created_at timestamptz not null default now(),
  foreign key (owner_user_id, task_id) references public.delegated_tasks(owner_user_id, id) on delete cascade
);

create table if not exists public.delegation_outbox (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  task_id uuid not null,
  operation_key text not null unique,
  recipient_userid text not null,
  content text not null,
  kind text not null check (kind in ('approval','approval_reminder','dispatch','followup','notice')),
  status text not null default 'pending' check (status in ('pending','sending','sent','failed','uncertain','cancelled')),
  attempts int not null default 0 check (attempts between 0 and 2),
  applied boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (owner_user_id, task_id) references public.delegated_tasks(owner_user_id, id) on delete cascade
);

create index if not exists idx_delegation_owner_scheduled on public.delegated_tasks(owner_user_id, approval_status, scheduled_at);
create index if not exists idx_delegation_followup on public.delegated_tasks(owner_user_id, task_status, next_followup_at);
create index if not exists idx_delegation_events on public.delegated_task_events(owner_user_id, task_id, created_at);
create index if not exists idx_delegation_outbox on public.delegation_outbox(owner_user_id, status, applied);

alter table public.colleagues enable row level security;
alter table public.delegated_tasks enable row level security;
alter table public.delegated_task_events enable row level security;
alter table public.delegation_outbox enable row level security;

-- Direct clients may read their own state; all mutations go through authenticated backend.
drop policy if exists "read own colleagues" on public.colleagues;
create policy "read own colleagues" on public.colleagues for select to authenticated using (auth.uid() = owner_user_id);
drop policy if exists "read own delegations" on public.delegated_tasks;
create policy "read own delegations" on public.delegated_tasks for select to authenticated using (auth.uid() = owner_user_id);
drop policy if exists "read own delegation events" on public.delegated_task_events;
create policy "read own delegation events" on public.delegated_task_events for select to authenticated using (auth.uid() = owner_user_id);

revoke all on public.colleagues, public.delegated_tasks, public.delegated_task_events, public.delegation_outbox from anon, authenticated;
grant select on public.colleagues, public.delegated_tasks, public.delegated_task_events to authenticated;
grant all on public.colleagues, public.delegated_tasks, public.delegated_task_events, public.delegation_outbox to service_role;

commit;
