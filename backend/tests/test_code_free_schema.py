from pathlib import Path
import re
import shutil
import socket

import pytest

from test_private_message_schema import run_local


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "upgrade_v9_code_free_commands.sql"
TABLE = "delegation_command_contexts"
OWNER = "00000000-0000-0000-0000-000000000001"
OTHER_OWNER = "00000000-0000-0000-0000-000000000002"
COLLEAGUE = "10000000-0000-0000-0000-000000000001"
TASK = "20000000-0000-0000-0000-000000000001"
CONTEXT = "30000000-0000-0000-0000-000000000001"


def test_migration_exists():
    assert MIGRATION.is_file(), "Missing code-free command migration"


@pytest.fixture(scope="module")
def sql():
    assert MIGRATION.is_file(), "Missing code-free command migration"
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).lower()


def test_migration_changes_only_nullable_code_and_new_context_schema(sql):
    assert sql.strip().startswith("begin;")
    assert sql.strip().endswith("commit;")
    assert "alter table public.delegated_tasks alter column approval_code drop not null;" in sql
    assert re.findall(r"create table(?: if not exists)? public\.(\w+)", sql) == [TABLE]
    assert not re.search(r"\b(insert into|delete from|truncate|drop table|drop column|drop constraint)\b", sql)
    assert not re.search(r"\bupdate public\.", sql)
    assert "approval_status =" not in sql
    assert "delivery_status =" not in sql


def test_context_contract_and_reused_candidate_validator(sql):
    for fragment in (
        "id uuid primary key default gen_random_uuid()",
        "owner_user_id uuid not null references public.users(id) on delete cascade",
        "actor_userid text not null",
        "actor_userid = lower(actor_userid)",
        "length(actor_userid) between 1 and 64",
        "operation text not null",
        "'approve', 'cancel', 'modify', 'reply'",
        "candidates jsonb not null default '[]'::jsonb",
        "public.private_message_candidates_valid(candidates)",
        "parameters jsonb not null default '{}'::jsonb",
        "jsonb_typeof(parameters) = 'object'",
        "expires_at timestamptz not null",
        "version int not null default 0 check (version >= 0)",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz not null default now()",
        "unique (owner_user_id, actor_userid)",
        "unique (owner_user_id, id)",
        "new.id is distinct from old.id",
        "new.owner_user_id is distinct from old.owner_user_id",
        "new.actor_userid is distinct from old.actor_userid",
        "create trigger delegation_context_identity before update on public.delegation_command_contexts",
        "idx_delegation_command_contexts_expiry",
    ):
        assert fragment in sql, fragment
    assert "create or replace function public.private_message_candidates_valid" not in sql


def test_context_is_server_only(sql):
    assert f"alter table public.{TABLE} enable row level security;" in sql
    assert f"revoke all on public.{TABLE} from public, anon, authenticated;" in sql
    assert f"grant select, insert, update, delete on public.{TABLE} to service_role;" in sql
    assert "create policy" not in sql
    assert "security definer" not in sql
    assert not re.search(r"grant .* to (?:public|anon|authenticated)\b", sql)


