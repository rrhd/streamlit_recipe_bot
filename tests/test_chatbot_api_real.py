import json
from datetime import datetime

import json
from datetime import datetime

import pytest
from mistralai.models import (
    AssistantMessage,
    UserMessage,
    ToolMessage,
    TextChunk,
)

from cache_manager import fetch_db_last_updated
from chat_agent import SEARCH_TOOL, search_and_rerank, _parse_query
from config import CONFIG
from constants import ModelName, FormatStrings
from db_utils import fetch_sources_cached
from mistral_utils import chat_complete
from models import RecipeSearchArgs
from session_state import SessionStateKeys
from ui_pages.chatbot import render_chatbot_page, _prep_history


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






def test_search_and_rerank_real(monkeypatch):
    monkeypatch.setattr(
        "chat_agent.query_top_k",
        lambda **_: [
            {"title": "Chicken Biryani", "url": "https://example.com/biryani"},
            {"title": "Chicken Fried Rice", "url": "https://example.com/fried"},
        ],
    )

    results = search_and_rerank("chicken rice", CONFIG, ["dummy"])
    assert results and isinstance(results[0], dict)


def test_chatbot_page_real(monkeypatch):
    fake = _FakeChat(user_input="chicken rice")
    fake.session_state[SessionStateKeys.ALL_SOURCES_LIST] = ["dummy"]

    monkeypatch.setattr(
        "ui_pages.chatbot.search_and_rerank",
        lambda q, c, s: [{"title": "R1", "url": "https://example.com"}],
    )

    render_chatbot_page(fake, CONFIG)

    assert any(role == "assistant" for role, _ in fake.messages)

@pytest.mark.parametrize(
    "query",
    [
        'savory hearty recipes with eggs and watermelon'
    ]
)
def test_parse_query(query):
    config = CONFIG
    sources = ["dummy_source"]
    params = _parse_query(query, config, sources)


@pytest.mark.parametrize(
    "user_input",
    [
        "I pretty much have an empty fridge all the time, except for gatorade and eggs, microplastics as well. I have some watermelon, I can get new ingredients though, I want something savory and hearty, not soup, using typical ingredients, basic and minimal equipment. Make sure to do a query",
    ]
)
def test_chatbot_page_real_with_files(user_input):
    db_update_time = fetch_db_last_updated()
    cache_key_time = (
        db_update_time.strftime(FormatStrings.TIMESTAMP_CACHE_KEY)
        if isinstance(db_update_time, datetime)
        else str(db_update_time)
    )
    new_sources = fetch_sources_cached(cache_key_time)
    config = CONFIG
    content_chunks = []
    chat_history = []
    content_chunks.append(TextChunk(text=user_input))
    chat_history.append(UserMessage(content=content_chunks))
    response = chat_complete(
        config,
        messages=_prep_history(chat_history),
        model=ModelName.CHAT_SMALL,
        tools=[SEARCH_TOOL],
        tool_choice="auto",
    )
    msg = response.choices[0].message
    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        args = RecipeSearchArgs.model_validate_json(tool_call.function.arguments)


        results = search_and_rerank(
            args.query,
            config,
            sources=new_sources
        )
        results_short = [
            {"title": r.get("title"), "url": r.get("url")}
            for r in results
        ]
        tool_result = json.dumps(results_short)
        if len(results) == 0:
            chat_history.append(
                ToolMessage(tool_call_id=tool_call.id, content="Search failed, tell user to be more specific."
                            , name=tool_call.function.name)
            )
        else:
            chat_history.append(
                ToolMessage(tool_call_id=tool_call.id, content=tool_result, name=tool_call.function.name)
            )
        follow = chat_complete(
            config,
            messages=_prep_history(chat_history),
            model=ModelName.CHAT_SMALL,
        )
        final_msg = follow.choices[0].message
        if final_msg.content:
            final_assistant = AssistantMessage(content=final_msg.content)
            chat_history.append(final_assistant)