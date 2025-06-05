"""Prototype Supabase connection using only environment variables."""

from __future__ import annotations

import logging

import psycopg2
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import create_client

from constants import DbKeys, SupabaseEnv, LogMsg
from log_utils import ErrorPayload, log_with_payload


class EnvSupabaseConfig(BaseSettings):
    """Supabase credentials sourced purely from environment variables."""

    supabase_url: str = Field(validation_alias=SupabaseEnv.URL.value)
    supabase_api_key: str = Field(validation_alias=SupabaseEnv.API_KEY.value)
    supabase_db_url: str = Field(validation_alias=SupabaseEnv.DB_URL.value)

    model_config = SettingsConfigDict(extra="ignore")


def main() -> None:
    """Attempt basic Supabase and PostgreSQL operations."""
    logging.basicConfig(level=logging.INFO)
    cfg = EnvSupabaseConfig()

    try:
        client = create_client(cfg.supabase_url, cfg.supabase_api_key)
        client.table(DbKeys.TABLE_USER_PROFILES).select("*").limit(1).execute()
        logging.info("Supabase API reachable via env config")
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
        with psycopg2.connect(cfg.supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                logging.info("Postgres connection successful via env config")
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
