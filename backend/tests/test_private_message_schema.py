from pathlib import Path
import re
import shutil
import socket
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "upgrade_v8_private_messages.sql"
TABLES = tuple("private_message_" + name for name in (
    "participants", "threads", "outbox", "inbound", "contexts"
)) + ("private_messages",)


@pytest.fixture(scope="module")
def sql():
    assert MIGRATION.is_file(), "Missing private-message migration"
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).lower()


def table_body(sql, table):
    match = re.search(
        rf"create table(?: if not exists)? public\.{table}\s*\((.*?)\n\);",
        sql, re.S,
    )
    assert match, f"Missing table: {table}"
    return match.group(1)


def test_migration_exists():
    assert MIGRATION.is_file(), "Missing private-message migration"


def test_transaction_and_exactly_six_private_tables(sql):
    assert sql.strip().startswith("begin;")
    assert sql.strip().endswith("commit;")
    assert set(re.findall(r"create table(?: if not exists)? public\.(\w+)", sql)) == set(TABLES)
    for table in TABLES:
        body = table_body(sql, table)
        assert "id uuid primary key default gen_random_uuid()" in body
        assert "space_id uuid not null references public.users(id)" in body
        assert "unique (space_id, id)" in body
        assert "created_at timestamptz not null default now()" in body
        assert "updated_at timestamptz not null default now()" in body


def test_service_field_contract(sql):
    expected = {
        "private_message_participants": "wecom_userid name aliases active",
        "private_message_threads": "participant_a participant_b",
        "private_messages": "thread_id sender_id recipient_id content delivery_mode scheduled_at status version confirmed_at sent_at acknowledged_at failure_code",
        "private_message_outbox": "message_id recipient_id kind operation_key status attempts applied error_code",
        "private_message_inbound": "msg_id sender_userid status",
        "private_message_contexts": "actor_id operation candidates parameters expires_at version",
    }
    for table, fields in expected.items():
        body = table_body(sql, table)
        for field in fields.split():
            assert re.search(rf"^\s*{field}\s+", body, re.M), (table, field)
    assert "unique (space_id, wecom_userid)" in sql
    assert "unique (space_id, participant_a, participant_b)" in sql
    assert "unique (space_id, msg_id)" in sql
    assert "unique (space_id, actor_id)" in sql
    assert "operation_key text not null unique" in sql
    assert "check (participant_a < participant_b)" in sql
    assert "check (sender_id <> recipient_id)" in sql
    assert "check (attempts between 0 and 2)" in sql
    assert "applied boolean not null default false" in sql
    assert "version int not null default 0" in sql
    assert "octet_length(content) between 1 and 1200" in sql
    for values in (
        "'immediate', 'scheduled'",
        "'draft', 'scheduled', 'sending', 'sent', 'failed', 'uncertain', 'cancelled', 'expired'",
        "'delivery', 'notice', 'receipt'",
        "'pending', 'sending', 'sent', 'failed', 'uncertain', 'cancelled'",
        "'processing', 'processed', 'failed'",
    ):
        assert values in sql


def test_all_internal_foreign_keys_include_space(sql):
    for columns, target, target_columns in re.findall(
        r"foreign key\s*\(([^)]+)\)\s*references public\.(\w+)\(([^)]+)\)", sql
    ):
        assert columns.strip().startswith("space_id,"), (columns, target)
        assert target_columns.strip().startswith("space_id,"), target_columns
    assert "foreign key (space_id, participant_a)" in sql
    assert "foreign key (space_id, participant_b)" in sql
    for field in ("thread_id", "sender_id", "recipient_id", "message_id", "actor_id"):
        assert f"foreign key (space_id, {field})" in sql


def test_private_tables_are_not_client_readable(sql):
    for table in TABLES:
        assert f"alter table public.{table} enable row level security;" in sql
        assert f"revoke all on public.{table} from public, anon, authenticated;" in sql
        assert f"grant select, insert, update, delete on public.{table} to service_role;" in sql
    assert "create policy" not in sql
    assert "security definer" not in sql
    assert not re.search(r"grant .* to (?:anon|authenticated|public)\b", sql)


def test_no_seed_short_code_or_legacy_content_storage(sql):
    for forbidden in ("approval_code", "short_code", "message_code", "wecom_inbound_messages"):
        assert forbidden not in sql
    assert not re.search(r"\binsert into\b", sql)
    inbound = table_body(sql, "private_message_inbound")
    assert not re.search(r"\b(content|body|payload|parameters|candidates)\b", inbound)
    assert "private_message_candidates_valid(candidates)" in sql
    assert "jsonb_typeof(parameters) = 'object'" in sql
    assert "idx_private_messages_due" in sql
    assert "idx_private_messages_thread" in sql
    assert "idx_private_message_outbox_pending" in sql


