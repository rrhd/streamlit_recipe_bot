"""Models for request payloads."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for advanced 'top_k' queries."""

    user_ingredients: list[str] = Field(default_factory=list)
    must_use: list[str] = Field(default_factory=list)
    forbidden_ingredients: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    tag_filters: dict[str, list[str]] = Field(default_factory=dict)
    excluded_tags: dict[str, list[str]] = Field(default_factory=dict)
    min_ing_matches: int = 0
    tag_filter_mode: str = Field(default="AND")
    max_steps: int = 0
    user_coverage_req: float = 0.0
    recipe_coverage_req: float = 0.0
    keywords_to_include: list[str] = Field(default_factory=list)
    keywords_to_exclude: list[str] = Field(default_factory=list)


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
