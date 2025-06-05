import logging
import sqlite3
from pathlib import Path

import psycopg2
from pydantic import BaseModel, Field
from supabase import Client, create_client

from config import CONFIG
from constants import DbKeys


class MigrationConfig(BaseModel):
    local_db: Path = Field(default_factory=lambda: Path(CONFIG.full_profile_db_path))
    supabase_url: str = Field(default_factory=lambda: CONFIG.supabase_url or "")
    supabase_key: str = Field(default_factory=lambda: CONFIG.supabase_api_key or "")
    supabase_db_url: str = Field(default_factory=lambda: CONFIG.supabase_db_url or "")


def create_table_if_missing(cfg: MigrationConfig) -> None:
    """Create the remote profiles table if it does not exist."""
    if not cfg.supabase_db_url:
        raise ValueError("Supabase DB URL required")

    with psycopg2.connect(cfg.supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(DbKeys.SQL_CREATE_PROFILES_PG)
            conn.commit()


def migrate_profiles(cfg: MigrationConfig, client: Client) -> None:
    """Migrate profiles from local SQLite to Supabase."""
    if not cfg.local_db.exists():
        logging.warning("Local DB %s not found", cfg.local_db)
        return

    with sqlite3.connect(cfg.local_db) as conn:
        rows = conn.execute(
            f"SELECT {DbKeys.COL_USERNAME}, {DbKeys.COL_TIMESTAMP}, {DbKeys.COL_PAYLOAD} FROM {DbKeys.TABLE_USER_PROFILES}"
        ).fetchall()

    batch_size = 500
    for i in range(0, len(rows), batch_size):
        chunk = [
            {
                DbKeys.COL_USERNAME: r[0],
                DbKeys.COL_TIMESTAMP: r[1],
                DbKeys.COL_PAYLOAD: r[2],
            }
            for r in rows[i : i + batch_size]
        ]
        if chunk:
            client.table(DbKeys.TABLE_USER_PROFILES).upsert(chunk).execute()


def main() -> None:
    cfg = MigrationConfig()
    client = create_client(cfg.supabase_url, cfg.supabase_key)
    create_table_if_missing(cfg)
    migrate_profiles(cfg, client)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