def run_local(args, capture=True, **kwargs):
    output = {"capture_output": True} if capture else {
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
    }
    return subprocess.run(
        [str(arg) for arg in args], text=True, encoding="utf-8", errors="replace",
        timeout=45, **output,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs,
    )


@pytest.fixture(scope="module")
def pg(tmp_path_factory, sql):
    """Never read DATABASE_URL or reuse a running/project database."""
    binary = shutil.which("initdb")
    if not binary:
        installs = sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin/initdb.exe"))
        binary = str(installs[-1]) if installs else None
    if not binary:
        pytest.skip("Local PostgreSQL unavailable: live DDL not validated")
    bindir = Path(binary).parent
    suffix = ".exe" if Path(binary).suffix == ".exe" else ""
    base = tmp_path_factory.mktemp("private-message-postgres")
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
        # Windows postgres inherits pipe handles; pg_ctl must not use PIPE.
        started = run_local([
            ctl, "-D", data, "-l", base / "server.log", "-w", "start",
            "-o", f"-h 127.0.0.1 -p {port} -c fsync=off",
        ], capture=False)
        if started.returncode:
            pytest.skip("Disposable PostgreSQL did not start; see " + str(base / "server.log"))

        def execute(statement, ok=True):
            result = run_local([
                bindir / ("psql" + suffix), "-X", "-v", "ON_ERROR_STOP=1",
                "-h", "127.0.0.1", "-p", port, "-U", "schema_test", "-d", "postgres",
                "-At",
            ], input=statement)
            if ok:
                assert result.returncode == 0, result.stderr
            return result

        execute("""
            create role anon;
            create role authenticated;
            create role service_role bypassrls;
            create table public.users (id uuid primary key);
        """)
        execute(MIGRATION.read_text(encoding="utf-8"))
        execute("""
            insert into public.users values
                ('00000000-0000-0000-0000-000000000001'),
                ('00000000-0000-0000-0000-000000000002');
            insert into public.private_message_participants (id, space_id, wecom_userid, name) values
                ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'TEST_A', 'Synthetic A'),
                ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'TEST_B', 'Synthetic B'),
                ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'TEST_C', 'Synthetic C'),
                ('10000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000002', 'TEST_X', 'Synthetic X');
            insert into public.private_message_threads (id, space_id, participant_a, participant_b) values
                ('20000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
                 '10000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002');
            insert into public.private_messages (id, space_id, thread_id, sender_id, recipient_id, content, delivery_mode) values
                ('30000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
                 '20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001',
                 '10000000-0000-0000-0000-000000000002', 'synthetic body', 'immediate'),
                ('30000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001',
                 '20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002',
                 '10000000-0000-0000-0000-000000000001', 'synthetic reply', 'immediate');
        """)
        yield execute
    finally:
        if (data / "postmaster.pid").exists():
            stopped = run_local([ctl, "-D", data, "-m", "immediate", "-w", "stop"], capture=False)
            assert stopped.returncode == 0, "Disposable PostgreSQL did not stop"


SPACE = "00000000-0000-0000-0000-000000000001"
A = "10000000-0000-0000-0000-000000000001"
B = "10000000-0000-0000-0000-000000000002"
C = "10000000-0000-0000-0000-000000000003"
X = "10000000-0000-0000-0000-000000000004"
THREAD = "20000000-0000-0000-0000-000000000001"
MESSAGE = "30000000-0000-0000-0000-000000000001"


def assert_rejected(pg, statement, code):
    result = pg("\\set VERBOSITY verbose\n begin;\n" + statement + "\nrollback;", ok=False)
    assert result.returncode != 0, "Invalid private data was accepted"
    assert code in result.stderr, result.stderr


@pytest.mark.parametrize("left,right,code", [(A, A, "23514"), (B, A, "23514"), (A, X, "23503")])
def test_live_threads_reject_self_reversed_and_cross_space(pg, left, right, code):
    assert_rejected(pg, f"""
        insert into public.private_message_threads (space_id, participant_a, participant_b)
        values ('{SPACE}', '{left}', '{right}');
    """, code)


@pytest.mark.parametrize("sender,recipient,space,code", [
    (A, A, SPACE, "23514"), (A, C, SPACE, "23514"),
    (C, B, SPACE, "23514"), (A, X, SPACE, "23514"),
    (A, B, "00000000-0000-0000-0000-000000000002", "23514"),
])
def test_live_message_direction_and_space(pg, sender, recipient, space, code):
    assert_rejected(pg, f"""
        insert into public.private_messages
            (space_id, thread_id, sender_id, recipient_id, content, delivery_mode)
        values ('{space}', '{THREAD}', '{sender}', '{recipient}', 'synthetic', 'immediate');
    """, code)


