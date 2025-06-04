"""Simple Supabase connectivity check."""
from __future__ import annotations

import logging

import psycopg2
from supabase import create_client

from config import CONFIG
from constants import DbKeys, LogMsg
from log_utils import ErrorPayload, log_with_payload


def main() -> None:
    """Verify that Supabase and Postgres credentials work."""
    logging.basicConfig(level=logging.INFO)
    try:
        client = create_client(CONFIG.supabase_url, CONFIG.supabase_api_key)
        client.table(DbKeys.TABLE_USER_PROFILES).select("*").limit(1).execute()
        logging.info("Supabase API reachable")
    except Exception as exc:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(exc))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_CONNECTION_FAILED,
            payload=err_payload,
            error=str(exc),
            exc_info=True,
        )

    try:
        with psycopg2.connect(CONFIG.supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                logging.info("Postgres connection successful")
    except Exception as exc:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(exc))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_INIT_FAIL,
            payload=err_payload,
            error=str(exc),
            exc_info=True,
        )


if __name__ == "__main__":
    main()
