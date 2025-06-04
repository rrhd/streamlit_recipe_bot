import json
from types import SimpleNamespace

import pytest
import streamlit as st

st.secrets._secrets = {}

import sys
from types import ModuleType

dummy = ModuleType('query_top_k')
dummy.query_top_k = lambda **kwargs: []
sys.modules['query_top_k'] = dummy


from config import AppConfig
from session_state import SessionStateKeys
from ui_pages.chatbot import render_chatbot_page


class FakeExpander:
    def __init__(self):
        self.markdowns = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def markdown(self, text):
        self.markdowns.append(text)


class FakeSidebar:
    def __init__(self, parent):
        self.parent = parent
        self.expanders = []

    def expander(self, title, expanded=True):
        exp = FakeExpander()
        self.expanders.append(exp)
        return exp


class FakeChatMessage:
    def __init__(self, store, role):
        self.store = store
        self.role = role

    def markdown(self, content):
        self.store.append((self.role, content))


class FakeStreamlit:
    def __init__(self, user_input=""):
        self.input = user_input
        self.session_state = {}
        self.sidebar = FakeSidebar(self)
        self.messages = []

    def header(self, text):
        pass

    def info(self, text):
        pass

    def chat_input(self, placeholder):
        return self.input

    def file_uploader(self, *a, **k):
        return []

    def chat_message(self, role):
        return FakeChatMessage(self.messages, role)

    def markdown(self, text):
        if self.sidebar.expanders:
            self.sidebar.expanders[-1].markdown(text)

    def error(self, text):
        self.messages.append(("error", text))


def test_render_chatbot_page_flow(monkeypatch):
    cfg = AppConfig(api_key="test")
    st = FakeStreamlit(user_input="chicken")
    st.session_state[SessionStateKeys.ALL_SOURCES_LIST] = ["s1"]

    def fake_chat_complete(*args, **kwargs):
        if fake_chat_complete.calls == 0:
            fake_chat_complete.calls += 1
            call = SimpleNamespace(
                id="1",
                function=SimpleNamespace(arguments=json.dumps({"query": "chicken"})),
            )
            msg = SimpleNamespace(content="searching", tool_calls=[call])
        else:
            msg = SimpleNamespace(content="done", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    fake_chat_complete.calls = 0

    monkeypatch.setattr("ui_pages.chatbot.chat_complete", fake_chat_complete)
    monkeypatch.setattr(
        "ui_pages.chatbot.search_and_rerank",
        lambda q, cfg, sources: [{"title": "R1", "url": "url1"}],
    )

    render_chatbot_page(st, cfg)

    history = st.session_state[SessionStateKeys.CHAT_HISTORY]
    assert history[-1].content == "done"
    assert st.sidebar.expanders[-1].markdowns == ["1. [R1](url1)"]

