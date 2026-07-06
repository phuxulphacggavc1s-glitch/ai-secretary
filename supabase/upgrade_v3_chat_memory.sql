-- V3 升级：删除冗余字段 + 秘书对话流 + 用户记忆层
-- 在 Supabase SQL Editor 中执行（先部署新后端，再执行本脚本）

-- 1. 删除三个不实用的字段
alter table public.tasks drop column if exists goal;
alter table public.tasks drop column if exists success_criteria;
alter table public.tasks drop column if exists related_person;

-- 2. 秘书对话消息表
create table if not exists public.secretary_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  role text not null check (role in ('user', 'secretary')),
  content text not null,
  created_at timestamptz default now()
);
create index if not exists idx_secretary_messages_user
  on public.secretary_messages(user_id, created_at desc);

alter table public.secretary_messages enable row level security;
drop policy if exists "own messages" on public.secretary_messages;
create policy "own messages" on public.secretary_messages
  for all using (auth.uid() = user_id);

-- 3. 用户记忆表（AI 每周提炼的画像 + 随聊随记的事实清单）
create table if not exists public.user_memory (
  user_id uuid primary key references public.users(id) on delete cascade,
  profile_text text,
  facts jsonb default '[]'::jsonb,
  task_count int default 0,
  updated_at timestamptz default now()
);
alter table public.user_memory add column if not exists facts jsonb default '[]'::jsonb;

alter table public.user_memory enable row level security;
drop policy if exists "own memory" on public.user_memory;
create policy "own memory" on public.user_memory
  for all using (auth.uid() = user_id);
