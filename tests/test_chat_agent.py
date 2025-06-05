import json
from types import SimpleNamespace



from config import AppConfig
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
    cfg = AppConfig(api_key="test")

    sample_results = [
        {"title": "A", "url": "u1"},
        {"title": "B", "url": "u2"},
        {"title": "C", "url": "u3"},
    ]

    monkeypatch.setattr(
        "chat_agent.query_top_k",
        lambda **kwargs: sample_results,
    )

    def fake_chat_parse(*a, **k):
        if k.get("response_format") is chat_agent.QueryRequest:
            msg = SimpleNamespace(parsed=chat_agent.QueryRequest())
        else:
            msg = SimpleNamespace(parsed=chat_agent.RecipeRankResponse(new_order=[2, 0, 1]))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr("chat_agent.chat_parse", fake_chat_parse)

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
    # chat_complete no longer used

    ordered = search_and_rerank("chicken", cfg, ["s1"])
    assert [r["title"] for r in ordered] == ["B", "C", "A"]