@pytest.mark.parametrize("table,change,code", [
    ("private_message_threads", f"participant_b = '{C}'", "23514"),
    ("private_messages", f"recipient_id = '{C}'", "23514"),
    ("private_messages", f"sender_id = '{B}', recipient_id = '{A}'", "23514"),
    ("private_messages", "content = repeat('x', 1201)", "23514"),
    ("private_messages", "content = repeat(chr(20013), 401)", "23514"),
    ("private_messages", "version = -1", "23514"),
])
def test_live_identity_and_payload_constraints(pg, table, change, code):
    row = THREAD if table.endswith("threads") else MESSAGE
    assert_rejected(pg, f"update public.{table} set {change} where id = '{row}';", code)


@pytest.mark.parametrize("kind,target,valid", [
    ("delivery", B, True), ("notice", A, True), ("receipt", A, True),
    ("delivery", A, False), ("notice", B, False), ("receipt", B, False),
    ("delivery", C, False), ("notice", X, False),
])
def test_live_outbox_target_is_kind_specific(pg, kind, target, valid):
    statement = f"""
        insert into public.private_message_outbox
            (space_id, message_id, recipient_id, kind, operation_key)
        values ('{SPACE}', '{MESSAGE}', '{target}', '{kind}', 'synthetic-operation');
    """
    if valid:
        pg("begin;" + statement + "rollback;")
    else:
        assert_rejected(pg, statement, "23514")


def test_live_outbox_updates_and_unique_operation(pg):
    insert = f"""
        insert into public.private_message_outbox (space_id, message_id, recipient_id, kind, operation_key)
        values ('{SPACE}', '{MESSAGE}', '{B}', 'delivery', 'synthetic-unique');
    """
    assert_rejected(pg, insert + insert, "23505")
    assert_rejected(pg, insert + "update public.private_message_outbox set kind = 'notice';", "23514")
    assert_rejected(pg, insert + "update public.private_message_outbox set attempts = 3;", "23514")
    assert_rejected(pg, insert + "update public.private_message_outbox set space_id = '00000000-0000-0000-0000-000000000002';", "23514")


@pytest.mark.parametrize("candidates,valid", [
    (f'[{{"id":"{MESSAGE}","version":0}}]', True), ("[]", True),
    (f'[{{"id":"{MESSAGE}","version":0,"content":"private"}}]', False),
    (f'[{{"id":"{MESSAGE}","version":-1}}]', False),
    (f'[{{"id":"{MESSAGE}","version":"0"}}]', False),
    (f'[{{"id":"{MESSAGE}","version":0.5}}]', False),
    (f'[{{"id":"{MESSAGE}","version":2147483648}}]', False),
    (f'[{{"id":"{MESSAGE}","version":null}}]', False),
    ('[{"id":null,"version":0}]', False),
    ('[{"id":"invalid","version":0}]', False),
    (f'[{{"id":"{MESSAGE}"}}]', False), ('{}', False), ('null', False),
])
def test_live_context_candidates_only_store_uuid_and_version(pg, candidates, valid):
    statement = f"""
        insert into public.private_message_contexts
            (space_id, actor_id, operation, candidates, parameters, expires_at)
        values ('{SPACE}', '{A}', 'reply', '{candidates}'::jsonb,
                '{{"content":"temporary private reply"}}'::jsonb, now() + interval '10 minutes');
    """
    if valid:
        pg("begin;" + statement + "rollback;")
    else:
        assert_rejected(pg, statement, "23514")


def test_live_context_actor_and_inbound_dedup(pg):
    assert_rejected(pg, f"""
        insert into public.private_message_contexts (space_id, actor_id, operation, expires_at)
        values ('{SPACE}', '{X}', 'view', now());
    """, "23503")
    insert = f"""
        insert into public.private_message_inbound (space_id, msg_id, sender_userid)
        values ('{SPACE}', 'SYNTHETIC_MSG', 'TEST_A');
    """
    assert_rejected(pg, insert + insert, "23505")


def test_live_rls_and_privileges(pg):
    names = ",".join(f"'{table}'" for table in TABLES)
    assert pg(f"select count(*) from pg_class where relname in ({names}) and relrowsecurity;").stdout.strip() == "6"
    assert pg(f"select count(*) from pg_policies where tablename in ({names});").stdout.strip() == "0"
    for table in TABLES:
        for role in ("anon", "authenticated"):
            for privilege in ("select", "insert", "update", "delete"):
                assert pg(f"select has_table_privilege('{role}', 'public.{table}', '{privilege}');").stdout.strip() == "f"
        for privilege in ("select", "insert", "update", "delete"):
            assert pg(f"select has_table_privilege('service_role', 'public.{table}', '{privilege}');").stdout.strip() == "t"
        assert_rejected(pg, f"set local role authenticated; select * from public.{table};", "42501")


