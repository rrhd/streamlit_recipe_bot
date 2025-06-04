# image_parser.py
import base64

from config import CONFIG
from process_images import LoggerManager, CacheManager, MistralInterface

_logger = LoggerManager(CONFIG)         # build once
_cache  = CacheManager(CONFIG)
_api    = MistralInterface(CONFIG, _cache)

if CONFIG.prompt_path and CONFIG.prompt_path.exists():
    _prompt = CONFIG.prompt_path.read_text("utf-8")
else:
    _prompt = ""

def parse_image_bytes(data: bytes) -> list[str]:
    """Return ingredient lines from one image (blocking)."""
    b64 = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    parsed = _api.parse_images(_prompt, [b64])
    if parsed:
        result = parsed[0]
        return [ing.lower() for ing in result.ingredients] if result.ingredients else []
    return []
