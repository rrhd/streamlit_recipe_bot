from __future__ import annotations

import json
from typing import Any, Iterable

from diskcache import Cache
from functools import lru_cache
from mistralai import Mistral

from config import AppConfig
from constants import ModelName

_cache = Cache("mistral_cache")

@lru_cache(maxsize=1)
def get_client(api_key: str) -> Mistral:
    """Return a cached Mistral client."""
    return Mistral(api_key=api_key)


def _cache_key(prefix: str, payload: Any) -> str:
    try:
        body = json.dumps(payload, sort_keys=True)
    except TypeError:
        body = str(payload)
    return f"{prefix}:{body}"


def chat_complete(cfg: AppConfig, *, messages: list, model: ModelName, **kwargs: Any) -> Any:
    """Cached wrapper around Mistral.chat.complete."""
    client = get_client(cfg.api_key)
    key = _cache_key("chat", {"model": model, "messages": [getattr(m, "model_dump", lambda: m)() for m in messages], **kwargs})
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
            "messages": [getattr(m, "model_dump", lambda: m)() for m in messages],
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
