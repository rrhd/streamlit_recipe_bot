from __future__ import annotations

import json
from typing import Any, Iterable

from diskcache import Cache
from functools import lru_cache
try:
    from mistralai import Mistral
except Exception:  # pragma: no cover - fallback
    class Mistral:
        def __init__(self, *_, **__):
            pass
        class chat:
            @staticmethod
            def complete(*_, **__):
                return None
            @staticmethod
            def parse(*_, **__):
                return None
        class embeddings:
            @staticmethod
            def create(*_, **__):
                return None

from config import AppConfig
from constants import ModelName

_cache = Cache("mistral_cache")

@lru_cache(maxsize=1)
def get_client(api_key: str) -> Mistral:
    """Return a cached Mistral client."""
    return Mistral(api_key=api_key)


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _cache_key(prefix: str, payload: Any) -> str:
    try:
        body = json.dumps(_serialize(payload), sort_keys=True)
    except TypeError:
        body = str(payload)
    return f"{prefix}:{body}"


def chat_complete(cfg: AppConfig, *, messages: list, model: ModelName, **kwargs: Any) -> Any:
    """Cached wrapper around Mistral.chat.complete."""
    client = get_client(cfg.api_key)
    key = _cache_key(
        "chat", {"model": model, "messages": [_serialize(m) for m in messages], **kwargs}
    )
    if cached := _cache.get(key):
        return cached
    resp = client.chat.complete(model=model, messages=messages, **kwargs)
    try:
        _cache.set(key, resp)
    except Exception:
        pass
    return resp


def embeddings_create(cfg: AppConfig, *, inputs: Iterable[str], model: ModelName) -> Any:
    """Cached wrapper around Mistral.embeddings.create."""
    client = get_client(cfg.api_key)
    key = _cache_key("embed", {"model": model, "inputs": list(inputs)})
    if cached := _cache.get(key):
        return cached
    resp = client.embeddings.create(model=model, inputs=list(inputs))
    try:
        _cache.set(key, resp)
    except Exception:
        pass
    return resp


def chat_parse(
    cfg: AppConfig,
    *,
    messages: list,
    model: ModelName,
    response_format: type,
    **kwargs: Any,
) -> Any:
    """Cached wrapper around Mistral.chat.parse."""
    client = get_client(cfg.api_key)
    key = _cache_key(
        "parse",
        {
            "model": model,
            "messages": [_serialize(m) for m in messages],
            "schema": response_format.__name__,
            **kwargs,
        },
    )
    if cached := _cache.get(key):
        return cached
    resp = client.chat.parse(
        model=model,
        messages=messages,
        response_format=response_format,
        **kwargs,
    )
    try:
        _cache.set(key, resp)
    except Exception:
        pass
    return resp
