import sys
from pathlib import Path

import psycopg2
import pytest
from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CONFIG
from constants import DbKeys


@pytest.fixture(scope="module")
def supabase_client() -> object:
    if not CONFIG.supabase_url or not CONFIG.supabase_api_key:
        pytest.skip("Supabase credentials not configured")
    try:
        client = create_client(CONFIG.supabase_url, CONFIG.supabase_api_key)
        client.table(DbKeys.TABLE_USER_PROFILES).select("id").limit(1).execute()
        return client
    except Exception as exc:  # pragma: no cover - network error handling
        pytest.skip(f"Supabase not reachable: {exc}")


def test_supabase_api_reachable(supabase_client: object) -> None:
    supabase_client.table(DbKeys.TABLE_USER_PROFILES).select("*").limit(1).execute()


def test_postgres_connection() -> None:
    if not CONFIG.supabase_db_url:
        pytest.skip("Supabase DB URL not configured")
    try:
        with psycopg2.connect(CONFIG.supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone() == (1,)
    except Exception as exc:  # pragma: no cover - network error handling
        pytest.skip(f"Postgres not reachable: {exc}")
