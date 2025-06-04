import base64

from config import AppConfig
from process_images import CacheManager, MistralInterface


class ImageParser:
    def __init__(self, cfg: AppConfig | None = None) -> None:
        import streamlit as st

        cfg = cfg or AppConfig(**getattr(st, "secrets", {}))
        self._cache = CacheManager(cfg)
        self._api = MistralInterface(cfg, self._cache)
        if cfg.prompt_path and cfg.prompt_path.exists():
            self._prompt = cfg.prompt_path.read_text("utf-8")
        else:
            self._prompt = ""

    def parse_bytes(self, data: bytes) -> list[str]:
        b64 = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        parsed = self._api.parse_images(self._prompt, [b64])
        if parsed:
            result = parsed[0]
            return (
                [ing.lower() for ing in result.ingredients]
                if result.ingredients
                else []
            )
        return []


def parse_image_bytes(data: bytes, parser: ImageParser | None = None) -> list[str]:
    return (parser or ImageParser()).parse_bytes(data)
