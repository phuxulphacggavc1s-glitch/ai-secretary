from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wecom_outreach_upgrade_has_rls_indexes_and_pause_flag():
    sql = (ROOT / "supabase" / "upgrade_v5_wecom_outreach.sql").read_text(
        encoding="utf-8"
    )
    lowered = sql.lower()

    assert "create table if not exists public.secretary_outreach" in lowered
    assert "user_id uuid" in lowered
    assert "task_id uuid" in lowered
    assert "enable row level security" in lowered
    assert "idx_secretary_outreach_user_created" in sql
    assert "followup_paused boolean" in lowered
