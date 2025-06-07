import json
import logging
import sqlite3
from typing import Any

import numpy as np
from mistralai.models import SystemMessage, UserMessage
from mistralai.models.function import Function
from mistralai.models.tool import Tool

from config import AppConfig
from constants import ModelName, ToolText, ToolCall, AgentText, SearchLimit
from mistral_utils import embeddings_create, chat_parse
from models import (
    QueryRequest,
    RecipeSearchArgs,
    RecipeRankArgs,
    RecipeRankResponse,
)
from query_top_k import query_top_k, get_db_connection


def _fetch_top_n_from_db(
    conn: sqlite3.Connection, sql: str, n: int, params: tuple[Any, ...] = ()
) -> list[str]:
    """Fetches a list of single-column results from the DB."""
    return [str(row[0]) for row in conn.execute(sql, (*params, n)).fetchall()]


def _fetch_tag_stats_from_db(
    conn: sqlite3.Connection
) -> dict[str, list[str]]:
    """
    Fetches tag statistics, mimicking the structure of `tag_examples`
    from your snapshot: a dict of category -> list of top tag titles.
    """
    # This query gets all tags grouped and ordered, Python will do the limiting per category.
    rows = conn.execute(
        """
        SELECT category, title, COUNT(*) AS cnt
        FROM recipe_tags
        WHERE category IS NOT NULL AND title IS NOT NULL AND category != '' AND title != ''
        GROUP BY category, title
        ORDER BY category, cnt DESC
        """
    ).fetchall() # .fetchall() is fine here as we'll process in Python

    tag_stats_dict: dict[str, list[str]] = {}
    # To keep track of how many distinct categories we've added to our snippet list
    categories_in_snippet = 0
    # To limit tags per category in the snippet
    # (using a hypothetical constant, adjust as needed)
    tags_per_category_limit = getattr(SearchLimit, 'MAX_TAGS_PER_CATEGORY_IN_PROMPT', 3)


    for row in rows:
        # Assumes conn.row_factory = sqlite3.Row is set
        cat = str(row['category']) # Ensure category is a string key
        title = str(row['title'])

        # If we haven't seen this category yet and we've already collected enough categories
        if cat not in tag_stats_dict and \
           categories_in_snippet >= getattr(SearchLimit, 'MAX_TAG_CATEGORIES_TO_SHOW_IN_PROMPT', 5): # Define this limit
            continue

        bucket = tag_stats_dict.setdefault(cat, [])

        if len(bucket) < tags_per_category_limit:
            bucket.append(title)
            if len(bucket) == 1 and cat not in tag_stats_dict: # This check seems redundant with setdefault
                                                             # and how categories_in_snippet is managed.
                                                             # Better to increment categories_in_snippet
                                                             # when a new category is *first* added.
                                                             # Let's refine this.
                pass # This part of the original logic for distinct_categories_processed needs care

    # A cleaner way to manage distinct categories added to the output dictionary
    final_tag_stats_dict: dict[str, list[str]] = {}
    distinct_categories_added = 0
    # Define how many categories you want in your prompt, e.g., top 5-7 most frequent overall.
    # For that, the SQL might need to change or you sort categories by total count first.
    # The current approach takes top tags from categories as they appear.

    # Let's refine the loop to correctly limit categories and tags per category
    tag_stats_dict_intermediate: dict[str, list[str]] = {}
    for row in rows:
        cat = str(row['category'])
        title = str(row['title'])

        if cat not in tag_stats_dict_intermediate:
            # If we are about to add a new category, check if we've hit the category limit
            if len(tag_stats_dict_intermediate) >= getattr(SearchLimit, 'MAX_TAG_CATEGORIES_TO_SHOW_IN_PROMPT', 7): # e.g. 7 categories
                # If this new category 'cat' would exceed the limit, and it's not one we're already tracking, skip
                # This ensures we fill up to X categories, and then only add to existing ones.
                # To be truly "top categories", the SQL would need pre-aggregation or Python post-processing.
                # For simplicity here, we take the first N categories encountered that have tags.
                continue # Or break if categories are sorted by overall importance

        bucket = tag_stats_dict_intermediate.setdefault(cat, [])
        if len(bucket) < tags_per_category_limit: # e.g. 3 tags per category
            bucket.append(title)

    return tag_stats_dict_intermediate

def _get_dynamic_db_data(conn: sqlite3.Connection) -> dict[str, Any]:
    """Fetches all required dynamic data from the database."""
    ingredients = _fetch_top_n_from_db(
        conn,
        "SELECT normalized_ingredient FROM recipe_ingredients "
        "GROUP BY normalized_ingredient "
        "ORDER BY COUNT(*) DESC LIMIT ?",
        SearchLimit.MAX_INGREDIENT_EXAMPLES,
    )

    tag_examples = _fetch_tag_stats_from_db(conn)

    equipment = _fetch_top_n_from_db(
        conn,
        "SELECT DISTINCT equipment FROM recipe_schema "
        "WHERE equipment IS NOT NULL AND equipment != '' "
        "ORDER BY RANDOM() LIMIT ?", # RANDOM() can be slow on large tables
        SearchLimit.MAX_EQUIPMENT_EXAMPLES,
    )

    titles = _fetch_top_n_from_db(
        conn,
        "SELECT title FROM recipe_schema "
        "WHERE title IS NOT NULL AND title != '' "
        "ORDER BY RANDOM() LIMIT ?", # RANDOM() can be slow
        SearchLimit.MAX_TITLE_EXAMPLES,
    )

    return {
        "ingredient_examples": ingredients,
        "tag_examples": tag_examples,
        "equipment_examples": equipment,
        "title_examples": titles,
    }

