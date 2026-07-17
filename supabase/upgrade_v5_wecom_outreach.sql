-- V5 升级：企业微信主动消息外联记录与任务跟进暂停

alter table public.tasks
  add column if not exists followup_paused boolean not null default false;

create table if not exists public.secretary_outreach (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  task_id uuid references public.tasks(id) on delete cascade,
  kind text not null check (kind in (
    'morning_briefing',
    'task_followup',
    's_escalation',
    'evening_review'
  )),
  content text not null,
  status text not null default 'pending' check (status in (
    'pending',
    'sent',
    'failed',
    'replied',
    'expired'
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
