from functools import lru_cache

from supabase import Client, create_client

from config import SUPABASE_SERVICE_KEY, SUPABASE_URL


def is_supabase_configured() -> bool:
    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
        and "xxxx.supabase.co" not in SUPABASE_URL
        and not SUPABASE_SERVICE_KEY.startswith("your-")
    )


@lru_cache
def get_supabase() -> Client:
    if not is_supabase_configured():
        raise RuntimeError("Valid SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


class SupabaseProxy:
    def __getattr__(self, name):
        return getattr(get_supabase(), name)


supabase = SupabaseProxy()
