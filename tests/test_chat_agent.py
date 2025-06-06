import json

import sys
from types import ModuleType, SimpleNamespace

dummy = ModuleType('query_top_k')
dummy.query_top_k = lambda **kwargs: []
sys.modules['query_top_k'] = dummy


from config import AppConfig, CONFIG
import chat_agent
from chat_agent import search_and_rerank


class DummyEmb:
    def __init__(self, embedding):
        self.embedding = embedding


class DummyEmbedResp:
    def __init__(self, data):
        self.data = [DummyEmb(e) for e in data]


class DummyChatResp:
    def __init__(self, order):
        call = SimpleNamespace(
            id="1",
            function=SimpleNamespace(arguments=json.dumps({"order": order})),
        )
        msg = SimpleNamespace(tool_calls=[call])
        choice = SimpleNamespace(message=msg)
        self.choices = [choice]


def test_search_and_rerank_uses_llm_order(monkeypatch):
    cfg = CONFIG

    sample_results = [
        {"title": "A", "url": "u1"},
        {"title": "B", "url": "u2"},
        {"title": "C", "url": "u3"},
    ]

    monkeypatch.setattr(
        "chat_agent.query_top_k",
        lambda **kwargs: sample_results,
    )

    monkeypatch.setattr(
        "chat_agent.chat_parse",
        lambda *a, **k: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=chat_agent.QueryRequest()))]
        ),
    )

    def fake_embeddings_create(*args, **kwargs):
        return DummyEmbedResp(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [0.0, 0.5],
                [1.0, 0.0],
            ]
        )

    monkeypatch.setattr("chat_agent.embeddings_create", fake_embeddings_create)
    monkeypatch.setattr(
        "chat_agent.chat_complete", lambda *a, **k: DummyChatResp([3, 1, 2])
    )

    ordered = search_and_rerank("chicken", cfg, ["s1"])
    assert [r["title"] for r in ordered] == ["B", "C", "A"]