@pytest.fixture(scope="module")
def database(tmp_path_factory, sql):
    """Bootstrap fresh local storage only; never use project DB configuration."""
    binary = shutil.which("initdb")
    if not binary:
        installs = sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin/initdb.exe"))
        binary = str(installs[-1]) if installs else None
    if not binary:
        pytest.skip("Local PostgreSQL unavailable: v7/v8/v9 live DDL not validated")
    bindir = Path(binary).parent
    suffix = ".exe" if Path(binary).suffix == ".exe" else ""
    base = tmp_path_factory.mktemp("code-free-postgres")
    data = base / "data"
    initialized = run_local([
        binary, "-D", data, "-U", "schema_test", "-A", "trust",
        "--encoding=UTF8", "--no-locale",
    ])
    if initialized.returncode:
        pytest.skip("Disposable PostgreSQL unavailable: " + initialized.stderr[-800:])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    ctl = bindir / ("pg_ctl" + suffix)
    try:
        started = run_local([
            ctl, "-D", data, "-l", base / "server.log", "-w", "start",
            "-o", f"-h 127.0.0.1 -p {port} -c fsync=off",
        ], capture=False)
        if started.returncode:
            pytest.skip("Disposable PostgreSQL did not start; see " + str(base / "server.log"))

        def execute(statement, ok=True):
            result = run_local([
                bindir / ("psql" + suffix), "-X", "-v", "ON_ERROR_STOP=1", "-At",
                "-h", "127.0.0.1", "-p", port, "-U", "schema_test", "-d", "postgres",
            ], input=statement)
            if ok:
                assert result.returncode == 0, result.stderr
            return result

        execute("""
            create role anon;
            create role authenticated;
            create role service_role bypassrls;
            create schema auth;
            create function auth.uid() returns uuid language sql stable as
                $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
            create table public.users (id uuid primary key);
        """)
        execute((ROOT / "supabase" / "upgrade_v7_delegation.sql").read_text(encoding="utf-8"))
        execute(f"""
            insert into public.users values ('{OWNER}'), ('{OTHER_OWNER}');
            insert into public.colleagues (id, owner_user_id, name, wecom_userid)
            values ('{COLLEAGUE}', '{OWNER}', 'Synthetic colleague', 'SYNTHETIC_USER');
            insert into public.delegated_tasks
                (id, owner_user_id, colleague_id, content, scheduled_at, approval_code,
                 approval_status, delivery_status, version)
            values ('{TASK}', '{OWNER}', '{COLLEAGUE}', 'Synthetic historical task',
                    now() - interval '1 hour', '1234', 'pending_approval', 'not_sent', 3),
                   ('20000000-0000-0000-0000-000000000002', '{OWNER}', '{COLLEAGUE}',
                    'Synthetic failed historical task', now() - interval '2 hours',
                    '5678', 'approved', 'failed', 4);
        """)
        before = execute("select to_jsonb(t) from public.delegated_tasks t order by id;").stdout
        constraints = execute("""
            select conname, pg_get_constraintdef(oid) from pg_constraint
            where conrelid = 'public.delegated_tasks'::regclass and contype in ('p','u','c','f')
            order by conname;
        """).stdout
        execute((ROOT / "supabase" / "upgrade_v8_private_messages.sql").read_text(encoding="utf-8"))
        execute(MIGRATION.read_text(encoding="utf-8"))
        execute(f"""
            insert into public.delegation_command_contexts
                (id, owner_user_id, actor_userid, operation, candidates, expires_at)
            values ('{CONTEXT}', '{OWNER}', 'synthetic_actor', 'approve',
                    '[{{"id":"{TASK}","version":3}}]'::jsonb, now() + interval '10 minutes');
        """)
        yield execute, before, constraints
    finally:
        if (data / "postmaster.pid").exists():
            stopped = run_local([ctl, "-D", data, "-m", "immediate", "-w", "stop"], capture=False)
            assert stopped.returncode == 0, "Disposable PostgreSQL did not stop"


@pytest.fixture
def execute(database):
    return database[0]


def assert_rejected(execute, statement, code):
    result = execute("\\set VERBOSITY verbose\n begin;\n" + statement + "\nrollback;", ok=False)
    assert result.returncode != 0, "Invalid command context data was accepted"
    assert code in result.stderr, result.stderr


def context_insert(actor="'another_actor'", owner=OWNER, candidates="'[]'::jsonb",
                   parameters="'{}'::jsonb", operation="'approve'"):
    return f"""
        insert into public.delegation_command_contexts
            (owner_user_id, actor_userid, operation, candidates, parameters, expires_at)
        values ('{owner}', {actor}, {operation}, {candidates}, {parameters},
                now() + interval '10 minutes');
    """


def test_live_migration_preserves_historical_tasks_and_constraints(database):
    execute, before, constraints = database
    assert execute("select to_jsonb(t) from public.delegated_tasks t order by id;").stdout == before
    assert execute("""
        select conname, pg_get_constraintdef(oid) from pg_constraint
        where conrelid = 'public.delegated_tasks'::regclass and contype in ('p','u','c','f')
        order by conname;
    """).stdout == constraints
    assert execute("""
        select is_nullable from information_schema.columns
        where table_schema = 'public' and table_name = 'delegated_tasks' and column_name = 'approval_code';
    """).stdout.strip() == "YES"


def test_live_multiple_null_approval_codes_keep_formal_approval(execute):
    result = execute(f"""
        begin;
        insert into public.delegated_tasks
            (owner_user_id, colleague_id, content, scheduled_at, approval_code, approval_status)
        values ('{OWNER}', '{COLLEAGUE}', 'Synthetic null code one', now(), null, 'pending_approval'),
               ('{OWNER}', '{COLLEAGUE}', 'Synthetic null code two', now(), null, 'pending_approval');
        select count(*) from public.delegated_tasks
        where approval_code is null and approval_status = 'pending_approval'
            and delivery_status = 'not_sent' and approved_at is null;
        rollback;
    """)
    assert "2" in result.stdout.splitlines()


@pytest.mark.parametrize("code,error", [("'bad-code'", "23514"), ("'1234'", "23505")])
def test_live_historical_code_check_and_unique_constraint_remain(execute, code, error):
    assert_rejected(execute, f"""
        insert into public.delegated_tasks
            (owner_user_id, colleague_id, content, scheduled_at, approval_code)
        values ('{OWNER}', '{COLLEAGUE}', 'Synthetic invalid code', now(), {code});
    """, error)


@pytest.mark.parametrize("actor", ["''", "'MixedCase'", "' actor'", "'actor '", "'   '", "repeat('x', 65)", "null"])
def test_live_actor_requires_normalized_lowercase_1_to_64(execute, actor):
    assert_rejected(execute, context_insert(actor=actor), "23502" if actor == "null" else "23514")


