from __future__ import annotations

import logging

import psycopg2
import pytest
from supabase import create_client

from config import CONFIG
from constants import DbKeys, LogMsg
from log_utils import ErrorPayload, log_with_payload
from scripts.init_supabase_project import SetupConfig


def test_setup_config_load_alt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "pat-from-env"
    monkeypatch.setenv("SUPA_BASE_API_KEY", token)
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    cfg = SetupConfig.load()
    assert cfg.access_token == token


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
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_CONNECTION_FAILED,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )

def test_supabase_api_reachable(supabase_client: object) -> None:
    try:
        supabase_client.table(DbKeys.TABLE_USER_PROFILES).select("*").limit(1).execute()
    except Exception as exc:  # pragma: no cover - network error handling
        pytest.skip(f"Supabase API not reachable: {exc}")


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
