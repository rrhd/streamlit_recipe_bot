# image_parser.py
import asyncio, base64

from config import CONFIG
from process_images import LoggerManager, CacheManager, MistralInterface

_logger = LoggerManager(CONFIG)         # build once
_cache  = CacheManager(CONFIG)
_api    = MistralInterface(CONFIG, _cache)

_prompt = CONFIG.prompt_path.read_text("utf-8")

def parse_image_bytes(data: bytes) -> list[str]:
    """Return ingredient lines from one image (blocking)."""
    b64 = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    result = _api.parse_images(_prompt, [b64])[0]
    return result.ingredients or []
