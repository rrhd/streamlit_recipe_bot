from types import SimpleNamespace
import sys
from pathlib import Path
import os

import pytest

from constants import PathName
from config import AppConfig
import cache_manager
from diskcache import Cache


def test_diskcache_string_none_creates_none_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = Cache(str(None))
    try:
        assert Path(c.directory).resolve() == (tmp_path / "None").resolve()
    finally:
        c.close()


def test_default_cache_dir_uses_enum(monkeypatch):
    monkeypatch.delenv("CACHE_DIR", raising=False)
    cfg = AppConfig()
    assert cfg.cache_dir == Path(PathName.CACHE_DIR)
    cm = cache_manager.CacheManager(str(cfg.cache_dir))
    try:
        assert Path(cm._cache.directory).name == PathName.CACHE_DIR
    finally:
        cm.close()
