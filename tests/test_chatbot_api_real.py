import os
import pytest

from config import CONFIG
from chat_agent import search_and_rerank
from ui_pages.chatbot import render_chatbot_page
from session_state import SessionStateKeys


class _FakeChat:
    def __init__(self, user_input: str = ""):
        self.input = user_input
        self.messages: list[tuple[str, str]] = []
        self.session_state = {}
        self.sidebar = _FakeSidebar()

    def header(self, _):
        pass

    def info(self, _):
        pass

    def chat_input(self, _):
        return self.input

    def file_uploader(self, *_, **__):
        return []

    def chat_message(self, role: str):
        return _FakeChatMessage(self.messages, role)


class _FakeChatMessage:
    def __init__(self, store: list[tuple[str, str]], role: str):
        self.store = store
        self.role = role

    def markdown(self, content: str):
        self.store.append((self.role, content))


class _FakeSidebar:
    def __init__(self):
        self.records: list[str] = []

    def expander(self, *_args, **_kwargs):
        return self

    def markdown(self, text: str):
        self.records.append(text)


API_KEY = CONFIG.api_key or os.getenv("MISTRAL_API_KEY")


@pytest.mark.skipif(API_KEY is None, reason="Mistral API key not configured")
def test_search_and_rerank_real(monkeypatch):
    monkeypatch.setattr(
        "chat_agent.query_top_k",
        lambda **_: [
            {"title": "Chicken Biryani", "url": "https://example.com/biryani"},
            {"title": "Chicken Fried Rice", "url": "https://example.com/fried"},
            {"title": "Chicken-fried steak", "url": "https://example.com/steak"},
        ],
    )

    results = search_and_rerank("chicken rice", CONFIG, ["dummy"])
    for r in results:
        assert r["title"] != "Chicken-fried steak"
    assert len(results) == 2


@pytest.mark.skipif(API_KEY is None, reason="Mistral API key not configured")
def test_chatbot_page_real(monkeypatch):
    fake = _FakeChat(user_input="chicken rice")
    fake.session_state[SessionStateKeys.ALL_SOURCES_LIST] = ["dummy"]

    monkeypatch.setattr(
        "ui_pages.chatbot.search_and_rerank",
        lambda q, c, s: [{"title": "R1", "url": "https://example.com"}],
    )

    render_chatbot_page(fake, CONFIG)

    assert any(role == "assistant" for role, _ in fake.messages)
