-- Requires v7 delegation and v8 private-message candidate validation.
-- PostgreSQL ALTER TABLE/constraints and Supabase RLS references:
-- https://www.postgresql.org/docs/current/sql-altertable.html
-- https://www.postgresql.org/docs/current/ddl-constraints.html
-- https://supabase.com/docs/guides/database/postgres/row-level-security
begin;

-- Preserve historical codes, checks, uniqueness and formal approval state.
alter table public.delegated_tasks alter column approval_code drop not null;

create table if not exists public.delegation_command_contexts (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  actor_userid text not null
    check (length(actor_userid) between 1 and 64
           and actor_userid = lower(actor_userid)
           and actor_userid = trim(actor_userid)),
  operation text not null check (operation in ('approve', 'cancel', 'modify', 'reply')),
  candidates jsonb not null default '[]'::jsonb
    check (public.private_message_candidates_valid(candidates)),
  parameters jsonb not null default '{}'::jsonb check (jsonb_typeof(parameters) = 'object'),
  expires_at timestamptz not null,
  version int not null default 0 check (version >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_user_id, actor_userid),
  unique (owner_user_id, id)
);

comment on column public.delegation_command_contexts.candidates is
  'Only internal task UUIDs and observed versions; no body, names or summary snapshots.';
comment on column public.delegation_command_contexts.parameters is
  'Temporary server-only command parameters; never grant direct client access.';

create or replace function public.delegation_command_context_guard_identity()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if new.id is distinct from old.id
     or new.owner_user_id is distinct from old.owner_user_id
     or new.actor_userid is distinct from old.actor_userid then
    raise exception using errcode = '23514', message = 'DELEGATION_CONTEXT_IDENTITY_IMMUTABLE';
  end if;
  return new;
end;
$$;

drop trigger if exists delegation_context_identity on public.delegation_command_contexts;
create trigger delegation_context_identity before update on public.delegation_command_contexts
  for each row execute function public.delegation_command_context_guard_identity();

create index if not exists idx_delegation_command_contexts_expiry
  on public.delegation_command_contexts(owner_user_id, expires_at);

alter table public.delegation_command_contexts enable row level security;
revoke all on public.delegation_command_contexts from public, anon, authenticated;
grant select, insert, update, delete on public.delegation_command_contexts to service_role;

revoke all on function public.delegation_command_context_guard_identity() from public, anon, authenticated;
grant execute on function public.delegation_command_context_guard_identity() to service_role;

commit;
