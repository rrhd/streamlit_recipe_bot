import logging
from typing import Any

import numpy as np
from mistralai.models import SystemMessage, UserMessage
from mistralai.models.toolchoice import ToolChoice
from pydantic import BaseModel

from config import AppConfig
from constants import ModelName, ToolText, ToolCall, AgentText, SearchLimit
from models import QueryRequest, RecipeSearchArgs, RecipeRankArgs
from mistralai.models.function import Function
from mistralai.models.tool import Tool
from query_top_k import query_top_k
from mistral_utils import embeddings_create, chat_complete, chat_parse


RESULT_LIMIT = SearchLimit.RESULTS



SEARCH_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.SEARCH_RECIPES,
        description=ToolText.SEARCH_DESC,
        parameters=RecipeSearchArgs.model_json_schema(),
    ),
)

RANK_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.RANK_RECIPES,
        description=ToolText.RANK_DESC,
        parameters=RecipeRankArgs.model_json_schema(),
    ),
)


def _parse_query(query: str, cfg: AppConfig, sources: list[str]) -> QueryRequest:
    messages = [
        SystemMessage(content=AgentText.PARSE_SYSTEM),
        UserMessage(content=AgentText.PARSE_USER.format(query=query)),
    ]
    try:
        resp = chat_parse(
            cfg,
            messages=messages,
            model=ModelName.CHAT_SMALL,
            response_format=QueryRequest,
        )
        args: QueryRequest = resp.choices[0].message.parsed
    except Exception as e:
        logging.error("Query parsing failed: %s", e)
        args = QueryRequest(keywords_to_include=query.split())
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
    try:
        resp = embeddings_create(config, inputs=titles, model=ModelName.EMBED_BASE)
    except Exception as e:
        logging.error("Embedding request failed: %s", e)
        return results[:RESULT_LIMIT]

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
    try:
        resp_rank = chat_complete(
            config,
            messages=messages,
            model=ModelName.CHAT_SMALL,
            tools=[RANK_TOOL],
            tool_choice=ToolChoice(function={"name": ToolCall.RANK_RECIPES}),
            temperature=0.2,
        )
        ordered: list[dict[str, Any]] = []
        if resp_rank.choices[0].message.tool_calls:
            call = resp_rank.choices[0].message.tool_calls[0]
            args = RecipeRankArgs.model_validate_json(call.function.arguments)
            for idx in args.order:
                if 1 <= idx <= len(ranked):
                    ordered.append(ranked[idx - 1])
        if ordered:
            ranked = ordered
    except Exception as e:
        logging.error("LLM ranking failed: %s", e)

    return ranked[:RESULT_LIMIT]