@pytest.mark.parametrize("actor", ["'x'", "repeat('x', 64)"])
def test_live_actor_length_boundaries_are_valid(execute, actor):
    execute("begin;" + context_insert(actor=actor) + "rollback;")


def test_live_context_uniqueness_is_owner_and_actor_scoped(execute):
    statement = context_insert(actor="'synthetic_actor'")
    assert_rejected(execute, statement, "23505")
    execute("begin;" + context_insert(actor="'synthetic_actor'", owner=OTHER_OWNER)
            + context_insert(actor="'other_actor'") + "rollback;")


def test_live_context_owner_requires_existing_user(execute):
    assert_rejected(execute, context_insert(owner="00000000-0000-0000-0000-000000000099"), "23503")


@pytest.mark.parametrize("change", [
    "id = '30000000-0000-0000-0000-000000000099'",
    f"owner_user_id = '{OTHER_OWNER}'",
    "actor_userid = 'rebound_actor'",
])
def test_live_context_identity_cannot_be_rebound(execute, change):
    assert_rejected(execute, f"""
        update public.delegation_command_contexts set {change}
        where owner_user_id = '{OWNER}' and actor_userid = 'synthetic_actor' and id = '{CONTEXT}';
    """, "23514")


@pytest.mark.parametrize("candidate", [
    '[{"id":"invalid","version":0}]',
    f'[{{"id":"{TASK}","version":0,"content":"private snapshot"}}]',
    f'[{{"id":"{TASK}","version":0,"name":"Synthetic"}}]',
    f'[{{"id":"{TASK}","version":-1}}]',
    f'[{{"id":"{TASK}","version":"0"}}]',
    f'[{{"id":"{TASK}","version":0.5}}]',
    f'[{{"id":"{TASK}","version":2147483648}}]',
    f'[{{"id":"{TASK}"}}]',
    f'[{{"id":"{TASK}","version":null}}]',
    '[{"id":null,"version":0}]', "{}", "null",
])
def test_live_context_candidates_are_only_uuid_and_integer_version(execute, candidate):
    assert_rejected(execute, context_insert(candidates=f"'{candidate}'::jsonb"), "23514")


@pytest.mark.parametrize("operation", ["'send'", "'approval_code'", "''"])
def test_live_context_operations_are_the_four_approved_actions(execute, operation):
    assert_rejected(execute, context_insert(operation=operation), "23514")


@pytest.mark.parametrize("value", ["'[]'::jsonb", "'null'::jsonb", "'1'::jsonb"])
def test_live_context_parameters_must_be_an_object(execute, value):
    assert_rejected(execute, context_insert(parameters=value), "23514")


def test_live_context_version_must_be_nonnegative(execute):
    assert_rejected(execute, f"""
        update public.delegation_command_contexts set version = -1 where id = '{CONTEXT}';
    """, "23514")


def test_live_service_role_can_update_runtime_context_without_rebinding(execute):
    result = execute(f"""
        begin;
        set local role service_role;
        update public.delegation_command_contexts
        set operation = 'modify', candidates = '[{{"id":"{TASK}","version":3}}]'::jsonb,
            parameters = '{{"content":"temporary replacement"}}'::jsonb,
            expires_at = now() + interval '10 minutes', version = version + 1, updated_at = now()
        where owner_user_id = '{OWNER}' and actor_userid = 'synthetic_actor' and id = '{CONTEXT}';
        select count(*) from public.delegation_command_contexts
        where id = '{CONTEXT}' and operation = 'modify' and version = 1;
        rollback;
    """)
    assert "1" in result.stdout.splitlines()
    for operation in ("approve", "cancel", "modify", "reply"):
        execute("begin; set local role service_role;"
                + context_insert(operation=f"'{operation}'") + "rollback;")


def test_live_context_roles_denied_and_rls_has_no_owner_policy(execute):
    assert execute(f"select relrowsecurity from pg_class where oid = 'public.{TABLE}'::regclass;").stdout.strip() == "t"
    assert execute(f"select count(*) from pg_policies where schemaname = 'public' and tablename = '{TABLE}';").stdout.strip() == "0"
    for role in ("anon", "authenticated", "service_role"):
        for privilege in ("select", "insert", "update", "delete"):
            expected = "t" if role == "service_role" else "f"
            assert execute(f"select has_table_privilege('{role}', 'public.{TABLE}', '{privilege}');").stdout.strip() == expected
    for role in ("anon", "authenticated"):
        assert_rejected(execute, f"""
            set local role {role};
            select set_config('request.jwt.claim.sub', '{OWNER}', true);
            select * from public.{TABLE};
        """, "42501")


def test_live_v9_reapply_keeps_task_and_context_rows_unchanged(database):
    execute, before, _ = database
    contexts = execute("select to_jsonb(c) from public.delegation_command_contexts c order by id;").stdout
    execute(MIGRATION.read_text(encoding="utf-8"))
    assert execute("select to_jsonb(t) from public.delegated_tasks t order by id;").stdout == before
    assert execute("select to_jsonb(c) from public.delegation_command_contexts c order by id;").stdout == contexts
