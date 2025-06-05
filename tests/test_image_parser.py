import sys
from pathlib import Path
from types import SimpleNamespace

sys.modules.setdefault("streamlit", SimpleNamespace(secrets={}))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import image_parser
from process_images import OutputModel, MistralInterface


def test_parse_image_bytes_returns_lowercased(monkeypatch):
    def fake_parse_images(self, prompt: str, images: list[str]):
        return [
            OutputModel(type="ingredients", barcode=None, ingredients=["Egg", "Milk"])
        ]

    monkeypatch.setattr(MistralInterface, "parse_images", fake_parse_images)
    result = image_parser.parse_image_bytes(b"x")
    assert result == ["egg", "milk"]


def test_parse_image_bytes_handles_empty(monkeypatch):
    def fake_parse_images(self, prompt: str, images: list[str]):
        return []

    monkeypatch.setattr(MistralInterface, "parse_images", fake_parse_images)
    assert image_parser.parse_image_bytes(b"x") == []

