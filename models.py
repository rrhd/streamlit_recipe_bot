"""Models for request payloads."""

from typing import Any

from pydantic import BaseModel, Field

from constants import TagFilterMode


def rec_strict_json_schema(schema_node: Any) -> Any:
    """Recursively enforce ``additionalProperties=False`` on a JSON schema."""

    if isinstance(schema_node, (str, bool)) or schema_node is None:
        return schema_node
    if isinstance(schema_node, dict):
        if schema_node.get("type") == "object":
            schema_node["additionalProperties"] = False
        for key, value in schema_node.items():
            schema_node[key] = rec_strict_json_schema(value)
    elif isinstance(schema_node, list):
        for idx, value in enumerate(schema_node):
            schema_node[idx] = rec_strict_json_schema(value)
    else:
        raise ValueError(f"Unexpected type: {schema_node}")
    return schema_node


def strict_model_schema(model: type[BaseModel]) -> dict:
    """Return a strict JSON schema for ``model``."""

    return rec_strict_json_schema(model.model_json_schema())


class RecipeRankResponse(BaseModel):
    """Structured ranking for the candidate recipes."""

    new_order: list[int] = Field(
        ...,
        description=(
            "0-based indices of the input recipes in preferred order. "
            "Include only recipes you deem relevant; omit indices for irrelevant recipes."
        ),
        examples=[
            ["0", "2", "1"],
            ["1", "0", "2"],
        ],
    )


class QueryRequest(BaseModel):
    """Parameters for advanced recipe searches."""

    user_ingredients: list[str] = Field(
        default_factory=list,
        examples=[["chicken", "rice"]],
        description="Ingredients the user has available.",
    )
    must_use: list[str] = Field(
        default_factory=list,
        examples=[["onion"]],
        description="Ingredients that must appear in the recipe.",
    )
    forbidden_ingredients: list[str] = Field(
        default_factory=list,
        examples=[["peanut"]],
        description="Ingredients that must be absent from the recipe.",
    )
    sources: list[str] = Field(
        default_factory=list,
        examples=[["example.com"]],
        description="Recipe source domains to search.",
    )
    tag_filters: dict[str, list[str]] = Field(
        default_factory=dict,
        examples=[{"cuisine": ["Indian"]}],
        description="Tags to include grouped by category.",
    )
    excluded_tags: dict[str, list[str]] = Field(
        default_factory=dict,
        examples=[{"course": ["Dessert"]}],
        description="Tags to exclude grouped by category.",
    )
    min_ing_matches: int | None = Field(
        default=None,
        description="Minimum number of ingredient matches required.",
        examples=["2"],
    )
    tag_filter_mode: TagFilterMode = Field(
        default=TagFilterMode.AND,
        description="Mode for combining include tag filters.",
    )
    max_steps: int | None = Field(
        default=None,
        description="Maximum allowed instruction steps (None for no limit).",
        examples=["10"],
    )
    user_coverage_req: float | None = Field(
        default=None,
        description="Required fraction of user ingredients present in recipe.",
        examples=["0.5"],
    )
    recipe_coverage_req: float | None = Field(
        default=None,
        description="Required fraction of recipe ingredients present in user list.",
        examples=["0.5"],
    )
    keywords_to_include: list[str] = Field(
        default_factory=list,
        examples=[["quick"]],
        description="Keywords that must appear in the recipe title or description.",
    )
    keywords_to_exclude: list[str] = Field(
        default_factory=list,
        examples=[["slow"]],
        description="Keywords that must not appear in the recipe.",
    )


class SimpleSearchRequest(BaseModel):
    """Request body for simple text-based recipe searches."""

    query: str


from pydantic import BaseModel


class SaveProfileRequest(BaseModel):
    username: str
    timestamp: str
    options_base64: str


class LoadProfileRequest(BaseModel):
    username: str
    timestamp: str | None = None


class RecipeSearchArgs(BaseModel):
    """Arguments for the recipe search tool."""

    query: str


class RecipeRankArgs(BaseModel):
    """Arguments returned by the ranking tool."""

    order: list[int]