# --- Helper Function to Format Tag Examples (Same as before) ---
def _format_tag_examples_for_prompt(
    tag_examples_dict: dict[str, list[str]],
    categories_to_show: list[str] | None = None,
    max_tags_per_cat: int = SearchLimit.MAX_TAGS_PER_CATEGORY_IN_PROMPT
) -> str:
    formatted_lines = []
    categories_to_iterate = categories_to_show if categories_to_show is not None else sorted(list(tag_examples_dict.keys()))

    for category in categories_to_iterate:
        if category in tag_examples_dict:
            tags = tag_examples_dict[category]
            if tags:
                safe_tags = [str(tag) for tag in tags[:max_tags_per_cat]]
                example_tags_str = ", ".join(safe_tags)
                formatted_lines.append(f"    – **{category}**: e.g., {example_tags_str}")
    return "\n".join(formatted_lines)



def _make_system_prompt_info(
    db_connection_provider: callable = get_db_connection
) -> dict[str, str]:
    """
    Constructs the dictionary of information to fill in the system prompt template,
    fetching data directly from the database.
    """
    conn = db_connection_provider()
    db_data = _get_dynamic_db_data(conn)
    conn.close()
    query_request_schema_dict = QueryRequest.model_json_schema()
    schema_as_json_string = json.dumps(query_request_schema_dict, indent=2)


    # 2. Ingredient Examples
    ingredient_examples_str = ", ".join(db_data.get('ingredient_examples', []))

    # 3. Tag Category Examples
    tag_category_examples_str = _format_tag_examples_for_prompt(
        db_data.get('tag_examples', {})
    )

    # 4. Equipment Examples
    equipment_examples_str = "; ".join(db_data.get('equipment_examples', []))

    # 5. Title Examples
    title_examples_str = "; ".join(db_data.get('title_examples', []))

    return {
        "query_request_schema_json": schema_as_json_string,
        "ingredient_examples_str": ingredient_examples_str,
        "tag_category_examples_str": tag_category_examples_str,
        "equipment_examples_str": equipment_examples_str,
        "title_examples_str": title_examples_str,
    }


SEARCH_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.SEARCH_RECIPES,
        description=ToolText.SEARCH_DESC,
        parameters=RecipeSearchArgs.model_json_schema()
    ),
)

RANK_TOOL = Tool(
    type="function",
    function=Function(
        name=ToolCall.RANK_RECIPES,
        description=ToolText.RANK_DESC,
        parameters=RecipeRankArgs.model_json_schema()
    ),
)


def _parse_query(query: str, cfg: AppConfig, sources: list[str]) -> QueryRequest:
    prompt = AgentText.PARSE_SYSTEM.format(
        **_make_system_prompt_info()
    )
    messages = [
        SystemMessage(content=prompt),
        UserMessage(content=AgentText.PARSE_USER.format(query=query)),
    ]
    resp = chat_parse(
        cfg,
        messages=messages,
        model=ModelName.CHAT_SMALL,
        response_format=QueryRequest,
        max_tokens= SearchLimit.MAX_QUERY_TOKENS,
    )
    args: QueryRequest = resp.choices[0].message.parsed
    return args


def search_and_rerank(query: str, config: AppConfig, sources: list[str]) -> list[dict[str, Any]]:
    """Parse the query, execute search, then rerank results."""
    params = _parse_query(query, config, sources)
    # We set these to empty lists to avoid any filtering by keywords, as that is too aggressive
    params.keywords_to_include = []
    params.keywords_to_exclude = []
    results = query_top_k(**params.model_dump(), sources=sources)

    if not results:
        return []
    # JSON dump each result to ensure we have a consistent format
    titles = [query] + [f"{r.get('title', '')} {r.get('description', '')}" for r in results]
    try:
        resp = embeddings_create(config, inputs=titles, model=ModelName.EMBED_BASE)
    except Exception as e:
        logging.error("Embedding request failed: %s", e)
        return results[:SearchLimit.RESULTS]

    embeds = [d.embedding for d in resp.data]
    query_vec = np.array(embeds[0])
    recipe_vecs = np.array(embeds[1:])
    denom = np.linalg.norm(recipe_vecs, axis=1) * np.linalg.norm(query_vec)
    sims = recipe_vecs @ query_vec / (denom + 1e-10)
    ranked = [r for _, r in sorted(zip(sims, results), key=lambda p: p[0], reverse=True)]
    # JSON dump each result to ensure we have all the information we need
    items = "\n".join(
        f"{i + 1}. {json.dumps(r, ensure_ascii=False, indent=2)}" for i, r in enumerate(ranked[:SearchLimit.RESULTS])
    )
    messages = [
        SystemMessage(content=AgentText.RERANK_SYSTEM),
        UserMessage(content=AgentText.RERANK_USER.format(query=query) + "\n" + items),
    ]
    try:
        resp_rank = chat_parse(
            config,
            messages=messages,
            model=ModelName.CHAT_SMALL,
            response_format=RecipeRankResponse,
        )
        order_idx = resp_rank.choices[0].message.parsed.new_order
        ranked = [
                     ranked[i - 1]
                     for i in order_idx
                     if 0 < i <= len(ranked)
                 ] or ranked
    except Exception as e:
        logging.error("LLM ranking failed: %s", e)

    return ranked[:SearchLimit.RESULTS]
