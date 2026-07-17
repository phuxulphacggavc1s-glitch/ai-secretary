from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wecom_inbound_migration_has_unique_msg_id_and_rls():
    sql = (ROOT / "supabase" / "upgrade_v6_wecom_reply_loop.sql").read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "create table if not exists public.wecom_inbound_messages" in lowered
    assert "msg_id text not null unique" in lowered
    assert "user_id uuid" in lowered
    assert "enable row level security" in lowered
    assert "idx_wecom_inbound_user_created" in sql
