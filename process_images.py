#!/usr/bin/env python3
# Python 3.12
import base64
import json
import logging
import sys
from pathlib import Path
from typing import Literal

from diskcache import Cache
from mistralai import Mistral
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import retry, retry_if_exception, stop_after_attempt

from config import CONFIG
from constants import Role, ContentType, UserPrompt, ModelName, CacheLimit, Suffix
from exceptions import RateLimitHeaderNotFoundError



def get_retry_after(exception: BaseException) -> float | None:
    """
    Extract wait time from the exception's raw_response headers.
    Try 'Retry-After', then fallback to 'ratelimitbysize-reset'.
    """
    try:
        headers = exception.raw_response.headers  # type: ignore[attr-defined]
        retry_after = headers.get("Retry-After") or headers.get("ratelimitbysize-reset")
        if retry_after is not None:
            return float(retry_after)
    except Exception as e:
        logging.getLogger("scanner").error("Error extracting retry wait time: %s", e)
    return None


def is_rate_limit_error(exception: BaseException) -> bool:
    """Return True if exception indicates a 429 rate limit error."""
    return ("429" in str(exception)) or (
        hasattr(exception, "status_code")
        and getattr(exception, "status_code", None) == 429
    )


def custom_wait(retry_state) -> float:
    """
    Use Retry-After header for wait. Raise if header missing.
    """
    exc = retry_state.outcome.exception()
    retry_after = get_retry_after(exc)
    if retry_after is None:
        msg = "Retry-After header not found in rate limit error response."
        logging.getLogger("scanner").error(msg)
        raise RateLimitHeaderNotFoundError(msg)
    return retry_after


# ─── 3) Configuration ────────────────────────────────────────────────────────────


class AppConfig(BaseSettings):
    api_key: str
    model: ModelName = ModelName.VISION
    prompt_path: Path
    cache_dir: Path
    max_log_length: int = 200
    truncation_suffix: Suffix = Suffix.ELLIPSIS

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# ─── 4) Pydantic Models ─────────────────────────────────────────────────────────


class OutputModel(BaseModel):
    type: Literal["barcode", "ingredients"]
    barcode: str | None
    ingredients: list[str] | None


# ─── 5) Utilities ───────────────────────────────────────────────────────────────


def chunk_list(items: list[object], size: int) -> list[list[object]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


# ─── 6) Logging Manager ─────────────────────────────────────────────────────────


class LoggerManager:
    def __init__(self, cfg: AppConfig):
        self.log = logging.getLogger("scanner")
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.log.addHandler(handler)
        self.log.setLevel(logging.INFO)
        self.cfg = cfg

    def log_with_payload(self, msg: str, payload: BaseModel) -> None:
        data = payload.model_dump()
        s = json.dumps(data, default=str)
        maxl = self.cfg.max_log_length
        snippet = s if len(s) <= maxl else s[:maxl] + self.cfg.truncation_suffix
        self.log.info(f"{msg}: {snippet}", extra={"payload": data})


# ─── 7) Cache Manager ───────────────────────────────────────────────────────────


class CacheManager:
    def __init__(self, cfg: AppConfig):
        self.cache = Cache(str(cfg.cache_dir))

    def get(self, key: str) -> object | None:
        return self.cache.get(key)

    def set(self, key: str, val: object) -> None:
        self.cache.set(key, val)


# ─── 8) Mistral Interface ───────────────────────────────────────────────────────


class MistralInterface:
    def __init__(self, cfg: AppConfig, cache: CacheManager):
        self.client = Mistral(api_key=cfg.api_key)
        self.model = cfg.model
        self.cache = cache

    @retry(
        retry=retry_if_exception(is_rate_limit_error),
        wait=custom_wait,
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def parse_images(self, prompt: str, images: list[str]) -> list[OutputModel]:
        key = f"{prompt}-{','.join(images)}"
        if cached := self.cache.get(key):
            return [OutputModel.model_validate(item) for item in cached]

        messages: list[dict] = [
            {"role": Role.SYSTEM, "content": prompt},
            {
                "role": Role.USER,
                "content": (
                    [{"type": ContentType.TEXT, "text": UserPrompt.PROCESS}]
                    + [
                        {"type": ContentType.IMAGE_URL, "image_url": img}
                        for img in images
                    ]
                ),
            },
        ]
        resp = self.client.chat.parse(
            model=self.model,
            messages=messages,
            response_format=OutputModel,
            temperature=0.1,
            max_tokens=CacheLimit.MAX_TOKENS,
        )
        print(resp)
        parsed = [c.message.parsed for c in resp.choices]
        self.cache.set(key, [p.model_dump() for p in parsed])
        print(parsed[0].model_dump_json(indent=2))
        return parsed


# ─── 9) Main Entry Point ────────────────────────────────────────────────────────


def main():
    logger = LoggerManager(CONFIG)
    cache = CacheManager(CONFIG)
    api = MistralInterface(CONFIG, cache)

    prompt = CONFIG.prompt_path.read_text(encoding="utf-8")
    results: list[dict] = []

    for batch in chunk_list(sys.argv[1:], CacheLimit.MAX_IMAGES):
        imgs = [encode_image(p) for p in batch]
        outs = api.parse_images(prompt, imgs)
        for out in outs:
            logger.log_with_payload("image_processed", out)
            results.append(out.model_dump())

    print(json.dumps(results))


if __name__ == "__main__":
    main()
