from __future__ import annotations

import logging

import psycopg2
import pytest
from supabase import create_client

from config import CONFIG
from constants import DbKeys, LogMsg


@pytest.fixture(scope="module")
def supabase_client() -> object:
    if not CONFIG.supabase_url or not CONFIG.supabase_api_key:
        pytest.skip("Supabase credentials not configured")
    return create_client(CONFIG.supabase_url, CONFIG.supabase_api_key)

def main() -> None:
    """Check Supabase and Postgres connectivity."""
    logging.basicConfig(level=logging.INFO)
    try:
        client = create_client(CONFIG.supabase_url, CONFIG.supabase_api_key)
        client.table("user_profiles").select("*").limit(1).execute()
        logging.info("Supabase API reachable")
    except Exception as e:  # pragma: no cover - network error handling
        logging.error(LogMsg.PROFILE_DB_CONNECTION_FAILED.value, exc_info=True)
        logging.error("Failed Supabase API check: %s", e)

def test_supabase_api_reachable(supabase_client: object) -> None:
    supabase_client.table(DbKeys.TABLE_USER_PROFILES).select("*").limit(1).execute()


def test_postgres_connection() -> None:
    if not CONFIG.supabase_db_url:
        pytest.skip("Supabase DB URL not configured")
    with psycopg2.connect(CONFIG.supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
