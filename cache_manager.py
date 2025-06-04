"""Handles caching of query results and detects DB updates."""

import logging
from datetime import datetime
from typing import Any

import diskcache
from models import QueryRequest, SimpleSearchRequest
from query_top_k import get_db_connection as get_recipe_db_connection
from constants import PathName, DefaultDate


def fetch_db_last_updated() -> datetime:
    conn = get_recipe_db_connection()

    cursor = conn.execute("SELECT MAX(processed_at) FROM recipe_schema")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return datetime.fromisoformat(DefaultDate.DB_MISSING)

    return datetime.fromisoformat(row[0])


class CacheManager:
    """Manages a persistent disk cache and invalidates on DB updates."""

    def __init__(self, cache_dir: str = PathName.CACHE_DIR) -> None:
        """
        Initializes the disk cache.

        Args:
            cache_dir: Directory where diskcache stores data.
        """
        self._cache = diskcache.Cache(cache_dir)
        self._last_db_update: datetime | None = None
        self.check_db_update_and_invalidate()

    def check_db_update_and_invalidate(self) -> None:
        """
        Checks if the DB has been updated and invalidates the cache if so.

        Returns:
            None
        """
        current_db_time = fetch_db_last_updated()

        if self._last_db_update is None:
            self._last_db_update = current_db_time
            return

        if current_db_time != self._last_db_update:
            logging.info("DB update detected: clearing disk cache.")
            self._cache.clear()
            self._last_db_update = current_db_time

    def build_query_key(self, req: QueryRequest) -> str:
        """
        Builds a cache key for a QueryRequest.

        Args:
            req: A QueryRequest object.

        Returns:
            A string representing the cache key.
        """

        return str(req.model_dump())

    def build_simple_search_key(self, req: SimpleSearchRequest) -> str:
        """
        Builds a cache key for a SimpleSearchRequest.

        Args:
            req: A SimpleSearchRequest object.

        Returns:
            A string representing the cache key.
        """
        return f"simple_search::{req.query.strip().lower()}"

    def get(self, key: str) -> Any | None:
        """
        Retrieves a cached value if present.

        Args:
            key: The cache key.

        Returns:
            The cached value if found, otherwise None.
        """
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """
        Stores a value in the cache.

        Args:
            key: The cache key.
            value: The value to store.

        Returns:
            None
        """
        self._cache[key] = value

    def close(self) -> None:
        """
        Closes the disk cache cleanly.

        Returns:
            None
        """
        self._cache.close()
