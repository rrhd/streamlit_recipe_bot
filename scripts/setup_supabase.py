import logging
import sqlite3
from pathlib import Path

import psycopg2
from postgrest import APIError
from pydantic import BaseModel, Field
from supabase import Client, create_client

from config import CONFIG
from constants import DbKeys
BATCH_SIZE = 500

class MigrationConfig(BaseModel):
    local_db: Path = Field(default_factory=lambda: Path(CONFIG.full_profile_db_path).resolve().absolute())
    supabase_url: str = Field(default_factory=lambda: CONFIG.supabase_url or "")
    supabase_key: str = Field(default_factory=lambda: CONFIG.supabase_api_key or "")
    supabase_db_url: str = Field(default_factory=lambda: CONFIG.supabase_db_url or "")


def create_table_if_missing(cfg: MigrationConfig) -> None:
    """Ensure remote table exists and only the (username,timestamp) pair is UNIQUE."""
    if not cfg.supabase_db_url:
        raise ValueError("Supabase DB URL required")

    with psycopg2.connect(cfg.supabase_db_url) as conn, conn.cursor() as cur:
        # 1. Create table if absent
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {DbKeys.TABLE_USER_PROFILES} (
                id SERIAL PRIMARY KEY,
                {DbKeys.COL_USERNAME} TEXT NOT NULL,
                {DbKeys.COL_TIMESTAMP} TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                {DbKeys.COL_PAYLOAD} JSONB
            );
        """)

        # 2. Remove the old single-column unique that blocks multiple rows per user
        cur.execute(f"""
            ALTER TABLE {DbKeys.TABLE_USER_PROFILES}
            DROP CONSTRAINT IF EXISTS {DbKeys.TABLE_USER_PROFILES}_{DbKeys.COL_USERNAME}_key;
        """)

        # 3. (Re)create the composite unique constraint required for ON CONFLICT
        cur.execute(f"""
            ALTER TABLE {DbKeys.TABLE_USER_PROFILES}
            DROP CONSTRAINT IF EXISTS user_profiles_username_timestamp_uniq;
        """)
        cur.execute(f"""
            ALTER TABLE {DbKeys.TABLE_USER_PROFILES}
            ADD CONSTRAINT user_profiles_username_timestamp_uniq
            UNIQUE ({DbKeys.COL_USERNAME}, {DbKeys.COL_TIMESTAMP});
        """)

        conn.commit()



def migrate_profiles(cfg: MigrationConfig, client: Client) -> None:
    """Bulk-upsert profiles from local SQLite to Supabase in batches."""
    if not cfg.local_db.exists():
        logging.warning("Local DB %s not found", cfg.local_db)
        return

    with sqlite3.connect(cfg.local_db) as conn:
        rows = conn.execute(
            f"SELECT {DbKeys.COL_USERNAME}, {DbKeys.COL_TIMESTAMP}, {DbKeys.COL_PAYLOAD} "
            f"FROM {DbKeys.TABLE_USER_PROFILES}"
        ).fetchall()

    # deduplicate on (username, timestamp)
    seen: set[tuple] = set()
    deduped = [r for r in rows if not (r[0], r[1]) in seen and not seen.add((r[0], r[1]))]
    if not deduped:
        logging.info("No profiles to migrate from %s", cfg.local_db)
        return

    # chunked bulk-upsert
    for start in range(0, len(deduped), BATCH_SIZE):
        batch = deduped[start : start + BATCH_SIZE]
        payload = [
            {
                DbKeys.COL_USERNAME: r[0],
                DbKeys.COL_TIMESTAMP: r[1],
                DbKeys.COL_PAYLOAD: r[2],
            }
            for r in batch
        ]
        try:
            client.table(DbKeys.TABLE_USER_PROFILES).upsert(
                payload,
                on_conflict=f"{DbKeys.COL_USERNAME},{DbKeys.COL_TIMESTAMP}",
                returning="minimal",
            ).execute()
        except APIError as e:
            # fallback to per-row upsert on failure
            for r in batch:
                try:
                    client.table(DbKeys.TABLE_USER_PROFILES).upsert(
                        {
                            DbKeys.COL_USERNAME: r[0],
                            DbKeys.COL_TIMESTAMP: r[1],
                            DbKeys.COL_PAYLOAD: r[2],
                        },
                        on_conflict=f"{DbKeys.COL_USERNAME},{DbKeys.COL_TIMESTAMP}",
                        returning="minimal",
                    ).execute()
                except APIError as ie:
                    logging.error("Failed record %s: %s", r[0], ie)
        else:
            logging.info("Upserted rows %s–%s", start, start + len(batch) - 1)

    logging.info("Completed migration of %s profiles", len(deduped))
def main() -> None:
    cfg = MigrationConfig()
    client = create_client(cfg.supabase_url, cfg.supabase_key)
    create_table_if_missing(cfg)
    migrate_profiles(cfg, client)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
