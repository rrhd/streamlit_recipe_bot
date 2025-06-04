import os
from pathlib import Path
from typing import Self
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import streamlit as st

from constants import (
    MiscValues,
    CategoryKeys,
    FileExt,
    ConfigKeys,
    TagFilterMode,
    LogMsg, ModelName, Suffix,
)


class DefaultValues(BaseModel):
    """Default values for UI elements and operations."""

    ingredients_text: str = Field(default="")
    must_use_text: str = Field(default="")
    excluded_text: str = Field(default="")
    keywords_include: str = Field(default="")
    keywords_exclude: str = Field(default="")
    min_ing_matches: int = Field(default=0)
    max_steps: int = Field(default=0)
    user_coverage: float = Field(default=0.0)
    recipe_coverage: float = Field(default=0.0)
    tag_filter_mode: str = Field(default="AND")
    username: str = Field(default="")
    simple_query: str = Field(default="")
    profile_message: str = Field(default="<p></p>")
    no_recipes_found: str = Field(default="No recipes found.")
    loading_message: str = Field(default="<p>Loading...</p>")


class LogConfig(BaseModel):
    """Configuration for logging."""

    truncate_length: int = Field(default=500)
    default_payload_value: str = Field(default="<Not Provided>")


class AppConfig(BaseSettings):
    """Application configuration settings."""
    api_key: str | None = Field(
        default=None,
    )
    model: ModelName = ModelName.VISION
    prompt_path: Path | None = Field(default=None)
    cache_dir: Path | None = Field(default=None)
    max_log_length: int = 200
    truncation_suffix: Suffix = Suffix.ELLIPSIS
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", extra="ignore"
    )

    profile_db_path: str = Field(default=ConfigKeys.PROFILE_DB_PATH)
    book_dir_relative: str = Field(default=ConfigKeys.BOOK_DIR_RELATIVE)
    temp_dir: str = Field(default=MiscValues.TEMP_DIR)
    download_dest_dir: str = Field(default=ConfigKeys.DOWNLOAD_DEST_DIR)
    recipe_db_filename: str = Field(default=ConfigKeys.RECIPE_DB_FILENAME)

    defaults: DefaultValues = Field(default_factory=DefaultValues)

    book_dir: str | None = Field(default=None)
    full_profile_db_path: str | None = Field(default=None)

    essential_filenames: list[str] | None = Field(default=None)

    category_choices: dict[CategoryKeys, list[str]] = Field(
        default={
            CategoryKeys.COURSE: [
                "Appetizers",
                "Desserts or Baked Goods",
                "Main Courses",
                "Side Dishes",
            ],
            CategoryKeys.MAIN_INGREDIENT: [
                "Beans",
                "Beef",
                "Cheese",
                "Chicken",
                "Chocolate",
                "Duck",
                "Eggs",
                "Eggs & Dairy",
                "Fish & Seafood",
                "Fruit",
                "Fruits & Vegetables",
                "Game Birds",
                "Grains",
                "Lamb",
                "Meat",
                "Pasta",
                "Pasta, Grains, Rice & Beans",
                "Pork",
                "Potatoes",
                "Poultry",
                "Rice",
                "Turkey",
                "Vegetables",
            ],
            CategoryKeys.DISH_TYPE: [
                "Beverages",
                "Breads",
                "Breakfast & Brunch",
                "Brownies & Bars",
                "Cakes",
                "Candy",
                "Casseroles",
                "Condiments",
                "Cookies",
                "Dessert Pies",
                "Frozen Desserts",
                "Fruit Desserts",
                "Marinades",
                "Pizza",
                "Puddings, Custards, Gelatins, & Souffles",
                "Quick Breads",
                "Roasts",
                "Rubs",
                "Salads",
                "Sandwiches",
                "Sauces",
                "Savory Pies & Tarts",
                "Snacks",
                "Soups",
                "Stews",
                "Tarts",
            ],
            CategoryKeys.RECIPE_TYPE: [
                "Cast-Iron Skillet",
                "Dairy-Free",
                "For Two",
                "Gluten Free",
                "Grilling & Barbecue",
                "Light",
                "Make Ahead",
                "Pressure Cooker",
                "Quick",
                "Reduced Sugar",
                "Slow Cooker",
                "Vegan",
                "Vegetarian",
                "Weeknight",
            ],
            CategoryKeys.CUISINE: [
                "Africa & Middle-East",
                "African",
                "American",
                "Asia",
                "Asian",
                "California",
                "Caribbean",
                "Central & South American",
                "Chinese",
                "Creole & Cajun",
                "Eastern European & German",
                "Europe",
                "French",
                "Great Britain",
                "Greek",
                "Indian",
                "Indonesian",
                "Irish",
                "Italian",
                "Japanese",
                "Korean",
                "Latin America & Caribbean",
                "Mexican",
                "Mid-Atlantic",
                "Middle Eastern",
                "Midwest",
                "New England",
                "Pacific Northwest",
                "Southern",
                "Southwest (Tex-Mex)",
                "Spanish & Portuguese",
                "Thai",
                "US & Canada",
                "Vietnamese",
            ],
            CategoryKeys.HOLIDAY: [
                "4th of July",
                "Easter",
                "Hanukkah",
                "Holiday",
                "Passover",
                "Super Bowl",
                "Thanksgiving",
                "Valentines Day",
            ],
        }
    )

    md5_chunk_size: int = Field(default=8192)
    gdrive_download_retries: int = Field(default=3)
    valid_book_extensions: tuple[str, ...] = Field(
        default=(
            FileExt.PDF,
            FileExt.EPUB,
            FileExt.MOBI,
        )
    )
    log_config: LogConfig = Field(default_factory=LogConfig)
    json_indent: int = Field(default=2)

    _validated_default_tag_filter_mode: TagFilterMode = PrivateAttr()

    @model_validator(mode="after")
    def assemble_paths_and_essentials(self) -> Self:
        """Assemble full paths and ensure essential files list is complete."""

        if isinstance(self.download_dest_dir, str) and isinstance(
            self.book_dir_relative, str
        ):
            self.book_dir = os.path.join(self.download_dest_dir, self.book_dir_relative)
        else:
            raise ValueError(
                LogMsg.CONFIG_VALIDATION_INVALID_STR.format(field="book_dir")
            )

        if isinstance(self.download_dest_dir, str) and isinstance(
            self.profile_db_path, str
        ):
            self.full_profile_db_path = os.path.join(
                self.download_dest_dir, self.profile_db_path
            )
        else:
            raise ValueError(
                LogMsg.CONFIG_VALIDATION_INVALID_STR.format(
                    field="full_profile_db_path"
                )
            )

        if self.profile_db_path and self.recipe_db_filename:
            profile_db_name = os.path.basename(self.profile_db_path)
            recipe_db_name = self.recipe_db_filename
            essentials = set(self.essential_filenames or [])
            essentials.add(profile_db_name)
            essentials.add(recipe_db_name)
            self.essential_filenames = list(essentials)
        else:
            raise ValueError(
                LogMsg.CONFIG_VALIDATION_MISSING_DEPS.format(
                    field="essential_filenames"
                )
            )

        try:
            self._validated_default_tag_filter_mode = TagFilterMode(
                self.defaults.tag_filter_mode
            )
        except ValueError:
            raise ValueError(
                LogMsg.CONFIG_INVALID_DEFAULT_MODE.format(
                    mode=self.defaults.tag_filter_mode
                )
            )

        return self


CONFIG = AppConfig(**st.secrets)
