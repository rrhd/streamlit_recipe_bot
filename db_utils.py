import base64
import json
import logging
import os
from datetime import datetime
from typing import Any

import sqlite3

import psycopg2
from supabase import Client, create_client

import streamlit as st

from constants import FormatStrings, DbKeys, ProfileDataKeys, LogMsg
from log_utils import (
    DbPayload,
    ProfilePayload,
    ErrorPayload,
    FuncPayload,
    log_with_payload,
)
from query_top_k import get_db_connection as get_recipe_db_connection
from config import CONFIG
from ui_helpers import UiText


@st.cache_resource
def get_profile_db_connection() -> Client | None:
    """Returns a Supabase client for the profiles table."""
    if not CONFIG.supabase_url or not CONFIG.supabase_api_key:
        st.error(UiText.ERROR_PROFILE_DB_CONNECT_FAILED.format(error="Missing Supabase config"))
        return None

    try:
        return create_client(CONFIG.supabase_url, CONFIG.supabase_api_key)
    except Exception as e:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_CONNECTION_FAILED,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_CONNECT_FAILED.format(error=e))
        return None


def init_profile_db() -> None:
    """Creates the user_profiles table on Supabase if it doesn't exist."""
    if not CONFIG.supabase_db_url:
        st.error(UiText.ERROR_PROFILE_DB_INIT.format(error="No Supabase DB URL"))
        return

    try:
        with psycopg2.connect(CONFIG.supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(DbKeys.SQL_CREATE_PROFILES_PG)
                conn.commit()
        log_with_payload(logging.INFO, LogMsg.PROFILE_DB_INIT_SUCCESS)
    except Exception as e:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_INIT_FAIL,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_INIT.format(error=e))


def save_profile(username: str, options_base64: str) -> str:
    """Saves a profile to the database. Returns the timestamp."""
    timestamp = datetime.now().isoformat(timespec=FormatStrings.TIMESTAMP_ISO_SECONDS)
    payload = ProfilePayload(username=username, timestamp=timestamp)
    log_with_payload(
        logging.INFO,
        LogMsg.PROFILE_DB_SAVE_ATTEMPT,
        payload=payload,
        username=username,
        timestamp=timestamp,
    )

    client = get_profile_db_connection()
    if not client:
        log_with_payload(
            logging.ERROR, LogMsg.PROFILE_DB_CONN_UNAVAILABLE_SAVE, payload=payload
        )
        raise ConnectionError(UiText.ERROR_PROFILE_DB_CONN_MISSING_SAVE)

    try:
        client.table(DbKeys.TABLE_USER_PROFILES).insert(
            {
                DbKeys.COL_USERNAME: username,
                DbKeys.COL_TIMESTAMP: timestamp,
                DbKeys.COL_PAYLOAD: options_base64,
            }
        ).execute()
        log_with_payload(
            logging.INFO,
            LogMsg.PROFILE_DB_SAVE_SUCCESS,
            payload=payload,
            username=username,
        )
        return timestamp
    except Exception as e:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_SAVE_FAIL,
            payload=err_payload,
            profile_payload=payload,
            username=username,
            error=str(e),
            exc_info=True,
        )
        raise


def load_profile(username: str) -> dict[str, Any] | None:
    """Loads the most recent profile for a user."""
    payload = ProfilePayload(username=username)
    log_with_payload(
        logging.INFO, LogMsg.PROFILE_DB_LOAD_ATTEMPT, payload=payload, username=username
    )

    client = get_profile_db_connection()
    if not client:
        log_with_payload(
            logging.ERROR, LogMsg.PROFILE_DB_CONN_UNAVAILABLE_LOAD, payload=payload
        )
        st.error(UiText.ERROR_PROFILE_DB_CONN_MISSING_LOAD)
        return None

    try:
        resp = (
            client.table(DbKeys.TABLE_USER_PROFILES)
            .select("*")
            .eq(DbKeys.COL_USERNAME, username)
            .order(DbKeys.COL_TIMESTAMP, desc=True)
            .limit(1)
            .execute()
        )
        row = resp.data[0] if resp.data else None

        if not row:
            log_with_payload(
                logging.WARNING,
                LogMsg.PROFILE_DB_LOAD_NOT_FOUND,
                payload=payload,
                username=username,
            )
            return None

        payload_b64 = row.get(DbKeys.COL_PAYLOAD)
        actual_ts = row.get(DbKeys.COL_TIMESTAMP)
        payload.timestamp = actual_ts
        try:
            decoded_bytes = base64.b64decode(payload_b64)
            decoded_str = decoded_bytes.decode(FormatStrings.ENCODING_UTF8)
            options_dict = json.loads(decoded_str)
            log_with_payload(
                logging.INFO,
                LogMsg.PROFILE_DB_LOAD_SUCCESS,
                payload=payload,
                username=username,
                timestamp=actual_ts,
            )

            return {
                ProfileDataKeys.TIMESTAMP: actual_ts,
                ProfileDataKeys.OPTIONS: options_dict,
            }
        except (
            base64.binascii.Error,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
        ) as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_DB_LOAD_DECODE_FAIL,
                payload=err_payload,
                profile_payload=payload,
                username=username,
                timestamp=actual_ts,
                error=str(e),
                exc_info=True,
            )
            st.error(UiText.ERROR_PROFILE_DECODE.format(username=username))
            return None

    except Exception as e:  # pragma: no cover - network error handling
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_QUERY_FAILED,
            payload=err_payload,
            profile_payload=payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_QUERY_FAILED_LOAD.format(error=e))
        return None


@st.cache_resource(ttl=600)
def fetch_sources_cached(db_last_updated_time_key: str | None) -> list[str] | None:
    """
    Cached function to fetch distinct source domains from the recipe database.
    Uses a stable string representation of update time for cache keying.
    """
    log_with_payload(
        logging.INFO,
        LogMsg.SOURCES_FETCHING,
        db_timestamp=str(db_last_updated_time_key),
    )
    func_payload = FuncPayload(function_name="fetch_sources_cached")

    conn: sqlite3.Connection | None = None
    try:
        conn = get_recipe_db_connection()
        if not conn:
            log_with_payload(
                logging.ERROR,
                LogMsg.RECIPE_DB_CONN_FAIL,
                payload=func_payload,
                function_name=func_payload.function_name,
            )
            st.error(UiText.ERROR_RECIPE_DB_CONNECT_FAILED_SOURCES)
            return []

        rows = conn.execute(DbKeys.SQL_SELECT_SOURCES).fetchall()
        sources = sorted([r[0] for r in rows if r and r[0]])
        log_with_payload(
            logging.INFO,
            LogMsg.SOURCES_FETCHED_COUNT,
            payload=func_payload,
            count=len(sources),
        )
        return sources
    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.RECIPE_DB_QUERY_SOURCES_FAILED,
            payload=err_payload,
            func_payload=func_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_RECIPE_DB_QUERY_FAILED_SOURCES.format(error=e))
        return []
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.SOURCES_FETCH_UNEXPECTED_ERROR,
            payload=err_payload,
            func_payload=func_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_UNEXPECTED_FETCH_SOURCES.format(error=e))
        return []
    finally:
        if conn:
            conn.close()
