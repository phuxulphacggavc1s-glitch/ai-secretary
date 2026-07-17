create table if not exists public.wecom_inbound_messages (
  id uuid primary key default gen_random_uuid(),
  msg_id text not null unique,
  user_id uuid references public.users(id) on delete cascade not null,
  wecom_userid text not null,
  content text not null,
  status text not null default 'processing'
    check (status in ('processing', 'processed', 'failed')),
  failure_reason text,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_wecom_inbound_user_created
  on public.wecom_inbound_messages(user_id, created_at desc);

alter table public.wecom_inbound_messages enable row level security;
drop policy if exists "own wecom inbound messages" on public.wecom_inbound_messages;
create policy "own wecom inbound messages"
  on public.wecom_inbound_messages for all using (auth.uid() = user_id);
