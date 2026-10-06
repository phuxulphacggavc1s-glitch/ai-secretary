-- Contract checked against PostgreSQL constraints/triggers and Supabase RLS docs:
-- https://www.postgresql.org/docs/current/ddl-constraints.html
-- https://www.postgresql.org/docs/current/sql-createtrigger.html
-- https://supabase.com/docs/guides/database/postgres/row-level-security
-- No participant seed or feature enablement is performed by this migration.
begin;

create table if not exists public.private_message_participants (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  wecom_userid text not null check (length(trim(wecom_userid)) between 1 and 100),
  name text not null check (length(trim(name)) between 1 and 100),
  aliases text[] not null default '{}',
  active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (space_id, wecom_userid),
  unique (space_id, id)
);

create table if not exists public.private_message_threads (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  participant_a uuid not null,
  participant_b uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (space_id, participant_a) references public.private_message_participants(space_id, id),
  foreign key (space_id, participant_b) references public.private_message_participants(space_id, id),
  check (participant_a < participant_b),
  unique (space_id, participant_a, participant_b),
  unique (space_id, id)
);

create table if not exists public.private_messages (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  thread_id uuid not null,
  sender_id uuid not null,
  recipient_id uuid not null,
  content text not null check (octet_length(content) between 1 and 1200 and length(trim(content)) > 0),
  delivery_mode text not null check (delivery_mode in ('immediate', 'scheduled')),
  scheduled_at timestamptz,
  status text not null default 'draft'
    check (status in ('draft', 'scheduled', 'sending', 'sent', 'failed', 'uncertain', 'cancelled', 'expired')),
  version int not null default 0 check (version >= 0),
  confirmed_at timestamptz,
  sent_at timestamptz,
  acknowledged_at timestamptz,
  failure_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (space_id, thread_id) references public.private_message_threads(space_id, id),
  foreign key (space_id, sender_id) references public.private_message_participants(space_id, id),
  foreign key (space_id, recipient_id) references public.private_message_participants(space_id, id),
  check (sender_id <> recipient_id),
  unique (space_id, id)
);

create table if not exists public.private_message_outbox (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  message_id uuid not null,
  recipient_id uuid not null,
  kind text not null check (kind in ('delivery', 'notice', 'receipt')),
  operation_key text not null unique,
  status text not null default 'pending'
    check (status in ('pending', 'sending', 'sent', 'failed', 'uncertain', 'cancelled')),
  attempts int not null default 0 check (attempts between 0 and 2),
  applied boolean not null default false,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (space_id, message_id) references public.private_messages(space_id, id) on delete cascade,
  foreign key (space_id, recipient_id) references public.private_message_participants(space_id, id),
  unique (space_id, id)
);