def test_live_runtime_parameters_must_be_an_object(pg):
    for value in ("[]", "null", '"snapshot"'):
        assert_rejected(pg, f"""
            insert into public.private_message_contexts
                (space_id, actor_id, operation, parameters, expires_at)
            values ('{SPACE}', '{A}', 'edit', '{value}'::jsonb, now());
        """, "23514")


def test_live_service_role_can_use_private_action_parameters(pg):
    pg(f"""
        begin;
        set local role service_role;
        insert into public.private_message_contexts
            (space_id, actor_id, operation, candidates, parameters, expires_at)
        values ('{SPACE}', '{A}', 'edit', '[{{"id":"{MESSAGE}","version":0}}]'::jsonb,
                '{{"content":"temporary edit","scheduled_at":null}}'::jsonb,
                now() + interval '10 minutes');
        update public.private_messages set content = 'edited synthetic body', version = 1
            where space_id = '{SPACE}' and id = '{MESSAGE}';
        insert into public.private_message_outbox
            (space_id, message_id, recipient_id, kind, operation_key)
        values ('{SPACE}', '{MESSAGE}', '{A}', 'notice', 'synthetic-service-operation');
        rollback;
    """)


def test_live_reapply_preserves_data_and_never_enables_participants(pg):
    pg(MIGRATION.read_text(encoding="utf-8"))
    assert pg("select count(*) from public.private_message_participants;").stdout.strip() == "4"
    assert pg("select count(*) from public.private_message_participants where active;").stdout.strip() == "0"
    assert pg("select count(*) from public.private_messages;").stdout.strip() == "2"


@pytest.mark.parametrize("participant", [A, C])
@pytest.mark.parametrize("change", [
    "id = '10000000-0000-0000-0000-000000000099'",
    "space_id = '00000000-0000-0000-0000-000000000002'",
    "wecom_userid = 'NEW_SYNTHETIC_ACCOUNT'",
])
def test_live_participant_identity_cannot_be_rebound(pg, participant, change):
    # C has no children: immutability must not depend on an existing foreign key.
    assert_rejected(pg, f"""
        update public.private_message_participants set {change}
        where space_id = '{SPACE}' and id = '{participant}';
    """, "23514")


def test_live_participant_userid_casing_is_also_immutable(pg):
    assert_rejected(pg, f"""
        update public.private_message_participants set wecom_userid = 'test_a'
        where space_id = '{SPACE}' and id = '{A}';
    """, "23514")


def test_live_participant_profile_fields_remain_editable(pg):
    result = pg(f"""
        begin;
        set local role service_role;
        update public.private_message_participants
        set name = 'Renamed synthetic A', aliases = array['Synthetic alias'], active = true
        where space_id = '{SPACE}' and id = '{A}';
        select count(*) from public.private_message_participants
        where id = '{A}' and space_id = '{SPACE}' and wecom_userid = 'TEST_A'
            and name = 'Renamed synthetic A' and aliases = array['Synthetic alias'] and active;
        rollback;
    """)
    assert "1" in result.stdout.splitlines()


def test_live_participant_userid_unique_ignores_case_within_space(pg):
    assert_rejected(pg, f"""
        insert into public.private_message_participants (space_id, wecom_userid, name)
        values ('{SPACE}', 'User', 'Synthetic first account'),
               ('{SPACE}', 'user', 'Synthetic duplicate account');
    """, "23505")


def test_live_participant_userid_case_uniqueness_is_space_scoped(pg):
    pg(f"""
        begin;
        insert into public.private_message_participants (space_id, wecom_userid, name)
        values ('{SPACE}', 'User', 'Synthetic first space'),
               ('00000000-0000-0000-0000-000000000002', 'user', 'Synthetic second space');
        rollback;
    """)


def test_participant_identity_guard_and_case_unique_index_are_declared(sql):
    assert "tg_table_name = 'private_message_participants'" in sql
    assert "new.wecom_userid is distinct from old.wecom_userid" in sql
    assert "create trigger private_participant_identity before update on public.private_message_participants" in sql
    assert re.search(
        r"create unique index if not exists idx_private_message_participants_userid_ci\s+"
        r"on public\.private_message_participants\(space_id, lower\(wecom_userid\)\);", sql,
    )
    assert "unique (space_id, wecom_userid)" in table_body(sql, "private_message_participants")
