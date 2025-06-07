"""Models for request payloads."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator
from pydantic import RootModel

from constants import TagFilterMode


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

class CourseEnum(StrEnum):
    Appetizers = "Appetizers"
    Desserts_or_Baked_Goods = "Desserts or Baked Goods"
    Main_Courses = "Main Courses"
    Side_Dishes = "Side Dishes"


class MainIngredientEnum(StrEnum):
    Beans = "Beans"
    Beef = "Beef"
    Cheese = "Cheese"
    Chicken = "Chicken"
    Chocolate = "Chocolate"
    Duck = "Duck"
    Eggs = "Eggs"
    Eggs_and_Dairy = "Eggs & Dairy"
    Fish_and_Seafood = "Fish & Seafood"
    Fruit = "Fruit"
    Fruits_and_Vegetables = "Fruits & Vegetables"
    Game_Birds = "Game Birds"
    Grains = "Grains"
    Lamb = "Lamb"
    Meat = "Meat"
    Pasta = "Pasta"
    Pasta_Grains_Rice_and_Beans = "Pasta, Grains, Rice & Beans"
    Pork = "Pork"
    Potatoes = "Potatoes"
    Poultry = "Poultry"
    Rice = "Rice"
    Turkey = "Turkey"
    Vegetables = "Vegetables"


class DishTypeEnum(StrEnum):
    Beverages = "Beverages"
    Breads = "Breads"
    Breakfast_and_Brunch = "Breakfast & Brunch"
    Brownies_and_Bars = "Brownies & Bars"
    Cakes = "Cakes"
    Candy = "Candy"
    Casseroles = "Casseroles"
    Condiments = "Condiments"
    Cookies = "Cookies"
    Dessert_Pies = "Dessert Pies"
    Frozen_Desserts = "Frozen Desserts"
    Fruit_Desserts = "Fruit Desserts"
    Marinades = "Marinades"
    Pizza = "Pizza"
    Puddings_Custards_Gelatins_and_Souffles = "Puddings, Custards, Gelatins, & Souffles"
    Quick_Breads = "Quick Breads"
    Roasts = "Roasts"
    Rubs = "Rubs"
    Salads = "Salads"
    Sandwiches = "Sandwiches"
    Sauces = "Sauces"
    Savory_Pies_and_Tarts = "Savory Pies & Tarts"
    Snacks = "Snacks"
    Soups = "Soups"
    Stews = "Stews"
    Tarts = "Tarts"


class RecipeTypeEnum(StrEnum):
    Cast_Iron_Skillet = "Cast-Iron Skillet"
    Dairy_Free = "Dairy-Free"
    For_Two = "For Two"
    Gluten_Free = "Gluten Free"
    Grilling_and_Barbecue = "Grilling & Barbecue"
    Light = "Light"
    Make_Ahead = "Make Ahead"
    Pressure_Cooker = "Pressure Cooker"
    Quick = "Quick"
    Reduced_Sugar = "Reduced Sugar"
    Slow_Cooker = "Slow Cooker"
    Vegan = "Vegan"
    Vegetarian = "Vegetarian"
    Weeknight = "Weeknight"


class CuisineEnum(StrEnum):
    Africa_and_Middle_East = "Africa & Middle-East"
    African = "African"
    American = "American"
    Asia = "Asia"
    Asian = "Asian"
    California = "California"
    Caribbean = "Caribbean"
    Central_and_South_American = "Central & South American"
    Chinese = "Chinese"
    Creole_and_Cajun = "Creole & Cajun"
    Eastern_European_and_German = "Eastern European & German"
    Europe = "Europe"
    French = "French"
    Great_Britain = "Great Britain"
    Greek = "Greek"
    Indian = "Indian"
    Indonesian = "Indonesian"
    Irish = "Irish"
    Italian = "Italian"
    Japanese = "Japanese"
    Korean = "Korean"
    Latin_America_and_Caribbean = "Latin America & Caribbean"
    Mexican = "Mexican"
    Mid_Atlantic = "Mid-Atlantic"
    Middle_Eastern = "Middle Eastern"
    Midwest = "Midwest"
    New_England = "New England"
    Pacific_Northwest = "Pacific Northwest"
    Southern = "Southern"
    Southwest_Tex_Mex = "Southwest (Tex-Mex)"
    Spanish_and_Portuguese = "Spanish & Portuguese"
    Thai = "Thai"
    US_and_Canada = "US & Canada"
    Vietnamese = "Vietnamese"


class HolidayEnum(StrEnum):
    Fourth_of_July = "4th of July"
    Easter = "Easter"
    Hanukkah = "Hanukkah"
    Holiday = "Holiday"
    Passover = "Passover"
    Super_Bowl = "Super Bowl"
    Thanksgiving = "Thanksgiving"
    Valentines_Day = "Valentines Day"


TAG_ENUMS: dict[str, type[StrEnum]] = {
    "course": CourseEnum,
    "main_ingredient": MainIngredientEnum,
    "dish_type": DishTypeEnum,
    "recipe_type": RecipeTypeEnum,
    "cuisine": CuisineEnum,
    "holiday": HolidayEnum,
}

TAG_ENUM_TEXT: dict[str, str] = {
    key: ", ".join(e for e in enum_cls)
    for key, enum_cls in TAG_ENUMS.items()
}

class TagFilters(BaseModel):
    course: list[CourseEnum] = Field(default_factory=list)
    main_ingredient: list[MainIngredientEnum] = Field(default_factory=list)
    dish_type: list[DishTypeEnum] = Field(default_factory=list)
    recipe_type: list[RecipeTypeEnum] = Field(default_factory=list)
    cuisine: list[CuisineEnum] = Field(default_factory=list)
    holiday: list[HolidayEnum] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """Parameters for advanced recipe searches."""

    user_ingredients: list[str] = Field(
        default_factory=list,
        examples=[["chicken", "rice"]],
        description=(
            "Free-form list of everything in the user's pantry.\n"
            "• Used purely for *scoring* unless numeric thresholds below are set."
        ),
    )
    must_use: list[str] = Field(
        default_factory=list,
        examples=[["onion"]],
        description=(
            "If non-empty, EVERY listed ingredient must appear in the recipe.\n"
            "Missing even one → recipe is discarded."
        ),
    )
    forbidden_ingredients: list[str] = Field(
        default_factory=list,
        examples=[["peanut"]],
        description="Recipes containing ANY of these ingredients are rejected outright.",
    )
    tag_filters: TagFilters = Field(
        default_factory=TagFilters,
        examples=[{"cuisine": ["Indian"]}],
        description=(
            "Tags to include, grouped by category. Keys must be valid tag types "
            "(e.g., 'cuisine', 'course') and values must be valid tags for that type."
        ),
    )
    excluded_tags: TagFilters = Field(
        default_factory=TagFilters,
        examples=[{"course": ["Dessert"]}],
        description=(
            "Tags to exclude, grouped by category. Keys must be valid tag types "
            "and values must be valid tags for that type."
        )
    )
    tag_filter_mode: TagFilterMode = Field(
        default=TagFilterMode.OR,
        description=(
            "'and'  → recipe must match **every** category present in *tag_filters* "
            "(intersection across tag_types).\n"
            "'or'   → recipe may match **any one** category (union)."
        ),
    )
    min_ing_matches: int | None = Field(
        default=None,
        description=(
            "If set, recipe must share **at least this many** ingredients with "
            "*user_ingredients*."
        ),
    )
    max_steps: int | None = Field(
        default=None,
        description="Upper bound on number of instruction steps (None → unlimited).",
    )
    keywords_to_include: list[str] = Field(
        default_factory=list,
        examples=[["quick"]],
        description="Keywords that must appear in the recipe title or description.",
    )
    keywords_to_exclude: list[str] = Field(
        default_factory=list,
        examples=[["slow"]],
        description=(
            "If ANY of these words/phrases appears anywhere, the recipe is rejected."
        ),
    )
    equipment_to_include: list[str] = Field(
        default_factory=list,
        examples=[["oven", "blender"]],
        description=(
            "Specific equipment items or types that the recipe should ideally use. "
            "The search is case-insensitive and matches parts of equipment descriptions."
        ),
    )
    equipment_to_exclude: list[str] = Field(
        default_factory=list,
        examples=[["microwave"]],
        description=(
            "Specific equipment items or types that must NOT be mentioned in the recipe's equipment list."
        ),
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