create table if not exists public.private_message_inbound (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  msg_id text not null check (length(trim(msg_id)) > 0),
  sender_userid text not null check (length(trim(sender_userid)) > 0),
  status text not null default 'processing' check (status in ('processing', 'processed', 'failed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (space_id, msg_id),
  unique (space_id, id)
);

-- Pure JSON validation: candidate lists cannot become another body/snapshot store.
create or replace function public.private_message_candidates_valid(value jsonb)
returns boolean
language plpgsql immutable
set search_path = pg_catalog, public
as $$
declare
  candidate jsonb;
begin
  if value is null or jsonb_typeof(value) <> 'array' then
    return false;
  end if;
  for candidate in select * from jsonb_array_elements(value) loop
    if jsonb_typeof(candidate) <> 'object' then
      return false;
    end if;
    if not (candidate ?& array['id', 'version'])
       or candidate - 'id' - 'version' <> '{}'::jsonb
       or jsonb_typeof(candidate -> 'id') <> 'string'
       or jsonb_typeof(candidate -> 'version') <> 'number'
       or (candidate ->> 'id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       or (candidate ->> 'version') !~ '^[0-9]+$' then
      return false;
    end if;
    if (candidate ->> 'version')::numeric > 2147483647 then
      return false;
    end if;
  end loop;
  return true;
end;
$$;

create table if not exists public.private_message_contexts (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.users(id) on delete cascade,
  actor_id uuid not null,
  operation text not null check (length(trim(operation)) > 0),
  candidates jsonb not null default '[]'::jsonb
    check (public.private_message_candidates_valid(candidates)),
  parameters jsonb not null default '{}'::jsonb check (jsonb_typeof(parameters) = 'object'),
  expires_at timestamptz not null,
  version int not null default 0 check (version >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (space_id, actor_id) references public.private_message_participants(space_id, id) on delete cascade,
  unique (space_id, actor_id),
  unique (space_id, id)
);

comment on column public.private_message_contexts.candidates is
  'Only internal message UUIDs and observed versions; never body, names or summaries.';
comment on column public.private_message_contexts.parameters is
  'Temporary runtime private-action parameters only, including edit/reply content; server-only, not candidate snapshots.';

-- Fixed identities keep child validations true even after later parent updates.
create or replace function public.private_message_guard_identity()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if new.id is distinct from old.id or new.space_id is distinct from old.space_id then
    raise exception using errcode = '23514', message = 'PRIVATE_IDENTITY_IMMUTABLE';
  end if;
  if tg_table_name = 'private_message_participants' then
    if new.wecom_userid is distinct from old.wecom_userid then
      raise exception using errcode = '23514', message = 'PRIVATE_PARTICIPANT_USERID_IMMUTABLE';
    end if;
  elsif tg_table_name = 'private_message_threads' then
    if new.participant_a is distinct from old.participant_a
       or new.participant_b is distinct from old.participant_b then
      raise exception using errcode = '23514', message = 'PRIVATE_THREAD_PARTIES_IMMUTABLE';
    end if;
  elsif tg_table_name = 'private_messages' then
    if new.thread_id is distinct from old.thread_id
       or new.sender_id is distinct from old.sender_id
       or new.recipient_id is distinct from old.recipient_id then
      raise exception using errcode = '23514', message = 'PRIVATE_MESSAGE_PARTIES_IMMUTABLE';
    end if;
  end if;
  return new;
end;
$$;

create or replace function public.private_message_validate_parties()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
  pair public.private_message_threads%rowtype;
begin
  select * into pair from public.private_message_threads
    where space_id = new.space_id and id = new.thread_id for key share;
  if not found or not (
    (new.sender_id = pair.participant_a and new.recipient_id = pair.participant_b)
    or (new.sender_id = pair.participant_b and new.recipient_id = pair.participant_a)
  ) then
    raise exception using errcode = '23514', message = 'PRIVATE_MESSAGE_INVALID_PARTIES';
  end if;
  return new;
end;
$$;

create or replace function public.private_message_validate_outbox_target()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
  item public.private_messages%rowtype;
  target_id uuid;
begin
  select * into item from public.private_messages
    where space_id = new.space_id and id = new.message_id for key share;
  if not found then
    raise exception using errcode = '23514', message = 'PRIVATE_OUTBOX_INVALID_MESSAGE';
  end if;
  target_id := case new.kind
    when 'delivery' then item.recipient_id
    when 'notice' then item.sender_id
    when 'receipt' then item.sender_id
    else null end;
  if target_id is null or new.recipient_id is distinct from target_id then
    raise exception using errcode = '23514', message = 'PRIVATE_OUTBOX_INVALID_TARGET';
  end if;
  return new;
end;
$$;

drop trigger if exists private_participant_identity on public.private_message_participants;
create trigger private_participant_identity before update on public.private_message_participants
  for each row execute function public.private_message_guard_identity();
drop trigger if exists private_thread_identity on public.private_message_threads;
create trigger private_thread_identity before update on public.private_message_threads
  for each row execute function public.private_message_guard_identity();
drop trigger if exists private_message_identity on public.private_messages;
create trigger private_message_identity before update on public.private_messages
  for each row execute function public.private_message_guard_identity();
drop trigger if exists private_message_parties on public.private_messages;
create trigger private_message_parties before insert or update on public.private_messages
  for each row execute function public.private_message_validate_parties();
drop trigger if exists private_outbox_target on public.private_message_outbox;
create trigger private_outbox_target before insert or update on public.private_message_outbox
  for each row execute function public.private_message_validate_outbox_target();

-- Internal-app plaintext UserID is case-insensitive (checked 2026-10-06):
-- https://identity.tencent.com/docs/guides/SyncConfig/configItem/mapping/
-- Keep the original exact-value unique constraint for the service contract.
create unique index if not exists idx_private_message_participants_userid_ci
  on public.private_message_participants(space_id, lower(wecom_userid));

create index if not exists idx_private_messages_due
  on public.private_messages(space_id, status, scheduled_at);
create index if not exists idx_private_messages_thread
  on public.private_messages(space_id, thread_id, created_at);
create index if not exists idx_private_messages_sender
  on public.private_messages(space_id, sender_id, status, created_at);
create index if not exists idx_private_messages_recipient
  on public.private_messages(space_id, recipient_id, status, created_at);
create index if not exists idx_private_message_outbox_pending
  on public.private_message_outbox(space_id, status, applied, created_at);
create index if not exists idx_private_message_contexts_expiry
  on public.private_message_contexts(space_id, expires_at);

-- The space owner has no client privilege or implicit body-read policy.
alter table public.private_message_participants enable row level security;
alter table public.private_message_threads enable row level security;
alter table public.private_messages enable row level security;
alter table public.private_message_outbox enable row level security;
alter table public.private_message_inbound enable row level security;
alter table public.private_message_contexts enable row level security;

revoke all on public.private_message_participants from public, anon, authenticated;
revoke all on public.private_message_threads from public, anon, authenticated;
revoke all on public.private_messages from public, anon, authenticated;
revoke all on public.private_message_outbox from public, anon, authenticated;
revoke all on public.private_message_inbound from public, anon, authenticated;
revoke all on public.private_message_contexts from public, anon, authenticated;

grant select, insert, update, delete on public.private_message_participants to service_role;
grant select, insert, update, delete on public.private_message_threads to service_role;
grant select, insert, update, delete on public.private_messages to service_role;
grant select, insert, update, delete on public.private_message_outbox to service_role;
grant select, insert, update, delete on public.private_message_inbound to service_role;
grant select, insert, update, delete on public.private_message_contexts to service_role;

revoke all on function public.private_message_candidates_valid(jsonb) from public, anon, authenticated;
revoke all on function public.private_message_guard_identity() from public, anon, authenticated;
revoke all on function public.private_message_validate_parties() from public, anon, authenticated;
revoke all on function public.private_message_validate_outbox_target() from public, anon, authenticated;
grant execute on function public.private_message_candidates_valid(jsonb) to service_role;
grant execute on function public.private_message_guard_identity() to service_role;
grant execute on function public.private_message_validate_parties() to service_role;
grant execute on function public.private_message_validate_outbox_target() to service_role;

commit;
