import image_parser
from process_images import OutputModel


def test_parse_image_bytes_returns_lowercased(monkeypatch):
    def fake_parse_images(prompt: str, images: list[str]):
        return [OutputModel(type="ingredients", barcode=None, ingredients=["Egg", "Milk"])]

    monkeypatch.setattr(image_parser._api, "parse_images", fake_parse_images)
    result = image_parser.parse_image_bytes(b"x")
    assert result == ["egg", "milk"]


def test_parse_image_bytes_handles_empty(monkeypatch):
    def fake_parse_images(prompt: str, images: list[str]):
        return []

    monkeypatch.setattr(image_parser._api, "parse_images", fake_parse_images)
    assert image_parser.parse_image_bytes(b"x") == []

