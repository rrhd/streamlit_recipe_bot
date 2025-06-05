import logging
from typing import Any

import numpy as np
try:
    from mistralai.models import SystemMessage, UserMessage
    from mistralai.models.toolchoice import ToolChoice
    from mistralai.models.function import Function
    from mistralai.models.tool import Tool
except Exception:  # pragma: no cover - fallback
    from mistralai.models import SystemMessage, UserMessage  # type: ignore
    from mistralai.models.toolchoice import ToolChoice  # type: ignore
    from mistralai.models.function import Function  # type: ignore
    from mistralai.models.tool import Tool  # type: ignore
from pydantic import BaseModel

from config import AppConfig
from constants import ModelName, ToolText, ToolCall, AgentText, SearchLimit
from models import (
    QueryRequest,
    RecipeSearchArgs,
    RecipeRankArgs,
    strict_model_schema,
    RecipeRankResponse,
)
from query_top_k import query_top_k
from mistral_utils import embeddings_create, chat_complete, chat_parse


RESULT_LIMIT = SearchLimit.RESULTS



SEARCH_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.SEARCH_RECIPES,
        description=ToolText.SEARCH_DESC,
        parameters=strict_model_schema(RecipeSearchArgs),
    ),
)

RANK_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.RANK_RECIPES,
        description=ToolText.RANK_DESC,
        parameters=strict_model_schema(RecipeRankArgs),
    ),
)


def _parse_query(query: str, cfg: AppConfig, sources: list[str]) -> QueryRequest:
    messages = [
        SystemMessage(content=AgentText.PARSE_SYSTEM),
        UserMessage(content=AgentText.PARSE_USER.format(query=query)),
    ]
    resp = chat_parse(
        cfg,
        messages=messages,
        model=ModelName.CHAT_LARGE,
        response_format=QueryRequest,
    )
    args: QueryRequest = resp.choices[0].message.parsed
    if not args.sources:
        args.sources = sources
    return args


def search_and_rerank(query: str, config: AppConfig, sources: list[str]) -> list[dict[str, Any]]:
    """Parse the query, execute search, then rerank results."""
    params = _parse_query(query, config, sources)
    results = query_top_k(**params.model_dump())

    if not results:
        return []

    titles = [query] + [r.get("title", "") for r in results]
    resp = embeddings_create(config, inputs=titles, model=ModelName.EMBED_BASE)
    embeds = [d.embedding for d in resp.data]
    query_vec = np.array(embeds[0])
    recipe_vecs = np.array(embeds[1:])
    denom = np.linalg.norm(recipe_vecs, axis=1) * np.linalg.norm(query_vec)
    sims = recipe_vecs @ query_vec / (denom + 1e-10)
    ranked = [r for _, r in sorted(zip(sims, results), key=lambda p: p[0], reverse=True)]

    items = "\n".join(
        f"{i + 1}. {r.get('url', '')}" for i, r in enumerate(ranked[:RESULT_LIMIT])
    )
    messages = [
        SystemMessage(content=AgentText.RERANK_SYSTEM),
        UserMessage(content=AgentText.RERANK_USER.format(query=query) + "\n" + items),
    ]
    resp_rank = chat_parse(
    cfg=config,
    messages=messages,
    model=ModelName.CHAT_LARGE,
    response_format=RecipeRankResponse,
    )
    ordered: RecipeRankResponse = resp_rank.choices[0].message.parsed
    ranked = [ranked[i] for i in ordered.new_order if i < len(ranked)]

    return ranked[:RESULT_LIMIT]
