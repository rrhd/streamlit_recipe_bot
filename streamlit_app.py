import base64
import gzip
import hashlib
import io
import json
import logging
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from cache_manager import fetch_db_last_updated
from query_top_k import (
    get_db_connection as get_recipe_db_connection,
)
from query_top_k import query_top_k


class LogMsg(StrEnum):
    """Log message templates."""

    SCRIPT_EXEC_FINISHED = "Streamlit script execution finished."
    UNHANDLED_ERROR = "Unhandled error: {error}"
    UNEXPECTED_ERROR = "Unexpected error: {error}"

    CONFIG_VALIDATION_MISSING_DEPS = (
        "Could not assemble {field}: missing dependent fields"
    )
    CONFIG_VALIDATION_INVALID_STR = "Dependent fields for {field} are not valid strings"
    CONFIG_INVALID_DEFAULT_MODE = "Invalid default TagFilterMode: {mode}"
    CONFIG_LOAD_FAIL = "CRITICAL: Failed to load AppConfig: {error}"

    EBOOK_CONVERT_FOUND = "ebook-convert found at: {path}"
    EBOOK_CONVERT_VERSION_SUCCESS = "ebook-convert version check successful: {output}"
    EBOOK_CONVERT_VERSION_FAIL = (
        "ebook-convert found but '--version' check failed: {error}"
    )
    EBOOK_CONVERT_NOT_FOUND = "ebook-convert command not found in system PATH."
    EBOOK_CONVERT_REQ = "Request to ensure PDF format for: {source_path}"
    EBOOK_CONVERT_SRC_NOT_FOUND = (
        "Source file for PDF conversion not found: {source_path}"
    )
    EBOOK_CONVERT_ALREADY_PDF = "File is already PDF."
    EBOOK_CONVERT_FOUND_EXISTING = "Found existing converted PDF: {output_pdf_path}"
    EBOOK_CONVERT_CONVERTING = (
        "Converting '{source_path}' to PDF at '{output_pdf_path}'..."
    )
    EBOOK_CONVERT_SUCCESS = (
        "ebook-convert completed successfully for {source_path}. Output:\n{output}"
    )
    EBOOK_CONVERT_OUTPUT_MISSING = (
        "ebook-convert ran but output file not found: {output_pdf_path}"
    )
    EBOOK_CONVERT_CMD_NOT_FOUND = "`ebook-convert` command not found. Is Calibre installed and in the system PATH?"
    EBOOK_CONVERT_FAILED = (
        "ebook-convert failed for {source_path}. Error: {error}\nStderr:\n{stderr}"
    )
    EBOOK_CONVERT_UNEXPECTED_ERROR = (
        "An unexpected error occurred during PDF conversion for {source_path}"
    )

    GDRIVE_MISSING_SECRET_ACCOUNT = (
        "Missing 'google_service_account' in Streamlit secrets."
    )
    GDRIVE_MISSING_SECRET_FOLDER = (
        "Missing 'google_drive.folder_id' in Streamlit secrets."
    )
    GDRIVE_SERVICE_FAIL = "Failed to build Google Drive service: {error}"
    GDRIVE_SERVICE_UNAVAILABLE = (
        "GDrive service not available, cannot perform operation."
    )
    GDRIVE_FOLDER_ID_MISSING = (
        "GDrive folder ID missing in secrets/config, cannot perform operation."
    )
    GDRIVE_LISTING_FILES = "Listing files from Google Drive to get details..."
    GDRIVE_NO_FILES_FOUND = "No files found in GDrive folder ID '{folder_id}'. Cannot check/download essentials."
    GDRIVE_FOUND_DETAILS = (
        "Found essential file details on Drive: {file_name} (ID: {file_id}, MD5: {md5})"
    )
    GDRIVE_LISTING_DONE = (
        "Finished listing Drive files. Found details for {count} essential file(s)."
    )
    GDRIVE_MISSING_ESSENTIALS = "Could not find the following essential files in the Drive folder: {missing_files}"
    GDRIVE_SKIPPING_NO_ID = "Skipping essential file '{filename}' because its ID is missing from Drive details."
    GDRIVE_WARN_NO_MD5 = "MD5 checksum missing for compressed file '{filename}' on Google Drive. Cannot reliably verify. Will attempt download."
    GDRIVE_DOWNLOAD_NEEDED = (
        "Local compressed file '{filename}' does not exist. Downloading."
    )
    GDRIVE_DOWNLOAD_MD5_MISMATCH = "Local compressed file '{filename}' exists but MD5 checksum differs (Local: {local_md5}, Drive: {drive_md5}). Re-downloading."
    GDRIVE_DOWNLOAD_NO_MD5_VERIFY = "Local compressed file '{filename}' exists, but no Drive MD5 to compare. Re-downloading for safety."
    GDRIVE_LOCAL_VERIFIED_SKIP = (
        "Local file '{filename}' exists and MD5 matches Drive. Skip download."
    )
    GDRIVE_DOWNLOAD_START = (
        "Downloading essential file '{filename}' (ID: {file_id}) to '{path}'..."
    )
    GDRIVE_DOWNLOAD_DONE = "Finished downloading '{filename}'."
    GDRIVE_VERIFY_SUCCESS = (
        "Successfully downloaded and verified '{filename}' (MD5: {md5})."
    )
    GDRIVE_VERIFY_FAIL = "MD5 mismatch after downloading '{filename}'! (Local: {local_md5}, Drive: {drive_md5}). File might be corrupt."
    GDRIVE_REMOVE_MISMATCHED = "Failed to remove mismatched file {path}: {error}"
    GDRIVE_DOWNLOAD_NO_VERIFY = (
        "Downloaded '{filename}' but could not verify MD5 (missing from Drive details)."
    )
    GDRIVE_DOWNLOAD_FAILED = (
        "Download failed for '{filename}' (ID: {file_id}). Error: {error}"
    )
    GDRIVE_REMOVE_INCOMPLETE = "Failed to remove incomplete file {path}: {error}"
    GDRIVE_DECOMPRESS_NEEDED_MISSING = "Decompressed file '{decompressed_filename}' missing. Decompressing '{compressed_filename}'..."
    GDRIVE_DECOMPRESS_NEEDED_OVERWRITE = "Downloaded new version of '{compressed_filename}'. Decompressing to overwrite '{decompressed_filename}'..."
    GDRIVE_MISSING_NON_COMPRESSED = "Essential non-compressed file '{filename}' is missing locally after checks/downloads."
    GDRIVE_DECOMPRESSING = "Decompressing '{gz_path}' to '{final_path}'..."
    GDRIVE_DECOMPRESS_SUCCESS = "Successfully decompressed to '{final_path}'."
    GDRIVE_DECOMPRESS_FAILED = "Failed to decompress {gz_path}: {error}"
    GDRIVE_REMOVE_INCOMPLETE_DECOMPRESS = (
        "Removing potentially incomplete decompressed file: {path}"
    )
    GDRIVE_FAILED_REMOVE_INCOMPLETE_DECOMPRESS = (
        "Failed to remove incomplete decompressed file {path}: {error}"
    )
    GDRIVE_ESSENTIALS_SUMMARY = "Essential files check/download/decompress process completed. Checked: {checked}, Skipped Downloads: {skipped}, Downloads Attempted: {attempted}, Verification Failed: {verify_failed}, Decompressions Needed: {decompress_needed}, Decompressions Failed: {decompress_failed}."
    GDRIVE_LISTING_BOOKS = "Listing books from Google Drive folder ID: {folder_id}"
    GDRIVE_LIST_FOUND_FILE = "GDrive List: Found file '{filename}' (ID: {file_id})"
    GDRIVE_LIST_DUPLICATE_LABEL = "Duplicate book label detected: '{label}'. Skipping file: '{filename}' (ID: {file_id})"
    GDRIVE_LIST_BOOK_COUNT = "Found {count} books in Google Drive."
    GDRIVE_LIST_BOOK_ERROR = (
        "Error listing books from Google Drive folder {folder_id}: {error}"
    )
    GDRIVE_NO_BOOKS_FOUND_LISTING = (
        "No files found in GDrive folder while listing books."
    )
    GDRIVE_ONDEMAND_DOWNLOAD_SKIP = (
        "File '{filename}' already exists locally at '{path}'. Skipping download."
    )
    GDRIVE_ONDEMAND_DOWNLOAD_START = (
        "Downloading on-demand: '{filename}' (ID: {file_id}) to '{path}'..."
    )
    GDRIVE_ONDEMAND_DOWNLOAD_PROGRESS = "Download progress for {filename}: {progress}%"
    GDRIVE_ONDEMAND_DOWNLOAD_DONE = "Finished downloading '{filename}'."
    GDRIVE_ONDEMAND_DOWNLOAD_FAILED = "Failed to download file '{filename}' (ID: {file_id}) from Google Drive: {error}"
    GDRIVE_ONDEMAND_REMOVE_INCOMPLETE = "Removed incomplete download: {path}"
    GDRIVE_ONDEMAND_FAILED_REMOVE = (
        "Failed to remove incomplete download {path}: {error}"
    )

    MD5_FILE_NOT_FOUND = "Cannot calculate MD5, file not found: {filepath}"
    MD5_READ_ERROR = "Error reading file {filepath} for MD5 calculation: {error}"
    MD5_UNEXPECTED_ERROR = "Unexpected error during MD5 calculation for {filepath}"

    PROFILE_DB_CONNECTING = "Connecting to profile database at: {db_path}"
    PROFILE_DB_PATH_INVALID = "Profile DB path is invalid or file missing: {db_path}"
    PROFILE_DB_MISSING_RETRY = (
        "Attempting to re-download essential files as profile DB is missing."
    )
    PROFILE_DB_FOUND_AFTER_RETRY = "Profile DB found after re-download attempt."
    PROFILE_DB_CONNECTION_FAILED = "Failed to connect to profile DB: {error}"
    PROFILE_DB_INIT_SUCCESS = "Profile database initialized successfully."
    PROFILE_DB_INIT_FAIL = "Failed to initialize profile database: {error}"
    PROFILE_DB_INIT_FAIL_NO_CONN = (
        "Failed to initialize profile database (no connection)."
    )
    PROFILE_DB_SAVE_ATTEMPT = (
        "Attempting to save profile for user='{username}' at timestamp='{timestamp}'"
    )
    PROFILE_DB_SAVE_SUCCESS = "Profile for user='{username}' saved successfully."
    PROFILE_DB_SAVE_FAIL = "Failed to save profile for user '{username}': {error}"
    PROFILE_DB_CONN_UNAVAILABLE_SAVE = "Profile DB connection not available for saving."
    PROFILE_DB_LOAD_ATTEMPT = (
        "Attempting to load most recent profile for user='{username}'"
    )
    PROFILE_DB_LOAD_NOT_FOUND = "No profile found for user='{username}'."
    PROFILE_DB_LOAD_SUCCESS = (
        "Profile loaded successfully for user='{username}' (timestamp: {timestamp})."
    )
    PROFILE_DB_LOAD_DECODE_FAIL = "Failed to decode profile data for user='{username}', timestamp='{timestamp}'. Error: {error}"
    PROFILE_DB_CONN_UNAVAILABLE_LOAD = (
        "Profile DB connection not available for loading."
    )
    PROFILE_DB_QUERY_FAILED = "Profile DB query failed: {error}"
    RECIPE_DB_CONN_FAIL = "Recipe DB connection failed in {function_name}."
    RECIPE_DB_QUERY_SOURCES_FAILED = "Failed to query sources from recipe DB: {error}"
    SOURCES_FETCHING = "Fetching sources from recipe DB (DB timestamp: {db_timestamp})"
    SOURCES_FETCHED_COUNT = "Fetched {count} distinct sources."
    SOURCES_FETCH_INIT_FAIL = "Failed to fetch initial source data."
    SOURCES_FETCH_UNEXPECTED_ERROR = "Unexpected error fetching sources: {error}"
    SOURCES_REFRESH_DB_TIME_FAIL = (
        "Could not determine recipe database update time. Refresh failed."
    )
    SOURCES_REFRESH_FAIL = "Failed to refresh sources: {error}"
    SOURCES_REFRESHED = "Sources refreshed and session state updated."

    RECIPE_INVALID_DATA_TYPE = "Recipe data is not a dictionary: {type}"
    RECIPE_CONTENT_NOT_DICT = (
        "Recipe content for title '{title}' is not a dictionary, type: {type}."
    )
    RECIPE_INVALID_INGREDIENT = (
        "Skipping non-dictionary item in ingredients list: {item}"
    )
    RECIPE_INGREDIENTS_NOT_LIST = "Ingredients data is not a list: {type}"
    RECIPE_SECTION_CONTENT_INVALID = (
        "Recipe section content for '{key}' is not a string, type: {type}."
    )
    RECIPE_INVALID_INSTRUCTION = (
        "Skipping non-dictionary item in instructions list: {item}"
    )
    RECIPE_INSTRUCTIONS_NOT_LIST = "Instructions data is not a list: {type}"
    RECIPE_INSTRUCTIONS_SORT_FAIL = "Failed to sort instructions: {error}"
    RECIPE_URL_NOT_STRING = "URL data is not a string: {type}"
    RECIPE_CONTENT_MISSING = (
        "Content for selected recipe label '{label}' is missing or invalid."
    )
    RECIPE_LABEL_NOT_FOUND_IN_OPTIONS = (
        "Selected recipe label '{label}' not found in options, defaulting index."
    )

    ADV_SEARCH_CLICKED = "Advanced search button clicked."
    ADV_SEARCH_PARAMS = "Calling query_top_k with params: {params_json}"
    ADV_SEARCH_QUERY_ERROR = "Error calling query_top_k function."
    ADV_SEARCH_NO_RESULTS = "query_top_k returned no results."
    ADV_SEARCH_RESULTS_COUNT = "query_top_k returned {count} results."
    ADV_SEARCH_PROCESSED = (
        "Processed results. HTML length: {html_len}, Mapping keys: {map_keys}"
    )
    SIMPLE_SEARCH_CLICKED = "Simple search button clicked."
    SIMPLE_SEARCH_PARAMS = (
        "Calling query_top_k for simple search with params: {params_json}"
    )
    SIMPLE_SEARCH_QUERY_ERROR = "Error calling query_top_k for simple search."
    SIMPLE_SEARCH_NO_RESULTS = "Simple search returned no results."
    SIMPLE_SEARCH_RESULTS_COUNT = "Simple search returned {count} results."
    SIMPLE_SEARCH_PROCESSED = "Processed simple search results. HTML length: {html_len}"
    SERIALIZE_PARAMS_FAIL = "<Could not serialize query params>"

    PROFILE_SAVE_CLICKED = "Save profile button clicked."
    PROFILE_ENCODE_FAIL = "Failed to encode profile data: {error}"
    PROFILE_SAVE_ACTION_FAIL = "Failed to save profile via UI action: {error}"
    PROFILE_LOAD_CLICKED = "Load profile button clicked."
    PROFILE_LOADED_RERUN = "Profile loaded for {username}, triggering rerun."
    PROFILE_INVALID_MODE_LOADED = (
        "Invalid TagFilterMode '{mode}' in loaded profile, using default."
    )
    PROFILE_LOAD_ACTION_FAIL = "Failed to load profile via UI action: {error}"

    SOURCES_REFRESH_CLICKED = "Refresh sources button clicked."
    SOURCES_SELECT_ALL_CLICKED = "Select all sources button clicked."
    SOURCES_SET_ALL = "Selected sources set to all {count} available sources in state."

    LIBRARY_REFRESH_CLICKED = "Refresh book list button clicked."
    LIBRARY_LIST_REFRESHED = "Book list refreshed from Drive."
    LIBRARY_LIST_REFRESH_FAIL = "Failed to refresh book list from Drive: {error}"
    LIBRARY_PREPARING_BOOK = "Preparing '{label}'..."
    LIBRARY_PROCESSING_BOOK = "Processing '{filename}'... Please wait."
    LIBRARY_DETAILS_NOT_FOUND = "Details not found for selected book: {label}"
    LIBRARY_MISSING_DETAILS = "Missing critical book details (ID, name, or local path)."
    LIBRARY_ENCODING_PDF = "Reading and encoding PDF for new tab link: {pdf_path}"
    LIBRARY_LINK_GENERATED = "Link generated for book: {label}"
    LIBRARY_PDF_CONVERT_ERROR = "PDF Conversion/Link Prep Error: File not found at '{path}' for book '{label}': {error}"
    LIBRARY_CONVERT_LINK_FAIL = (
        "Error converting or preparing link for book '{label}': {error}"
    )
    LIBRARY_DOWNLOAD_FIND_FAIL = "Failed to download or find local file for '{label}'"
    LIBRARY_BOOK_SELECTION_INVALID = (
        "Book selection '{selection}' not in options, defaulting index."
    )
    LIBRARY_UNSUPPORTED_TYPE = "Unsupported file type for PDF conversion: {path}"
    LIBRARY_SELECTION_RESET = (
        "Reset library selection as '{selection}' is no longer valid."
    )

    RECIPE_SELECTION_CHANGED = (
        "Recipe selection changed via dropdown callback to: {selection}"
    )

    LOG_FORMATTING_ERROR = "Log formatting error for template '{template}'. Missing key: {key}. Raw kwargs: {kwargs}"
    LOG_MISSING_FORMAT_KEY = "Missing key '{key}' in kwargs for log message: {template}"


class FileExt(StrEnum):
    """File extensions."""

    GZ = ".gz"
    PDF = ".pdf"
    EPUB = ".epub"
    MOBI = ".mobi"
    DB = ".db"
    SQLITE = ".sqlite"
    TXT = ".txt"


class FileMode(StrEnum):
    """File open modes."""

    READ_BINARY = "rb"
    WRITE_BINARY = "wb"


class ConfigKeys(StrEnum):
    """Keys for configuration values stored directly."""

    PROFILE_DB_PATH = "profiles_db.sqlite"
    BOOK_DIR_RELATIVE = "cookbooks"
    DOWNLOAD_DEST_DIR = "data"
    RECIPE_DB_FILENAME = "recipe_links.db.gz"


class DefaultKeys(StrEnum):
    """Keys for Pydantic default values."""

    INGREDIENTS_TEXT = "ingredients_text"
    MUST_USE_TEXT = "must_use_text"
    EXCLUDED_TEXT = "excluded_text"
    KEYWORDS_INCLUDE = "keywords_include"
    KEYWORDS_EXCLUDE = "keywords_exclude"
    MIN_ING_MATCHES = "min_ing_matches"
    MAX_STEPS = "max_steps"
    USER_COVERAGE = "user_coverage"
    RECIPE_COVERAGE = "recipe_coverage"
    TAG_FILTER_MODE = "tag_filter_mode"
    USERNAME = "username"
    SIMPLE_QUERY = "simple_query"
    PROFILE_MESSAGE = "profile_message"
    NO_RECIPES_FOUND = "no_recipes_found"
    LOADING_MESSAGE = "loading_message"


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


class SessionStateKeys(StrEnum):
    """Keys for storing data in Streamlit's session state."""

    SIMPLE_SEARCH_RESULTS_HTML = "simple_search_results_html"
    SIMPLE_SEARCH_MAPPING = "simple_search_mapping"
    SIMPLE_SEARCH_RESULTS_DF = "simple_search_results_df"
    SIMPLE_SELECTED_RECIPE_LABEL = "simple_selected_recipe_label"

    ADVANCED_SEARCH_RESULTS_HTML = "adv_search_results_html"
    ADVANCED_SEARCH_MAPPING = "adv_search_mapping"
    ADVANCED_SELECTED_RECIPE_LABEL = "adv_selected_recipe_label"
    ADVANCED_SEARCH_RESULTS_DF = "adv_search_results_df"

    SELECTED_PAGE = "selected_page"
    LOADED_INGREDIENTS_TEXT = "loaded_ingredients_text"
    LOADED_EXCLUDED_TEXT = "loaded_excluded_text"
    LOADED_KEYWORDS_INCLUDE = "loaded_keywords_include"
    LOADED_KEYWORDS_EXCLUDE = "loaded_keywords_exclude"
    LOADED_MIN_ING_MATCHES = "loaded_min_ing_matches"
    LOADED_COURSE_FILTER = "loaded_course_filter"
    LOADED_MAIN_ING_FILTER = "loaded_main_ing_filter"
    LOADED_DISH_TYPE_FILTER = "loaded_dish_type_filter"
    LOADED_RECIPE_TYPE_FILTER = "loaded_recipe_type_filter"
    LOADED_CUISINE_FILTER = "loaded_cuisine_filter"
    LOADED_EXCLUDE_COURSE_FILTER = "loaded_exclude_course_filter"
    LOADED_EXCLUDE_MAIN_ING_FILTER = "loaded_exclude_main_ing_filter"
    LOADED_EXCLUDE_DISH_TYPE_FILTER = "loaded_exclude_dish_type_filter"
    LOADED_EXCLUDE_RECIPE_TYPE_FILTER = "loaded_exclude_recipe_type_filter"
    LOADED_EXCLUDE_CUISINE_FILTER = "loaded_exclude_cuisine_filter"
    LOADED_TAG_FILTER_MODE = "loaded_tag_filter_mode"
    LOADED_MAX_STEPS = "loaded_max_steps"
    LOADED_USER_COVERAGE = "loaded_user_coverage"
    LOADED_RECIPE_COVERAGE = "loaded_recipe_coverage"
    LOADED_SOURCES = "loaded_sources"
    LOADED_MUST_USE_TEXT = "loaded_must_use_text"

    USERNAME_INPUT = "widget_username"
    ADV_INGREDIENTS_INPUT = "widget_adv_ingredients"
    ADV_MUST_USE_INPUT = "widget_adv_must_use"
    ADV_EXCLUDED_INPUT = "widget_adv_excluded"
    ADV_MIN_ING_MATCHES_INPUT = "widget_adv_min_ing_matches"
    ADV_KEYWORDS_INCLUDE_INPUT = "widget_adv_keywords_include"
    ADV_KEYWORDS_EXCLUDE_INPUT = "widget_adv_keywords_exclude"
    ADV_COURSE_FILTER_INPUT = "widget_adv_course_filter"
    ADV_MAIN_ING_FILTER_INPUT = "widget_adv_main_ing_filter"
    ADV_DISH_TYPE_FILTER_INPUT = "widget_adv_dish_type_filter"
    ADV_RECIPE_TYPE_FILTER_INPUT = "widget_adv_recipe_type_filter"
    ADV_CUISINE_FILTER_INPUT = "widget_adv_cuisine_filter"
    ADV_EXCLUDE_COURSE_FILTER_INPUT = "widget_adv_exclude_course_filter"
    ADV_EXCLUDE_MAIN_ING_FILTER_INPUT = "widget_adv_exclude_main_ing_filter"
    ADV_EXCLUDE_DISH_TYPE_FILTER_INPUT = "widget_adv_exclude_dish_type_filter"
    ADV_EXCLUDE_RECIPE_TYPE_FILTER_INPUT = "widget_adv_exclude_recipe_type_filter"
    ADV_EXCLUDE_CUISINE_FILTER_INPUT = "widget_adv_exclude_cuisine_filter"
    ADV_TAG_FILTER_MODE_INPUT = "widget_adv_tag_filter_mode"
    ADV_MAX_STEPS_INPUT = "widget_adv_max_steps"
    ADV_USER_COVERAGE_SLIDER = "widget_adv_user_coverage"
    ADV_RECIPE_COVERAGE_SLIDER = "widget_adv_recipe_coverage"
    ADV_SOURCE_SELECTOR = "widget_adv_source_selector"
    RECIPE_SELECTOR_DROPDOWN = "widget_recipe_selector"
    SIMPLE_QUERY_INPUT = "widget_simple_query"
    LIBRARY_BOOK_SELECTOR = "widget_library_book_selector"

    ALL_SOURCES_LIST = "all_sources_list"
    LIBRARY_BOOK_MAPPING = "library_book_mapping"
    PROFILE_STATUS_MESSAGE = "profile_status_message"


class TagFilterMode(StrEnum):
    AND = "AND"
    OR = "OR"


class CategoryKeys(StrEnum):
    COURSE = "course"
    MAIN_INGREDIENT = "main_ingredient"
    DISH_TYPE = "dish_type"
    RECIPE_TYPE = "recipe_type"
    CUISINE = "cuisine"
    HOLIDAY = "holiday"


class GDriveKeys(StrEnum):
    """Keys related to Google Drive API and secrets."""

    FOLDER_ID = "folder_id"
    SECRET_ACCOUNT = "google_service_account"
    SECRET_DRIVE = "google_drive"
    API_SERVICE = "drive"
    API_VERSION = "v3"
    QUERY_FOLDER_FILES = "'{folder_id}' in parents and trashed=false"
    FIELDS_FILE_LIST = "nextPageToken, files(id, name, md5Checksum)"
    FIELDS_FILE_LIST_NO_MD5 = "nextPageToken, files(id, name)"
    NEXT_PAGE_TOKEN = "nextPageToken"
    FILES = "files"
    FILE_NAME = "name"
    FILE_ID = "id"
    FILE_MD5 = "md5Checksum"


class DbKeys(StrEnum):
    """Keys related to database operations."""

    TABLE_USER_PROFILES = "user_profiles"
    COL_ID = "id"
    COL_USERNAME = "username"
    COL_TIMESTAMP = "timestamp"
    COL_PAYLOAD = "payload_base64"
    SQL_CREATE_PROFILES = """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload_base64 TEXT NOT NULL
        )
        """
    SQL_INSERT_PROFILE = """
        INSERT INTO user_profiles (username, timestamp, payload_base64)
        VALUES (?, ?, ?)
        """
    SQL_SELECT_PROFILE = """
        SELECT payload_base64, timestamp
        FROM user_profiles
        WHERE username=?
        ORDER BY timestamp DESC
        LIMIT 1
        """

    TABLE_RECIPE_SCHEMA = "recipe_schema"
    COL_SOURCE_DOMAIN = "source_domain"
    SQL_SELECT_SOURCES = """
        SELECT DISTINCT source_domain
        FROM recipe_schema
        WHERE source_domain IS NOT NULL
        ORDER BY source_domain
    """


class ProfileDataKeys(StrEnum):
    """Keys used *within* the saved profile JSON payload."""

    TIMESTAMP = "timestamp"
    OPTIONS = "options"
    INGREDIENTS_TEXT = "ingredients_text"
    MUST_USE_TEXT = "must_use_text"
    EXCLUDED_BOX = "excluded_box"
    KEYWORDS_INCLUDE = "keywords_include"
    KEYWORDS_EXCLUDE = "keywords_exclude"
    MIN_ING_MATCHES = "min_ing_matches"
    COURSE_FILTER = "course_filter"
    MAIN_ING_FILTER = "main_ing_filter"
    DISH_TYPE_FILTER = "dish_type_filter"
    RECIPE_TYPE_FILTER = "recipe_type_filter"
    CUISINE_FILTER = "cuisine_filter"
    EXCLUDE_COURSE_FILTER = "exclude_course_filter"
    EXCLUDE_MAIN_ING_FILTER = "exclude_main_ing_filter"
    EXCLUDE_DISH_TYPE_FILTER = "exclude_dish_type_filter"
    EXCLUDE_RECIPE_TYPE_FILTER = "exclude_recipe_type_filter"
    EXCLUDE_CUISINE_FILTER = "exclude_cuisine_filter"
    TAG_FILTER_MODE = "tag_filter_mode"
    MAX_STEPS = "max_steps"
    USER_COVERAGE_SLIDER = "user_coverage_slider"
    RECIPE_COVERAGE_SLIDER = "recipe_coverage_slider"
    SOURCES = "sources"


class RecipeKeys(StrEnum):
    """Keys within recipe data dictionaries (from DB/API)."""

    TITLE = "title"
    DESCRIPTION = "description"
    SIMPLIFIED_DATA = "simplified_data"
    COOK_TIME = "cook_time"
    YIELD = "yield"
    YIELDS = "yields"
    WHY_THIS_WORKS = "why_this_works"
    HEADNOTE = "headnote"
    EQUIPMENT = "equipment"
    INGREDIENTS = "ingredients"
    QUANTITY = "quantity"
    MEASUREMENT = "measurement"
    INGREDIENT = "ingredient"
    DETAIL = "detail"
    INSTRUCTIONS = "instructions"
    STEP = "step"
    INSTRUCTION = "instruction"
    URL = "url"
    RECIPE = "recipe"
    USER_COVERAGE = "user_coverage"
    RECIPE_COVERAGE = "recipe_coverage"


class FormatStrings(StrEnum):
    """String templates for formatting."""

    TIMESTAMP_ISO_SECONDS = "seconds"
    TIMESTAMP_CACHE_KEY = "%Y%m%d%H%M%S"
    ENCODING_UTF8 = "utf-8"
    ENCODING_ERRORS_REPLACE = "replace"
    SLIDER_PERCENT = "%.0f%%"
    RECIPE_LABEL = "{coverage:.3f} - {title}"
    RECIPE_LABEL_DUPLICATE = "{original_label} ({count})"
    PDF_DATA_URI = "data:application/pdf;base64,{base64_pdf}"
    BYTES_UNDECODABLE = "<Bytes length={length}, undecodable>"
    TRUNCATION_SUFFIX = "..."


class UiText(StrEnum):
    """Static UI text elements like labels, titles, messages."""

    PREPARING_BOOK = "Preparing '{label}'…"
    SPINNER_LOADING_PDF = "Loading PDF..."
    BUTTON_OPEN_BOOK_PDF = "Open Book PDF"
    PAGE_TITLE = "Recipe Finder"
    TAB_ABOUT = "About"
    TAB_ADVANCED = "Advanced Search"
    TAB_SIMPLE = "Simple Search"
    TAB_LIBRARY = "Library"
    SIDEBAR_PAGE_SELECT = "Select Page"
    ABOUT_MARKDOWN = """
        # Recipe Finder

        **How to Use:**

        - **Ingredients (one per line):**
          Enter your available ingredients. These are used to search for recipes that contain any of these ingredients.

        - **Must Use Ingredients (one per line):**
          Enter ingredients that must appear in the recipe (or a similar match). For example, entering "onion" will require recipes to include an ingredient like "chopped onion."

        - **Ingredients to Exclude:**
          Specify ingredients you want to exclude from the recipes.

        - **Keywords to Include/Exclude:**
          These keywords filter the recipe title or description. For instance, you might include "celery marinade" or exclude "dutch oven."

        - **Minimum Ingredient Matches:**
          Set the minimum number of ingredient matches required between your ingredients and the recipe. Set to 0 to ignore ingredient matching and rely only on keywords/tags.

        - **Tag Filters (Course, Main Ingredient, Dish Type, Recipe Type, Cuisine):**
          Select one or more tags to include or exclude to narrow down the search.

        - **Tag Filter Mode:**
          Choose "AND" to require all selected include tag filters to match, or "OR" to allow any match. Exclusion filters are always applied with AND logic (must not have *any* of the excluded tags in the relevant category).

        - **Maximum Steps:**
          Limit recipes by the number of steps in the instructions (set to 0 for no limit).

        - **User/Recipe Coverage Sliders:**
          Adjust the percentage of ingredients (from your list and the recipe's list) that must match for the recipe to be considered. Set to 0% to disable coverage requirements.

        - **Sources:**
          Select the sources (websites, cookbooks) to include in the search.

        - **Profile Functions:**
          Save and load your query settings under a profile username for quick reuse. Loading retrieves the most recent profile for that user.

        - **Simple Search Tab:**
          Enter a query (e.g. "rice onion") to perform a keyword search over the recipe title and description. Results are sorted by relevance (if supported by backend) or title.

        Click **Search Recipes** (or **Simple Search** on the respective tab) to see the matching recipes. Then, select a recipe from the dropdown below the results table to view its details.

        - **Library Tab:**
          Browse cookbooks downloaded from Google Drive. Requires `ebook-convert` (from Calibre) to be installed and in the PATH for non-PDF files.
        """

    HEADER_ADVANCED_SEARCH = "Advanced Recipe Search"
    SUBHEADER_INPUTS_FILTERS = "Inputs & Filters"
    SUBHEADER_RESULTS = "Results"
    LABEL_INGREDIENTS = "Ingredients (one per line)"
    PLACEHOLDER_INGREDIENTS = "e.g.\nchicken\nonion\ngarlic"
    LABEL_MIN_MATCHES = "Minimum Ingredient Matches"
    HELP_MIN_MATCHES = "Minimum number of your ingredients that must be found in the recipe. 0 to disable."
    LABEL_MAX_STEPS = "Maximum Steps (0 = no limit)"
    EXPANDER_ADV_OPTIONS = "Advanced Ingredient & Keyword Options"
    LABEL_MUST_USE = "Must Use Ingredients (one per line)"
    PLACEHOLDER_MUST_USE = "e.g.\ncelery\nmushrooms"
    LABEL_EXCLUDE_INGS = "Ingredients to Exclude (one per line)"
    PLACEHOLDER_EXCLUDE_INGS = "e.g.\nnuts\nsoy"
    LABEL_KEYWORDS_INCLUDE = (
        "Keywords to Include (in Title/Description, space-separated)"
    )
    PLACEHOLDER_KEYWORDS_INCLUDE = "e.g. quick easy bake"
    LABEL_KEYWORDS_EXCLUDE = (
        "Keywords to Exclude (in Title/Description, space-separated)"
    )
    PLACEHOLDER_KEYWORDS_EXCLUDE = "e.g. slow cooker grill"
    EXPANDER_TAG_FILTERS = "Tag Filters"
    LABEL_TAG_FILTER_MODE = "Tag Filter Mode (for Includes)"
    LABEL_INCLUDE_TAGS = "**Include Recipes With Tags:**"
    LABEL_EXCLUDE_TAGS = "**Exclude Recipes With Tags:**"
    LABEL_USER_COVERAGE = "Min % User Ingredients Required"
    HELP_USER_COVERAGE = (
        "Percentage of your ingredients list that must be present in the recipe."
    )
    LABEL_RECIPE_COVERAGE = "Min % Recipe Ingredients Required"
    HELP_RECIPE_COVERAGE = (
        "Percentage of the recipe's ingredients that must be present in your list."
    )
    EXPANDER_SOURCE_SELECT = "Source Selection"
    LABEL_SELECT_SOURCES = "Select Sources"
    BUTTON_REFRESH_SOURCES = "Refresh Sources List"
    BUTTON_SELECT_ALL_SOURCES = "Select All Sources"
    EXPANDER_USER_PROFILES = "User Profiles"
    LABEL_USERNAME = "Username"
    BUTTON_SAVE_PROFILE = "Save Current Settings"
    BUTTON_LOAD_PROFILE = "Load Most Recent Profile"
    BUTTON_SEARCH_RECIPES = "Search Recipes"
    MARKDOWN_MATCHING_RECIPES = "##### Matching Recipes Table"
    MARKDOWN_SELECT_RECIPE = "##### Select Recipe for Details"
    MARKDOWN_RECIPE_DETAILS = "##### Recipe Details"
    SELECTBOX_LABEL_RECIPE = "Select a Recipe"
    PROFILE_MSG_USERNAME_NEEDED_SAVE = (
        "<p style='color:orange;'>Please provide a username to save the profile.</p>"
    )
    PROFILE_MSG_USERNAME_NEEDED_LOAD = (
        "<p style='color:orange;'>Please provide a username to load a profile.</p>"
    )
    PROFILE_MSG_SAVE_SUCCESS = "<p style='color:green;'>Profile '{username}' saved successfully at {timestamp}.</p>"
    PROFILE_MSG_LOAD_SUCCESS = "<p style='color:green;'>Profile for '{username}' loaded (from {timestamp}).</p>"
    PROFILE_MSG_LOAD_NOT_FOUND = (
        "<p style='color:orange;'>No profile found for username '{username}'.</p>"
    )
    PROFILE_MSG_ENCODE_ERROR = (
        "<p style='color:red;'>Error encoding profile data: {error}</p>"
    )
    PROFILE_MSG_SAVE_ERROR = "<p style='color:red;'>Error saving profile: {error}</p>"
    PROFILE_MSG_LOAD_ERROR = "<p style='color:red;'>Error loading profile: {error}</p>"
    MSG_SELECT_RECIPE_PROMPT = (
        "<p>Select a recipe from the dropdown above to see details.</p>"
    )
    MSG_NO_RESULTS_FOUND_ADV = "<p>No recipes found matching your search criteria.</p>"
    MSG_COULD_NOT_DISPLAY = (
        "Could not display details for '{label}'. Data might be missing."
    )
    ERROR_DURING_SEARCH = "<p style='color:red;'>Error during search: {error}</p>"

    HEADER_SIMPLE_SEARCH = "Simple Keyword Search"
    LABEL_SIMPLE_QUERY = "Search Query (Keywords for Title/Description)"
    PLACEHOLDER_SIMPLE_QUERY = "e.g. easy chicken stir fry"
    BUTTON_SIMPLE_SEARCH = "Simple Search"
    MARKDOWN_SIMPLE_RESULTS = "### Simple Search Results"
    WARN_EMPTY_QUERY = "Please enter a search query."
    MSG_SIMPLE_QUERY_PROMPT = "<p>Enter a query above.</p>"
    MSG_SIMPLE_NO_RESULTS = "<p>No results found for query: '{query_text}'</p>"
    ERROR_DURING_SIMPLE_SEARCH = (
        "<p style='color:red;'>Error during simple search: {error}</p>"
    )

    HEADER_LIBRARY = "Cookbook Library"
    WARN_EBOOK_CONVERT_MISSING = (
        "**`ebook-convert` (from Calibre) was not found.** "
        "Non-PDF books cannot be converted. Please install Calibre and ensure "
        "it's in your system PATH, or add `calibre` to `.streamlit/packages.txt` "
        "if deploying to Streamlit Community Cloud."
    )
    WARN_NO_BOOKS_FOUND = "No books found in the configured Google Drive folder."
    SELECTBOX_LABEL_BOOK = "Choose a book"
    BUTTON_REFRESH_BOOKS = "Refresh Book List"
    ERROR_BOOK_DETAILS_NOT_FOUND = "Details not found for selected book: {label}"
    ERROR_BOOK_MISSING_DETAILS = (
        "Missing critical book details (ID, name, or local path)."
    )
    ERROR_BOOK_CONVERT_LINK = (
        "Could not convert or prepare link for book '{label}'. Error: {error}"
    )
    ERROR_BOOK_FILE_NOT_FOUND = (
        "Error: Could not find the file '{filename}' for processing."
    )
    ERROR_BOOK_DOWNLOAD_FAIL = "Failed to download or find local file for '{label}'"
    LINK_OPEN_BOOK_HTML = (
        '<a href="{data_uri}" target="_blank" '
        'style="font-size: 1.2em; padding: 10px; border: 1px solid #ccc; border-radius: 5px; text-decoration: none;">'
        "📖 Open '{label}' in New Tab"
        "</a><br><br><small>(Clicking should open in a new tab using your browser's PDF viewer. Behavior depends on browser settings and PDF size; some browsers may still force a download.)</small>"
    )

    FATAL_CONFIG_LOAD_FAIL = (
        "FATAL: Application configuration failed to load: {error}. Cannot continue."
    )
    ERROR_SOURCES_LOAD_FAIL = "Error fetching initial source data: {error}"
    ERROR_SOURCES_DISPLAY = "Error: Could not load sources"
    ERROR_BOOKS_LOAD_FAIL = "Error listing books from Drive: {error}"
    ERROR_BOOKS_DISPLAY = "Error: Could not list books"
    ERROR_PROFILE_DB_PATH_MISSING = "Profile DB path not configured."
    ERROR_PROFILE_DB_CONNECT_FAILED = (
        "Database Error: Could not connect to profile DB: {error}"
    )
    ERROR_PROFILE_DB_INIT = "Database Error: Could not initialize profile DB: {error}"
    ERROR_PROFILE_DECODE = "Error decoding profile data for user {username}. The stored data might be corrupted."
    ERROR_GDRIVE_NO_FILES = "No files found in the configured Google Drive folder. Essential files ({files}) cannot be obtained."
    ERROR_GDRIVE_VERIFY_FAIL = "Verification failed after downloading {filename}. Please try restarting the app."
    ERROR_GDRIVE_DOWNLOAD_FAIL_UI = "Failed to download {filename}: {error}"
    ERROR_GDRIVE_DECOMPRESS_FAIL = (
        "Failed to decompress essential file {filename}: {error}"
    )
    ERROR_GDRIVE_ESSENTIAL_MISSING = "Essential files missing in Drive folder: {files}. App might not function correctly."
    ERROR_GDRIVE_UNEXPECTED = (
        "An unexpected error occurred while processing essential files: {error}"
    )
    ERROR_GDRIVE_CONNECTION_FAILED = "Google Drive connection failed."
    ERROR_RECIPE_DB_CONNECT_FAILED_SOURCES = (
        "Could not connect to recipe database to fetch sources."
    )
    ERROR_RECIPE_DB_QUERY_FAILED_SOURCES = "Error querying recipe sources: {error}"
    ERROR_UNEXPECTED_FETCH_SOURCES = "Unexpected error fetching sources: {error}"
    ERROR_EBOOK_CONVERT_MISSING_RUNTIME = "`ebook-convert` not found. Please install Calibre and ensure it's in the system PATH to view non-PDF books."
    ERROR_EBOOK_CONVERT_FAIL_RUNTIME = (
        "Failed to convert book '{filename}' to PDF. Error: {stderr}"
    )
    ERROR_EBOOK_CONVERT_UNEXPECTED_RUNTIME = (
        "An unexpected error occurred converting book: {error}"
    )
    ERROR_PROFILE_DB_CONN_MISSING_LOAD = "Profile database connection error."
    ERROR_PROFILE_DB_CONN_MISSING_SAVE = (
        "Profile DB connection not available for saving."
    )
    ERROR_PROFILE_DB_QUERY_FAILED_LOAD = "Database error loading profile: {error}"
    ERROR_CRITICAL_FILE_MISSING = "Critical file {filename} missing. App may fail."

    DEFAULT_RECIPE_TITLE = "No Title Provided"
    DEFAULT_RECIPE_URL = "N/A"
    DEFAULT_TIMESTAMP = "N/A"
    INVALID_INGREDIENT_FORMAT = "Invalid ingredient format"
    INVALID_INSTRUCTION_FORMAT = "Invalid instruction format"
    WARNING_INSTRUCTION_SORT_FAIL = "Warning: Could not sort instructions numerically."
    SPINNER_DOWNLOADING = "Downloading {filename}..."
    SPINNER_DECOMPRESSING = "Decompressing {filename}..."
    SPINNER_DOWNLOADING_ON_DEMAND = "Downloading {filename}..."
    SPINNER_PREPARING_BOOK = "Preparing '{label}'..."
    SPINNER_PROCESSING_BOOK = "Processing '{filename}'... Please wait."
    SPINNER_CONVERTING_PDF = "Converting {filename} to PDF..."


class HtmlClasses(StrEnum):
    """CSS classes used in generated HTML."""

    RECIPE_CONTAINER = "recipe-container"
    RECIPE_TITLE = "recipe-title"
    RECIPE_SECTION = "recipe-section"
    RECIPE_INGREDIENTS = "recipe-ingredients"
    RECIPE_INSTRUCTIONS = "recipe-instructions"
    RECIPE_SOURCE = "recipe-source"


class HtmlTags(StrEnum):
    """HTML tags."""

    H2 = "h2"
    H3 = "h3"
    P = "p"
    UL = "ul"
    OL = "ol"
    LI = "li"
    DIV = "div"
    A = "a"
    STRONG = "strong"
    TABLE = "table"
    THEAD = "thead"
    TBODY = "tbody"
    TR = "tr"
    TH = "th"
    TD = "td"
    STYLE = "style"
    SMALL = "small"
    BR = "br"


class HtmlStyle(StrEnum):
    """Inline styles or style block content."""

    RECIPE_STYLE_BLOCK = """
    <style>
      .recipe-container {
          font-family: 'Arial', sans-serif;
          line-height: 1.6;
          padding: 20px;
          max-width: 800px;
          margin: auto;
          background-color: #fdfdfd; /* Light mode background */
          color: #333; /* Light mode text */
          border: 1px solid #ddd;
          border-radius: 5px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }
      .recipe-title {
          font-size: 2em;
          margin-bottom: 0.5em;
          color: inherit; /* Inherit color from container */
      }
      .recipe-section {
          margin-bottom: 1em;
      }
      .recipe-section h3 {
          margin: 0 0 0.5em 0;
          padding-bottom: 5px;
          border-bottom: 1px solid #ccc; /* Light mode border */
          color: inherit; /* Inherit color */
      }
      .recipe-ingredients li,
      .recipe-instructions li {
          margin-bottom: 5px;
      }
      .recipe-source a {
          color: #1a73e8; /* Light mode link */
          text-decoration: none;
      }
      .recipe-source a:hover {
          text-decoration: underline;
      }
      /* Basic Dark Mode Adaptation (Streamlit handles theme switching) */
      body.dark-mode .recipe-container { /* Example selector, adjust if needed */
          background-color: #222;
          color: #eee;
          border: 1px solid #444;
          box-shadow: 0 2px 4px rgba(0,0,0,0.5);
      }
       body.dark-mode .recipe-section h3 {
           border-bottom: 1px solid #555;
       }
       body.dark-mode .recipe-source a {
           color: #9ecfff; /* Dark mode link */
       }
    </style>
    """
    RESULTS_TABLE_STYLE = (
        "border-collapse: collapse; width: 100%; border: 1px solid #ccc;"
    )
    RESULTS_HEADER_STYLE = "background-color: #f0f0f0;"
    RESULTS_CELL_STYLE = "padding: 5px; border: 1px solid #ccc;"  # Reduced padding
    RESULTS_HEADER_CELL_STYLE = (
        "padding: 8px; border: 1px solid #ccc; text-align: left;"
    )


class ToolNames(StrEnum):
    """Executable tool names."""

    EBOOK_CONVERT = "ebook-convert"


class MiscValues(StrEnum):
    """Miscellaneous constant values."""

    TEMP_DIR = tempfile.gettempdir()
    NEWLINE = "\n"
    SPACE = " "
    EMPTY = ""
    HTTP_PREFIX = "http://"
    HTTPS_PREFIX = "https://"
    DEFAULT_NA = "N/A"
    DEFAULT_STEP = "?"


class LogPayloadKeys(StrEnum):
    """Keys for structured logging payloads."""

    FILE_PATH = "file_path"
    GDRIVE_ID = "gdrive_id"
    GDRIVE_FOLDER = "gdrive_folder"
    USERNAME = "username"
    TIMESTAMP = "timestamp"
    QUERY_PARAMS = "query_params"
    ERROR_MESSAGE = "error_message"
    STACK_TRACE = "stack_trace"
    SOURCE_COUNT = "source_count"
    BOOK_COUNT = "book_count"
    RESULT_COUNT = "result_count"
    MD5_HASH = "md5_hash"
    LABEL = "label"
    FUNCTION_NAME = "function_name"
    LOG_FORMATTING_ERROR = "_log_formatting_error"
    ORIGINAL_KWARGS = "_original_kwargs"
    PAYLOAD_DATA = "payload_data"
    MISSING_KEY = "missing_key"
    TEMPLATE = "template"


class LogConfig(BaseModel):
    """Configuration for logging."""

    truncate_length: int = Field(default=500)
    default_payload_value: str = Field(default="<Not Provided>")


class LogPayloadBase(BaseModel):
    """Base model for structured log payloads."""

    pass


class FileOperationPayload(LogPayloadBase):
    """Payload for file operations."""

    file_path: str | None = None


class GDrivePayload(FileOperationPayload):
    """Payload for Google Drive operations."""

    gdrive_id: str | None = None
    gdrive_folder: str | None = None
    md5_hash: str | None = None


class DbPayload(LogPayloadBase):
    """Payload for database operations."""

    db_path: str | None = None
    username: str | None = None
    timestamp: str | None = None


class SearchPayload(LogPayloadBase):
    """Payload for search operations."""

    query_params: str | None = None
    result_count: int | None = None


class ProfilePayload(DbPayload):
    """Payload specific to profile operations."""

    pass


class LibraryPayload(GDrivePayload):
    """Payload for library operations."""

    label: str | None = None


class ErrorPayload(LogPayloadBase):
    """Payload for error logging."""

    error_message: str | None = None


class FuncPayload(LogPayloadBase):
    """Payload including a function name."""

    function_name: str | None = None


class FormatErrorPayload(ErrorPayload):
    """Payload for logging formatting errors."""

    missing_key: str | None = None
    template: str | None = None


class AppConfig(BaseSettings):
    """Application configuration settings."""

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


def display_recipe_markdown(recipe_data: dict[str, Any]) -> str:
    """
    Builds a Markdown snippet for the full recipe details.
    Handles both original and 'simplified_data' structures.
    """
    if RecipeKeys.SIMPLIFIED_DATA in recipe_data:
        data = recipe_data[RecipeKeys.SIMPLIFIED_DATA]
    else:
        data = recipe_data

    if not isinstance(data, dict):
        log_with_payload(
            logging.ERROR, LogMsg.RECIPE_INVALID_DATA_TYPE, type=type(data)
        )

        return f"**Error:** Invalid recipe data format ({type(data)})."

    markdown_str = f"# {data.get(RecipeKeys.TITLE, UiText.DEFAULT_RECIPE_TITLE)}\n\n"

    def add_markdown_section(key: RecipeKeys, title: str) -> str:
        content = data.get(key)
        section_md = MiscValues.EMPTY
        if content and isinstance(content, str):
            section_md += f"### {title}\n\n"
            section_md += f"{content}\n\n"
        elif content:
            log_with_payload(
                logging.WARNING,
                LogMsg.RECIPE_SECTION_CONTENT_INVALID,
                key=key,
                type=type(content),
            )
        return section_md

    markdown_str += add_markdown_section(RecipeKeys.DESCRIPTION, "Description")

    cook_time = data.get(RecipeKeys.COOK_TIME)

    if cook_time:
        markdown_str += f"### Cook Time\n\n{cook_time} minutes\n\n"

    yield_info = data.get(RecipeKeys.YIELD) or data.get(RecipeKeys.YIELDS)
    if yield_info:
        markdown_str += f"### Yields\n\n{yield_info}\n\n"

    markdown_str += add_markdown_section(RecipeKeys.WHY_THIS_WORKS, "Why This Works")
    markdown_str += add_markdown_section(RecipeKeys.HEADNOTE, "Headnote")
    markdown_str += add_markdown_section(RecipeKeys.EQUIPMENT, "Equipment")

    ingredients = data.get(RecipeKeys.INGREDIENTS)
    if ingredients and isinstance(ingredients, list):
        markdown_str += f"### Ingredients\n\n"
        for ing in ingredients:
            if isinstance(ing, dict):
                quantity = ing.get(RecipeKeys.QUANTITY, MiscValues.EMPTY).strip()
                measurement = ing.get(RecipeKeys.MEASUREMENT, MiscValues.EMPTY).strip()
                ingredient = ing.get(RecipeKeys.INGREDIENT, MiscValues.EMPTY).strip()
                detail = ing.get(RecipeKeys.DETAIL, MiscValues.EMPTY).strip()

                line_parts = [
                    part for part in [quantity, measurement, ingredient] if part
                ]
                line = MiscValues.SPACE.join(line_parts)
                if detail and detail.lower() not in line.lower():
                    line += f" ({detail})"

                markdown_str += f"- {line}\n"
            else:
                log_with_payload(
                    logging.WARNING, LogMsg.RECIPE_INVALID_INGREDIENT, item=str(ing)
                )
                markdown_str += (
                    f"- **Warning:** {UiText.INVALID_INGREDIENT_FORMAT} ({str(ing)})\n"
                )

        markdown_str += "\n"

    elif ingredients:
        log_with_payload(
            logging.WARNING, LogMsg.RECIPE_INGREDIENTS_NOT_LIST, type=type(ingredients)
        )

    instructions = data.get(RecipeKeys.INSTRUCTIONS)
    if instructions and isinstance(instructions, list):
        markdown_str += f"### Instructions\n\n"

        def get_step_num(instr: Any) -> float:
            if isinstance(instr, dict):
                step = instr.get(RecipeKeys.STEP)
                try:
                    return float(step) if step is not None else float("inf")
                except (ValueError, TypeError):
                    return float("inf")
            return float("inf")

        try:
            sorted_instructions = sorted(instructions, key=get_step_num)
        except Exception as sort_err:
            err_payload = ErrorPayload(error_message=str(sort_err))
            log_with_payload(
                logging.ERROR,
                LogMsg.RECIPE_INSTRUCTIONS_SORT_FAIL,
                payload=err_payload,
                error=str(sort_err),
                exc_info=True,
            )
            sorted_instructions = instructions
            markdown_str += f"- **Warning:** {UiText.WARNING_INSTRUCTION_SORT_FAIL}\n"

        for ins in sorted_instructions:
            if isinstance(ins, dict):
                step = ins.get(RecipeKeys.STEP, MiscValues.DEFAULT_STEP)
                instruction_text = ins.get(
                    RecipeKeys.INSTRUCTION, "No instruction text."
                )

                markdown_str += f"{step}. {instruction_text}\n"

            else:
                log_with_payload(
                    logging.WARNING, LogMsg.RECIPE_INVALID_INSTRUCTION, item=str(ins)
                )
                markdown_str += (
                    f"- **Warning:** {UiText.INVALID_INSTRUCTION_FORMAT} ({str(ins)})\n"
                )

        markdown_str += "\n"

    elif instructions:
        log_with_payload(
            logging.WARNING,
            LogMsg.RECIPE_INSTRUCTIONS_NOT_LIST,
            type=type(instructions),
        )

    url = data.get(RecipeKeys.URL) or recipe_data.get(RecipeKeys.URL, MiscValues.EMPTY)
    if url and isinstance(url, str):
        markdown_str += f"### Source\n\n"
        url_lower = url.lower()

        if url_lower.startswith(MiscValues.HTTP_PREFIX) or url_lower.startswith(
            MiscValues.HTTPS_PREFIX
        ):
            markdown_str += f"[{url}]({url})\n\n"
        else:
            markdown_str += f"{url}\n\n"
    elif url:
        log_with_payload(logging.WARNING, LogMsg.RECIPE_URL_NOT_STRING, type=type(url))

    return markdown_str


st.set_page_config(layout="wide", page_title=UiText.PAGE_TITLE)


st.markdown(
    """
    <style>
      /* Style both our custom button and any Streamlit “Open Book PDF” button */
      button[title="Open Book PDF"], #openBtn {
        background-color: var(--primary-color) !important;
        color: white !important;
        border: none !important;
        border-radius: 4px !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        padding: 0.5em 1em !important;
        max-width: 180px !important;
        cursor: pointer !important;
      }
      button[title="Open Book PDF"]:hover,
      #openBtn:hover {
        background-color: var(--primary-color-dark) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def open_pdf_in_new_tab(pdf_path: str):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    js = f"""
    <script>
      const binStr = atob("{b64}");
      const len = binStr.length;
      const u8arr = new Uint8Array(len);
      for (let i = 0; i < len; i++) {{
        u8arr[i] = binStr.charCodeAt(i);
      }}
      const blob = new Blob([u8arr], {{ type: 'application/pdf' }});
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank'); 
    </script>
    """

    components.html(js, height=0)


try:
    config = AppConfig()
    default_tag_filter_mode_enum = config._validated_default_tag_filter_mode
except Exception as e:
    logging.basicConfig(level=logging.ERROR)
    logging.critical(LogMsg.CONFIG_LOAD_FAIL.format(error=e), exc_info=True)
    st.error(UiText.FATAL_CONFIG_LOAD_FAIL.format(error=e))
    st.stop()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)


def truncate_string(text: str | bytes, max_length: int) -> str:
    """Truncates a string or bytes object if it exceeds max_length."""
    if isinstance(text, bytes):
        try:
            text_str = text.decode(
                FormatStrings.ENCODING_UTF8,
                errors=FormatStrings.ENCODING_ERRORS_REPLACE,
            )
        except Exception:
            text_str = FormatStrings.BYTES_UNDECODABLE.format(length=len(text))
    else:
        text_str = str(text)

    if len(text_str) > max_length:
        effective_max = max(max_length, len(FormatStrings.TRUNCATION_SUFFIX))
        return (
            text_str[: effective_max - len(FormatStrings.TRUNCATION_SUFFIX)]
            + FormatStrings.TRUNCATION_SUFFIX
        )
    return text_str


def _prepare_log_payload(
    payload: LogPayloadBase | dict[str, Any] | None, max_len: int
) -> dict[str, Any]:
    """Prepares the payload dictionary for logging, truncating long values."""
    if payload is None:
        return {}
    if isinstance(payload, LogPayloadBase):
        dumped_payload = payload.model_dump(exclude_unset=True, exclude_none=True)
    elif isinstance(payload, dict):
        dumped_payload = {k: v for k, v in payload.items() if v is not None}
    else:
        return {LogPayloadKeys.PAYLOAD_DATA: truncate_string(str(payload), max_len)}

    truncated_payload: dict[str, Any] = {}
    for key, value in dumped_payload.items():
        if isinstance(value, (str, bytes)):
            truncated_payload[key] = truncate_string(value, max_len)
        elif isinstance(value, (list, dict, tuple, set)):
            try:
                value_str = json.dumps(value, default=str)
            except TypeError:
                value_str = str(value)
            truncated_payload[key] = truncate_string(value_str, max_len)
        else:
            truncated_payload[key] = value

    return truncated_payload


def log_with_payload(
    level: int,
    msg_template: LogMsg | str,
    payload: LogPayloadBase | dict[str, Any] | None = None,
    exc_info: bool = False,
    **kwargs: Any,
) -> None:
    """
    Logs a message formatted ONLY with **kwargs, including a structured payload in 'extra'.

    Args:
        level: Logging level (e.g., logging.INFO).
        msg_template: A LogMsg enum member or a format string template.
        payload: A Pydantic model or dictionary for the structured payload (passed to 'extra').
        exc_info: If exception info should be added to the log.
        **kwargs: Arguments used ONLY to format the msg_template string.
    """
    prepared_payload = _prepare_log_payload(payload, config.log_config.truncate_length)
    message = str(msg_template)

    try:
        message = str(msg_template).format(**kwargs)
    except KeyError as e:
        missing_key = str(e)
        error_message = LogMsg.LOG_MISSING_FORMAT_KEY.format(
            key=missing_key, template=msg_template
        )

        format_error_payload = FormatErrorPayload(
            error_message=error_message,
            missing_key=missing_key,
            template=str(msg_template),
        )
        logger.warning(
            error_message,
            exc_info=False,
            extra={
                "struct_payload": _prepare_log_payload(
                    format_error_payload, config.log_config.truncate_length
                ),
                "_original_payload": prepared_payload,
                "_original_kwargs": kwargs,
            },
        )

        message = str(msg_template)

    logger.log(
        level, message, exc_info=exc_info, extra={"struct_payload": prepared_payload}
    )


@st.cache_resource
def check_ebook_convert_availability() -> bool:
    """Checks if ebook-convert command is available in the system PATH."""
    path = shutil.which(ToolNames.EBOOK_CONVERT)
    if path:
        log_with_payload(logging.INFO, LogMsg.EBOOK_CONVERT_FOUND, path=path)
        try:
            result = subprocess.run(
                [ToolNames.EBOOK_CONVERT, "--version"],
                capture_output=True,
                text=True,
                check=True,
                encoding=FormatStrings.ENCODING_UTF8,
            )
            output = result.stdout.strip()
            log_with_payload(
                logging.INFO, LogMsg.EBOOK_CONVERT_VERSION_SUCCESS, output=output
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.WARNING,
                LogMsg.EBOOK_CONVERT_VERSION_FAIL,
                payload=err_payload,
                error=str(e),
            )
            return False
        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.EBOOK_CONVERT_VERSION_FAIL,
                payload=err_payload,
                error=str(e),
                exc_info=True,
            )
            return False
    else:
        log_with_payload(logging.ERROR, LogMsg.EBOOK_CONVERT_NOT_FOUND)
        return False


def _get_gdrive_service() -> Any | None:
    """Gets an authenticated Google Drive API client."""

    if GDriveKeys.SECRET_ACCOUNT not in st.secrets:
        st.error(LogMsg.GDRIVE_MISSING_SECRET_ACCOUNT)
        log_with_payload(logging.ERROR, LogMsg.GDRIVE_MISSING_SECRET_ACCOUNT)
        return None

    try:
        folder_id = st.secrets[GDriveKeys.SECRET_DRIVE][GDriveKeys.FOLDER_ID]

        if not folder_id:
            log_with_payload(
                logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + "(value is empty)"
            )
            st.error("Google Drive Folder ID secret is present but has no value.")
            return None

    except KeyError:
        st.error(LogMsg.GDRIVE_MISSING_SECRET_FOLDER)
        log_with_payload(logging.ERROR, LogMsg.GDRIVE_MISSING_SECRET_FOLDER)
        return None
    except TypeError:
        st.error(
            f"Streamlit secret '{GDriveKeys.SECRET_DRIVE}' is not structured correctly."
        )
        log_with_payload(
            logging.ERROR,
            f"Streamlit secret '{GDriveKeys.SECRET_DRIVE}' is not dictionary-like.",
        )
        return None

    try:
        creds_info = st.secrets[GDriveKeys.SECRET_ACCOUNT]
        creds = service_account.Credentials.from_service_account_info(creds_info)
        service = build(
            GDriveKeys.API_SERVICE, GDriveKeys.API_VERSION, credentials=creds
        )
        return service
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_SERVICE_FAIL,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED + f": {e}")
        return None


def calculate_md5(filepath: str, chunk_size: int = config.md5_chunk_size) -> str | None:
    """Calculates the MD5 checksum of a file."""
    payload = FileOperationPayload(file_path=filepath)
    if not os.path.exists(filepath):
        log_with_payload(
            logging.WARNING,
            LogMsg.MD5_FILE_NOT_FOUND,
            payload=payload,
            filepath=filepath,
        )
        return None

    hash_md5 = hashlib.md5()
    try:
        with open(filepath, FileMode.READ_BINARY) as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        hex_digest = hash_md5.hexdigest()

        return hex_digest
    except OSError as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.MD5_READ_ERROR,
            payload=err_payload,
            filepath=filepath,
            error=str(e),
            exc_info=True,
        )
        return None
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.MD5_UNEXPECTED_ERROR,
            payload=err_payload,
            filepath=filepath,
            exc_info=True,
        )
        return None


def download_essential_files() -> None:
    """
    Downloads essential compressed files (e.g., DBs ending in .gz) from Google Drive
    if they don't exist locally, if their MD5 differs, or if the decompressed
    target file is missing. Decompresses them after successful download/verification.
    """
    func_name = "download_essential_files"
    service = _get_gdrive_service()
    if not service:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})"
        )
        st.error(
            UiText.ERROR_GDRIVE_CONNECTION_FAILED + " Cannot download essential files."
        )
        return

    folder_id = st.secrets.get(GDriveKeys.SECRET_DRIVE, {}).get(GDriveKeys.FOLDER_ID)
    dest_dir = config.download_dest_dir
    essential_compressed_files = set(config.essential_filenames or [])

    if not essential_compressed_files:
        log_with_payload(logging.WARNING, "No essential files configured to download.")
        return
    if not folder_id:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + f"({func_name})"
        )
        st.error(
            "Google Drive Folder ID is missing in configuration. Cannot download essential files."
        )
        return

    gdrive_payload = GDrivePayload(gdrive_folder=folder_id)
    log_with_payload(logging.INFO, f"Ensuring local directory '{dest_dir}' exists.")
    os.makedirs(dest_dir, exist_ok=True)

    log_with_payload(
        logging.INFO,
        f"Checking essential files {essential_compressed_files} against GDrive in '{dest_dir}'.",
        payload=gdrive_payload,
    )
    download_needed_count = 0
    verification_failed_count = 0
    decompression_needed_count = 0
    decompression_failed_count = 0
    checked_count = 0
    skipped_download_count = 0

    try:
        page_token = None
        drive_files_details: dict[str, dict[str, Any]] = {}

        log_with_payload(
            logging.INFO, LogMsg.GDRIVE_LISTING_FILES, payload=gdrive_payload
        )
        while True:
            resp = (
                service.files()
                .list(
                    q=GDriveKeys.QUERY_FOLDER_FILES.format(folder_id=folder_id),
                    fields=GDriveKeys.FIELDS_FILE_LIST,
                    pageToken=page_token,
                )
                .execute()
            )
            files_in_page = resp.get(GDriveKeys.FILES, [])
            if not files_in_page and page_token is None:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_NO_FILES_FOUND,
                    payload=gdrive_payload,
                    folder_id=folder_id,
                )
                st.warning(
                    UiText.ERROR_GDRIVE_NO_FILES.format(
                        files=essential_compressed_files
                    )
                )
                return

            for f in files_in_page:
                file_name = f.get(GDriveKeys.FILE_NAME)
                if file_name in essential_compressed_files:
                    file_id = f.get(GDriveKeys.FILE_ID)
                    md5_checksum = f.get(GDriveKeys.FILE_MD5)
                    drive_files_details[file_name] = {
                        GDriveKeys.FILE_ID: file_id,
                        GDriveKeys.FILE_MD5: md5_checksum,
                    }

            page_token = resp.get(GDriveKeys.NEXT_PAGE_TOKEN)
            if not page_token:
                break
        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_LISTING_DONE,
            payload=gdrive_payload,
            count=len(drive_files_details),
        )

        missing_essentials_on_drive = essential_compressed_files - set(
            drive_files_details.keys()
        )
        if missing_essentials_on_drive:
            missing_files_str = ", ".join(missing_essentials_on_drive)
            log_with_payload(
                logging.WARNING,
                LogMsg.GDRIVE_MISSING_ESSENTIALS,
                payload=GDrivePayload(gdrive_folder=folder_id),
                missing_files=missing_files_str,
            )
            st.warning(
                UiText.ERROR_GDRIVE_ESSENTIAL_MISSING.format(files=missing_files_str)
            )

        for compressed_filename, details in drive_files_details.items():
            checked_count += 1
            local_gz_path = os.path.join(dest_dir, compressed_filename)
            drive_file_id = details.get(GDriveKeys.FILE_ID)
            drive_md5 = details.get(GDriveKeys.FILE_MD5)

            file_payload = GDrivePayload(
                file_path=local_gz_path,
                gdrive_id=drive_file_id,
                gdrive_folder=folder_id,
                md5_hash=drive_md5,
            )

            is_compressed = compressed_filename.lower().endswith(FileExt.GZ)
            decompressed_filename = (
                compressed_filename[: -len(FileExt.GZ)]
                if is_compressed
                else compressed_filename
            )
            local_final_path = os.path.join(dest_dir, decompressed_filename)

            decompression_payload = GDrivePayload(
                file_path=local_final_path,
                gdrive_id=drive_file_id,
                gdrive_folder=folder_id,
            )

            if not drive_file_id:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_SKIPPING_NO_ID,
                    payload=file_payload,
                    filename=compressed_filename,
                )
                continue
            if not drive_md5 and is_compressed:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_WARN_NO_MD5,
                    payload=file_payload,
                    filename=compressed_filename,
                )

            should_download = False
            download_verified = False

            if os.path.exists(local_gz_path):
                if drive_md5:
                    local_md5 = calculate_md5(local_gz_path)
                    if local_md5 == drive_md5:
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_LOCAL_VERIFIED_SKIP,
                            payload=file_payload,
                            filename=compressed_filename,
                        )
                        skipped_download_count += 1
                        download_verified = True
                    else:
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_DOWNLOAD_MD5_MISMATCH,
                            payload=file_payload,
                            filename=compressed_filename,
                            local_md5=local_md5,
                            drive_md5=drive_md5,
                        )
                        should_download = True
                else:
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DOWNLOAD_NO_MD5_VERIFY,
                        payload=file_payload,
                        filename=compressed_filename,
                    )
                    should_download = True
            else:
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DOWNLOAD_NEEDED,
                    payload=file_payload,
                    filename=compressed_filename,
                )
                should_download = True

            if should_download:
                download_needed_count += 1
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DOWNLOAD_START,
                    payload=file_payload,
                    filename=compressed_filename,
                    file_id=drive_file_id,
                    path=local_gz_path,
                )
                request = service.files().get_media(fileId=drive_file_id)
                try:
                    with io.FileIO(local_gz_path, FileMode.WRITE_BINARY) as fh:
                        with st.spinner(
                            UiText.SPINNER_DOWNLOADING.format(
                                filename=compressed_filename
                            )
                        ):
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while not done:
                                _, done = downloader.next_chunk(
                                    num_retries=config.gdrive_download_retries
                                )
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DOWNLOAD_DONE,
                        payload=file_payload,
                        filename=compressed_filename,
                    )

                    if drive_md5:
                        post_download_md5 = calculate_md5(local_gz_path)
                        if post_download_md5 == drive_md5:
                            log_with_payload(
                                logging.INFO,
                                LogMsg.GDRIVE_VERIFY_SUCCESS,
                                payload=file_payload,
                                filename=compressed_filename,
                                md5=drive_md5,
                            )
                            download_verified = True
                        else:
                            verify_fail_payload = file_payload.model_copy(
                                update={"md5_hash": post_download_md5}
                            )
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_VERIFY_FAIL,
                                payload=verify_fail_payload,
                                filename=compressed_filename,
                                local_md5=post_download_md5,
                                drive_md5=drive_md5,
                            )
                            st.error(
                                UiText.ERROR_GDRIVE_VERIFY_FAIL.format(
                                    filename=compressed_filename
                                )
                            )
                            verification_failed_count += 1
                            try:
                                os.remove(local_gz_path)
                            except OSError as rm_err:
                                log_with_payload(
                                    logging.ERROR,
                                    LogMsg.GDRIVE_REMOVE_MISMATCHED,
                                    payload=file_payload,
                                    path=local_gz_path,
                                    error=str(rm_err),
                                )
                            continue
                    else:
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_DOWNLOAD_NO_VERIFY,
                            payload=file_payload,
                            filename=compressed_filename,
                        )
                        download_verified = True

                except Exception as download_err:
                    err_payload = ErrorPayload(error_message=str(download_err))
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_DOWNLOAD_FAILED,
                        payload=err_payload,
                        file_payload=file_payload,
                        filename=compressed_filename,
                        file_id=drive_file_id,
                        error=str(download_err),
                        exc_info=True,
                    )
                    st.error(
                        UiText.ERROR_GDRIVE_DOWNLOAD_FAIL_UI.format(
                            filename=compressed_filename, error=download_err
                        )
                    )
                    verification_failed_count += 1
                    if os.path.exists(local_gz_path):
                        try:
                            os.remove(local_gz_path)
                        except OSError as rm_err:
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_REMOVE_INCOMPLETE,
                                payload=file_payload,
                                path=local_gz_path,
                                error=str(rm_err),
                            )
                    continue

            needs_decompression = False
            if download_verified:
                if is_compressed:
                    if not os.path.exists(local_final_path):
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_DECOMPRESS_NEEDED_MISSING,
                            payload=decompression_payload,
                            decompressed_filename=decompressed_filename,
                            compressed_filename=compressed_filename,
                        )
                        needs_decompression = True
                    elif should_download:
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_DECOMPRESS_NEEDED_OVERWRITE,
                            payload=decompression_payload,
                            compressed_filename=compressed_filename,
                            decompressed_filename=decompressed_filename,
                        )
                        needs_decompression = True

                elif not os.path.exists(local_final_path):
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_MISSING_NON_COMPRESSED,
                        payload=file_payload,
                        filename=compressed_filename,
                    )
                    st.error(
                        UiText.ERROR_CRITICAL_FILE_MISSING.format(
                            filename=compressed_filename
                        )
                    )

            if needs_decompression:
                decompression_needed_count += 1
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DECOMPRESSING,
                    payload=decompression_payload,
                    gz_path=local_gz_path,
                    final_path=local_final_path,
                )
                try:
                    with gzip.open(local_gz_path, FileMode.READ_BINARY) as f_in:
                        with open(local_final_path, FileMode.WRITE_BINARY) as f_out:
                            with st.spinner(
                                UiText.SPINNER_DECOMPRESSING.format(
                                    filename=compressed_filename
                                )
                            ):
                                shutil.copyfileobj(f_in, f_out)
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DECOMPRESS_SUCCESS,
                        payload=decompression_payload,
                        final_path=local_final_path,
                    )

                except Exception as decomp_err:
                    err_payload = ErrorPayload(error_message=str(decomp_err))
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_DECOMPRESS_FAILED,
                        payload=err_payload,
                        decompression_payload=decompression_payload,
                        gz_path=local_gz_path,
                        error=str(decomp_err),
                        exc_info=True,
                    )
                    st.error(
                        UiText.ERROR_GDRIVE_DECOMPRESS_FAIL.format(
                            filename=compressed_filename, error=decomp_err
                        )
                    )
                    decompression_failed_count += 1
                    if os.path.exists(local_final_path):
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_REMOVE_INCOMPLETE_DECOMPRESS,
                            payload=decompression_payload,
                            path=local_final_path,
                        )
                        try:
                            os.remove(local_final_path)
                        except OSError as rm_err:
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_FAILED_REMOVE_INCOMPLETE_DECOMPRESS,
                                payload=ErrorPayload(error_message=str(rm_err)),
                                path=local_final_path,
                                error=str(rm_err),
                            )

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ESSENTIALS_SUMMARY,
            checked=checked_count,
            skipped=skipped_download_count,
            attempted=download_needed_count,
            verify_failed=verification_failed_count,
            decompress_needed=decompression_needed_count,
            decompress_failed=decompression_failed_count,
        )

    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.CRITICAL,
            LogMsg.UNHANDLED_ERROR,
            payload=err_payload,
            gdrive_payload=gdrive_payload,
            error="essential files processing",
            exc_info=True,
        )
        st.error(UiText.ERROR_GDRIVE_UNEXPECTED.format(error=e))


download_essential_files()


@st.cache_resource
def get_profile_db_connection() -> sqlite3.Connection | None:
    """Gets a connection to the profiles SQLite database."""
    db_path = config.full_profile_db_path
    db_payload = DbPayload(db_path=db_path)

    if not db_path or not os.path.exists(db_path):
        st.error(UiText.ERROR_PROFILE_DB_PATH_MISSING + f" Path: {db_path}")
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_PATH_INVALID,
            payload=db_payload,
            db_path=str(db_path),
        )

        log_with_payload(
            logging.WARNING, LogMsg.PROFILE_DB_MISSING_RETRY, payload=db_payload
        )
        download_essential_files()

        if not db_path or not os.path.exists(db_path):
            st.error(
                f"Profile database still not found at '{db_path}' after download attempt."
            )
            return None
        else:
            log_with_payload(
                logging.INFO, LogMsg.PROFILE_DB_FOUND_AFTER_RETRY, payload=db_payload
            )

    log_with_payload(
        logging.INFO, LogMsg.PROFILE_DB_CONNECTING, payload=db_payload, db_path=db_path
    )
    try:
        return sqlite3.connect(db_path, check_same_thread=False)
    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_CONNECTION_FAILED,
            payload=err_payload,
            db_payload=db_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_CONNECT_FAILED.format(error=e))
        return None


def init_profile_db() -> None:
    """Creates the user_profiles table if it doesn't exist."""
    conn = get_profile_db_connection()
    db_path = config.full_profile_db_path or "Unknown"
    db_payload = DbPayload(db_path=db_path)

    if not conn:
        st.error(UiText.ERROR_PROFILE_DB_INIT.format(error="No DB connection"))
        log_with_payload(
            logging.ERROR, LogMsg.PROFILE_DB_INIT_FAIL_NO_CONN, payload=db_payload
        )
        return
    try:
        conn.execute(DbKeys.SQL_CREATE_PROFILES)
        conn.commit()
        log_with_payload(
            logging.INFO, LogMsg.PROFILE_DB_INIT_SUCCESS, payload=db_payload
        )
    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_INIT_FAIL,
            payload=err_payload,
            db_payload=db_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_INIT.format(error=e))


def save_profile(username: str, options_base64: str) -> str:
    """Saves a profile to the database. Returns the timestamp."""
    timestamp = datetime.now().isoformat(timespec=FormatStrings.TIMESTAMP_ISO_SECONDS)
    payload = ProfilePayload(username=username, timestamp=timestamp)
    log_with_payload(
        logging.INFO,
        LogMsg.PROFILE_DB_SAVE_ATTEMPT,
        payload=payload,
        username=username,
        timestamp=timestamp,
    )

    conn = get_profile_db_connection()
    if not conn:
        log_with_payload(
            logging.ERROR, LogMsg.PROFILE_DB_CONN_UNAVAILABLE_SAVE, payload=payload
        )
        raise ConnectionError(UiText.ERROR_PROFILE_DB_CONN_MISSING_SAVE)

    try:
        cur = conn.cursor()
        cur.execute(
            DbKeys.SQL_INSERT_PROFILE,
            (username, timestamp, options_base64),
        )
        conn.commit()
        log_with_payload(
            logging.INFO,
            LogMsg.PROFILE_DB_SAVE_SUCCESS,
            payload=payload,
            username=username,
        )
        return timestamp
    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_SAVE_FAIL,
            payload=err_payload,
            profile_payload=payload,
            username=username,
            error=str(e),
            exc_info=True,
        )
        raise


def load_profile(username: str) -> dict[str, Any] | None:
    """Loads the most recent profile for a user."""
    payload = ProfilePayload(username=username)
    log_with_payload(
        logging.INFO, LogMsg.PROFILE_DB_LOAD_ATTEMPT, payload=payload, username=username
    )

    conn = get_profile_db_connection()
    if not conn:
        log_with_payload(
            logging.ERROR, LogMsg.PROFILE_DB_CONN_UNAVAILABLE_LOAD, payload=payload
        )
        st.error(UiText.ERROR_PROFILE_DB_CONN_MISSING_LOAD)
        return None

    try:
        cur = conn.cursor()
        row = cur.execute(
            DbKeys.SQL_SELECT_PROFILE,
            (username,),
        ).fetchone()

        if not row:
            log_with_payload(
                logging.WARNING,
                LogMsg.PROFILE_DB_LOAD_NOT_FOUND,
                payload=payload,
                username=username,
            )
            return None

        payload_b64, actual_ts = row
        payload.timestamp = actual_ts
        try:
            decoded_bytes = base64.b64decode(payload_b64)
            decoded_str = decoded_bytes.decode(FormatStrings.ENCODING_UTF8)
            options_dict = json.loads(decoded_str)
            log_with_payload(
                logging.INFO,
                LogMsg.PROFILE_DB_LOAD_SUCCESS,
                payload=payload,
                username=username,
                timestamp=actual_ts,
            )

            return {
                ProfileDataKeys.TIMESTAMP: actual_ts,
                ProfileDataKeys.OPTIONS: options_dict,
            }
        except (
            base64.binascii.Error,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
        ) as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_DB_LOAD_DECODE_FAIL,
                payload=err_payload,
                profile_payload=payload,
                username=username,
                timestamp=actual_ts,
                error=str(e),
                exc_info=True,
            )
            st.error(UiText.ERROR_PROFILE_DECODE.format(username=username))
            return None

    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.PROFILE_DB_QUERY_FAILED,
            payload=err_payload,
            profile_payload=payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_PROFILE_DB_QUERY_FAILED_LOAD.format(error=e))
        return None


init_profile_db()


@st.cache_resource(ttl=600)
def fetch_sources_cached(db_last_updated_time_key: str | None) -> list[str]:
    """
    Cached function to fetch distinct source domains from the recipe database.
    Uses a stable string representation of update time for cache keying.
    """
    log_with_payload(
        logging.INFO,
        LogMsg.SOURCES_FETCHING,
        db_timestamp=str(db_last_updated_time_key),
    )
    func_payload = FuncPayload(function_name="fetch_sources_cached")

    conn: sqlite3.Connection | None = None
    try:
        conn = get_recipe_db_connection()
        if not conn:
            log_with_payload(
                logging.ERROR,
                LogMsg.RECIPE_DB_CONN_FAIL,
                payload=func_payload,
                function_name=func_payload.function_name,
            )
            st.error(UiText.ERROR_RECIPE_DB_CONNECT_FAILED_SOURCES)
            return []

        rows = conn.execute(DbKeys.SQL_SELECT_SOURCES).fetchall()
        sources = sorted([r[0] for r in rows if r and r[0]])
        log_with_payload(
            logging.INFO,
            LogMsg.SOURCES_FETCHED_COUNT,
            payload=func_payload,
            count=len(sources),
        )
        return sources
    except sqlite3.Error as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.RECIPE_DB_QUERY_SOURCES_FAILED,
            payload=err_payload,
            func_payload=func_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_RECIPE_DB_QUERY_FAILED_SOURCES.format(error=e))
        return []
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.SOURCES_FETCH_UNEXPECTED_ERROR,
            payload=err_payload,
            func_payload=func_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_UNEXPECTED_FETCH_SOURCES.format(error=e))
        return []
    finally:
        if conn:
            conn.close()


@st.cache_resource(ttl=600)
def list_drive_books_cached() -> tuple[list[str], dict[str, dict[str, str]]]:
    """Lists cookbook files from Google Drive, returning labels and a mapping to file ID and name."""
    func_name = "list_drive_books_cached"
    service = _get_gdrive_service()
    if not service:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})"
        )
        st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED + " Cannot list books.")

        return [], {}

    folder_id = st.secrets.get(GDriveKeys.SECRET_DRIVE, {}).get(GDriveKeys.FOLDER_ID)
    if not folder_id:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + f"({func_name})"
        )
        st.error("Google Drive Folder ID is missing. Cannot list books.")

        return [], {}

    payload = GDrivePayload(gdrive_folder=folder_id)
    log_with_payload(
        logging.INFO, LogMsg.GDRIVE_LISTING_BOOKS, payload=payload, folder_id=folder_id
    )
    book_labels = []
    book_mapping: dict[str, dict[str, str]] = {}
    all_files_count = 0

    try:
        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=GDriveKeys.QUERY_FOLDER_FILES.format(folder_id=folder_id),
                    fields=GDriveKeys.FIELDS_FILE_LIST_NO_MD5,
                    pageToken=page_token,
                )
                .execute()
            )

            files = resp.get(GDriveKeys.FILES, [])
            if not files and page_token is None:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_NO_BOOKS_FOUND_LISTING,
                    payload=payload,
                )

                return [], {}

            for f in files:
                all_files_count += 1
                file_name = f.get(GDriveKeys.FILE_NAME)
                file_id = f.get(GDriveKeys.FILE_ID)

                if (
                    file_name
                    and file_id
                    and file_name.lower().endswith(config.valid_book_extensions)
                ):
                    label = pathlib.Path(file_name).stem
                    if label not in book_mapping:
                        book_labels.append(label)

                        book_mapping[label] = {
                            GDriveKeys.FILE_ID: file_id,
                            GDriveKeys.FILE_NAME: file_name,
                        }
                    else:
                        dup_payload = LibraryPayload(
                            label=label, gdrive_id=file_id, file_path=file_name
                        )
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_LIST_DUPLICATE_LABEL,
                            payload=dup_payload,
                            label=label,
                            filename=file_name,
                            file_id=file_id,
                        )

            page_token = resp.get(GDriveKeys.NEXT_PAGE_TOKEN)
            if not page_token:
                break

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_LIST_BOOK_COUNT,
            payload=payload,
            count=len(book_labels),
        )
        book_labels.sort()
        return book_labels, book_mapping

    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_LIST_BOOK_ERROR,
            payload=err_payload,
            gdrive_payload=payload,
            folder_id=folder_id,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_BOOKS_LOAD_FAIL.format(error=e))

        return [], {}


def download_gdrive_file(
    file_id: str, file_name: str, destination_dir: str
) -> str | None:
    """Downloads a single file from GDrive if not already present locally."""
    func_name = "download_gdrive_file"
    dest_path = os.path.join(destination_dir, file_name)
    payload = GDrivePayload(file_path=dest_path, gdrive_id=file_id)

    try:
        os.makedirs(destination_dir, exist_ok=True)

        if os.path.exists(dest_path):
            log_with_payload(
                logging.INFO,
                LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_SKIP,
                payload=payload,
                filename=file_name,
                path=dest_path,
            )
            return dest_path

        service = _get_gdrive_service()
        if not service:
            log_with_payload(
                logging.ERROR,
                LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})",
                payload=payload,
            )
            st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED)
            return None

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_START,
            payload=payload,
            filename=file_name,
            file_id=file_id,
            path=dest_path,
        )
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(dest_path, FileMode.WRITE_BINARY) as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            with st.spinner(
                UiText.SPINNER_DOWNLOADING_ON_DEMAND.format(filename=file_name)
            ):
                while not done:
                    status, done = downloader.next_chunk(
                        num_retries=config.gdrive_download_retries
                    )

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_DONE,
            payload=payload,
            filename=file_name,
        )
        return dest_path
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_FAILED,
            payload=err_payload,
            file_payload=payload,
            filename=file_name,
            file_id=file_id,
            error=str(e),
            exc_info=True,
        )
        st.error(
            UiText.ERROR_GDRIVE_DOWNLOAD_FAIL_UI.format(filename=file_name, error=e)
        )

        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_ONDEMAND_REMOVE_INCOMPLETE,
                    payload=payload,
                    path=dest_path,
                )
            except OSError as rm_err:
                err_payload = ErrorPayload(error_message=str(rm_err))
                log_with_payload(
                    logging.ERROR,
                    LogMsg.GDRIVE_ONDEMAND_FAILED_REMOVE,
                    payload=err_payload,
                    file_payload=payload,
                    path=dest_path,
                    error=str(rm_err),
                )
        return None


@st.cache_resource(max_entries=5)
def to_pdf_cached(source_path: str, temp_dir: str) -> str:
    """
    Converts an ebook (epub, mobi) to PDF using ebook-convert.
    Returns the path to the PDF. Requires Calibre's ebook-convert.
    Raises exceptions on failure.
    """
    payload = FileOperationPayload(file_path=source_path)
    log_with_payload(
        logging.INFO, LogMsg.EBOOK_CONVERT_REQ, payload=payload, source_path=source_path
    )

    if not os.path.exists(source_path):
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_SRC_NOT_FOUND,
            payload=payload,
            source_path=source_path,
        )
        raise FileNotFoundError(f"Source file not found: {source_path}")

    source_lower = source_path.lower()
    if source_lower.endswith(FileExt.PDF):
        log_with_payload(
            logging.INFO, LogMsg.EBOOK_CONVERT_ALREADY_PDF, payload=payload
        )
        return source_path

    if not (source_lower.endswith(FileExt.EPUB) or source_lower.endswith(FileExt.MOBI)):
        log_with_payload(
            logging.WARNING,
            LogMsg.LIBRARY_UNSUPPORTED_TYPE,
            payload=payload,
            path=source_path,
        )
        raise ValueError(
            f"Cannot convert unsupported file type: {pathlib.Path(source_path).suffix}"
        )

    output_pdf_path = os.path.join(
        temp_dir, pathlib.Path(source_path).stem + FileExt.PDF
    )

    output_payload = FileOperationPayload(file_path=output_pdf_path)

    if os.path.exists(output_pdf_path):
        log_with_payload(
            logging.INFO,
            LogMsg.EBOOK_CONVERT_FOUND_EXISTING,
            payload=output_payload,
            output_pdf_path=output_pdf_path,
        )
        return output_pdf_path

    log_with_payload(
        logging.INFO,
        LogMsg.EBOOK_CONVERT_CONVERTING,
        payload=output_payload,
        source_path=source_path,
        output_pdf_path=output_pdf_path,
    )
    try:
        os.makedirs(temp_dir, exist_ok=True)
        source_filename = pathlib.Path(source_path).name

        with st.spinner(UiText.SPINNER_CONVERTING_PDF.format(filename=source_filename)):
            result = subprocess.run(
                [ToolNames.EBOOK_CONVERT, source_path, output_pdf_path],
                check=True,
                capture_output=True,
                text=True,
                encoding=FormatStrings.ENCODING_UTF8,
            )
        log_with_payload(
            logging.INFO,
            LogMsg.EBOOK_CONVERT_SUCCESS,
            payload=output_payload,
            source_path=source_path,
            output=result.stdout,
        )

        if not os.path.exists(output_pdf_path):
            log_with_payload(
                logging.ERROR,
                LogMsg.EBOOK_CONVERT_OUTPUT_MISSING,
                payload=output_payload,
                output_pdf_path=output_pdf_path,
            )
            raise RuntimeError(
                f"ebook-convert failed to create output file: {output_pdf_path}"
            )
        return output_pdf_path

    except FileNotFoundError:
        log_with_payload(
            logging.ERROR, LogMsg.EBOOK_CONVERT_CMD_NOT_FOUND, payload=payload
        )
        st.error(UiText.ERROR_EBOOK_CONVERT_MISSING_RUNTIME)
        raise
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "<No Stderr>"
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_FAILED,
            payload=err_payload,
            file_payload=payload,
            source_path=source_path,
            error=str(e),
            stderr=stderr,
            exc_info=True,
        )
        st.error(
            UiText.ERROR_EBOOK_CONVERT_FAIL_RUNTIME.format(
                filename=pathlib.Path(source_path).name, stderr=stderr
            )
        )
        raise
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_UNEXPECTED_ERROR,
            payload=err_payload,
            file_payload=payload,
            source_path=source_path,
            exc_info=True,
        )
        st.error(UiText.ERROR_EBOOK_CONVERT_UNEXPECTED_RUNTIME.format(error=e))
        raise


def initialize_session_state():
    """Initializes Streamlit session state with default values."""

    default_sources = []
    try:
        db_update_time = fetch_db_last_updated()
        cache_key_time = (
            db_update_time.strftime(FormatStrings.TIMESTAMP_CACHE_KEY)
            if isinstance(db_update_time, datetime)
            else str(db_update_time)
        )
        all_sources = fetch_sources_cached(cache_key_time)
        valid_sources = [s for s in all_sources if s != UiText.ERROR_SOURCES_DISPLAY]
        st.session_state[SessionStateKeys.ALL_SOURCES_LIST] = valid_sources
        default_sources = valid_sources
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.SOURCES_FETCH_INIT_FAIL,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_SOURCES_LOAD_FAIL.format(error=e))
        st.session_state[SessionStateKeys.ALL_SOURCES_LIST] = [
            UiText.ERROR_SOURCES_DISPLAY
        ]
        default_sources = []

    try:
        book_labels, book_mapping = list_drive_books_cached()
        st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING] = book_mapping
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            "Failed to list books from Drive during init.",
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_BOOKS_LOAD_FAIL.format(error=e))
        st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING] = {}

    defaults = config.defaults

    state_initializer = {
        SessionStateKeys.SELECTED_PAGE: UiText.TAB_ABOUT,
        SessionStateKeys.ADVANCED_SEARCH_RESULTS_HTML: defaults.profile_message,
        SessionStateKeys.ADVANCED_SEARCH_MAPPING: {},
        SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL: None,
        SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML: defaults.profile_message,
        SessionStateKeys.SIMPLE_SEARCH_MAPPING: {},
        SessionStateKeys.ADVANCED_SEARCH_RESULTS_DF: None,
        SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF: None,
        SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL: None,
        SessionStateKeys.LOADED_INGREDIENTS_TEXT: defaults.ingredients_text,
        SessionStateKeys.LOADED_MUST_USE_TEXT: defaults.must_use_text,
        SessionStateKeys.LOADED_EXCLUDED_TEXT: defaults.excluded_text,
        SessionStateKeys.LOADED_KEYWORDS_INCLUDE: defaults.keywords_include,
        SessionStateKeys.LOADED_KEYWORDS_EXCLUDE: defaults.keywords_exclude,
        SessionStateKeys.LOADED_MIN_ING_MATCHES: defaults.min_ing_matches,
        SessionStateKeys.LOADED_COURSE_FILTER: [],
        SessionStateKeys.LOADED_MAIN_ING_FILTER: [],
        SessionStateKeys.LOADED_DISH_TYPE_FILTER: [],
        SessionStateKeys.LOADED_RECIPE_TYPE_FILTER: [],
        SessionStateKeys.LOADED_CUISINE_FILTER: [],
        SessionStateKeys.LOADED_EXCLUDE_COURSE_FILTER: [],
        SessionStateKeys.LOADED_EXCLUDE_MAIN_ING_FILTER: [],
        SessionStateKeys.LOADED_EXCLUDE_DISH_TYPE_FILTER: [],
        SessionStateKeys.LOADED_EXCLUDE_RECIPE_TYPE_FILTER: [],
        SessionStateKeys.LOADED_EXCLUDE_CUISINE_FILTER: [],
        SessionStateKeys.LOADED_TAG_FILTER_MODE: default_tag_filter_mode_enum,
        SessionStateKeys.LOADED_MAX_STEPS: defaults.max_steps,
        SessionStateKeys.LOADED_USER_COVERAGE: defaults.user_coverage * 100.0,
        SessionStateKeys.LOADED_RECIPE_COVERAGE: defaults.recipe_coverage * 100.0,
        SessionStateKeys.LOADED_SOURCES: default_sources,
        SessionStateKeys.PROFILE_STATUS_MESSAGE: defaults.profile_message,
    }

    for key, default_value in state_initializer.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


initialize_session_state()


page_options = [
    UiText.TAB_ABOUT,
    UiText.TAB_ADVANCED,
    UiText.TAB_SIMPLE,
    UiText.TAB_LIBRARY,
]

st.sidebar.radio(
    UiText.SIDEBAR_PAGE_SELECT,
    options=page_options,
    key=SessionStateKeys.SELECTED_PAGE,
)


if st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_ABOUT:
    st.markdown(UiText.ABOUT_MARKDOWN)

elif st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_ADVANCED:
    st.header(UiText.HEADER_ADVANCED_SEARCH)

    def run_advanced_search():
        log_with_payload(logging.INFO, LogMsg.ADV_SEARCH_CLICKED)
        defaults = config.defaults

        def get_list_from_textarea(key: SessionStateKeys) -> list[str]:
            text = st.session_state.get(key, MiscValues.EMPTY)
            return [
                item.strip()
                for item in text.strip().split(MiscValues.NEWLINE)
                if item.strip()
            ]

        def get_list_from_textinput(key: SessionStateKeys) -> list[str]:
            text = st.session_state.get(key, MiscValues.EMPTY)
            return [
                item.strip()
                for item in text.strip().split(MiscValues.SPACE)
                if item.strip()
            ]

        tag_filters = {
            cat_key: st.session_state.get(widget_key, [])
            for cat_key, widget_key in [
                (CategoryKeys.COURSE, SessionStateKeys.ADV_COURSE_FILTER_INPUT),
                (
                    CategoryKeys.MAIN_INGREDIENT,
                    SessionStateKeys.ADV_MAIN_ING_FILTER_INPUT,
                ),
                (CategoryKeys.DISH_TYPE, SessionStateKeys.ADV_DISH_TYPE_FILTER_INPUT),
                (
                    CategoryKeys.RECIPE_TYPE,
                    SessionStateKeys.ADV_RECIPE_TYPE_FILTER_INPUT,
                ),
                (CategoryKeys.CUISINE, SessionStateKeys.ADV_CUISINE_FILTER_INPUT),
            ]
            if st.session_state.get(widget_key)
        }
        excluded_tags = {
            cat_key: st.session_state.get(widget_key, [])
            for cat_key, widget_key in [
                (CategoryKeys.COURSE, SessionStateKeys.ADV_EXCLUDE_COURSE_FILTER_INPUT),
                (
                    CategoryKeys.MAIN_INGREDIENT,
                    SessionStateKeys.ADV_EXCLUDE_MAIN_ING_FILTER_INPUT,
                ),
                (
                    CategoryKeys.DISH_TYPE,
                    SessionStateKeys.ADV_EXCLUDE_DISH_TYPE_FILTER_INPUT,
                ),
                (
                    CategoryKeys.RECIPE_TYPE,
                    SessionStateKeys.ADV_EXCLUDE_RECIPE_TYPE_FILTER_INPUT,
                ),
                (
                    CategoryKeys.CUISINE,
                    SessionStateKeys.ADV_EXCLUDE_CUISINE_FILTER_INPUT,
                ),
            ]
            if st.session_state.get(widget_key)
        }

        selected_sources = [
            s
            for s in st.session_state.get(SessionStateKeys.ADV_SOURCE_SELECTOR, [])
            if s != UiText.ERROR_SOURCES_DISPLAY
        ]

        if not selected_sources:
            selected_sources = [
                s
                for s in st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, [])
                if s != UiText.ERROR_SOURCES_DISPLAY
            ]

        query_params = dict(
            user_ingredients=get_list_from_textarea(
                SessionStateKeys.ADV_INGREDIENTS_INPUT
            ),
            tag_filters=tag_filters,
            excluded_tags=excluded_tags,
            min_ing_matches=int(
                st.session_state.get(
                    SessionStateKeys.ADV_MIN_ING_MATCHES_INPUT, defaults.min_ing_matches
                )
            ),
            forbidden_ingredients=get_list_from_textarea(
                SessionStateKeys.ADV_EXCLUDED_INPUT
            ),
            must_use=get_list_from_textarea(SessionStateKeys.ADV_MUST_USE_INPUT),
            tag_filter_mode=st.session_state.get(
                SessionStateKeys.ADV_TAG_FILTER_MODE_INPUT, default_tag_filter_mode_enum
            ),
            max_steps=int(
                st.session_state.get(
                    SessionStateKeys.ADV_MAX_STEPS_INPUT, defaults.max_steps
                )
            ),
            user_coverage_req=float(
                st.session_state.get(
                    SessionStateKeys.ADV_USER_COVERAGE_SLIDER,
                    defaults.user_coverage * 100.0,
                )
            )
            / 100.0,
            recipe_coverage_req=float(
                st.session_state.get(
                    SessionStateKeys.ADV_RECIPE_COVERAGE_SLIDER,
                    defaults.recipe_coverage * 100.0,
                )
            )
            / 100.0,
            keywords_to_include=get_list_from_textinput(
                SessionStateKeys.ADV_KEYWORDS_INCLUDE_INPUT
            ),
            keywords_to_exclude=get_list_from_textinput(
                SessionStateKeys.ADV_KEYWORDS_EXCLUDE_INPUT
            ),
            sources=selected_sources,
        )

        try:
            params_json = json.dumps(
                query_params, indent=config.json_indent, default=str
            )
        except TypeError:
            params_json = LogMsg.SERIALIZE_PARAMS_FAIL

        payload = SearchPayload(query_params=params_json)
        log_with_payload(
            logging.INFO,
            LogMsg.ADV_SEARCH_PARAMS,
            payload=payload,
            params_json=params_json,
        )

        try:
            results = query_top_k(**query_params)
        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.ADV_SEARCH_QUERY_ERROR,
                payload=err_payload,
                search_payload=payload,
                exc_info=True,
            )
            st.error(UiText.ERROR_DURING_SEARCH.format(error=e))

            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_HTML] = (
                UiText.ERROR_DURING_SEARCH.format(error=e)
            )

            st.session_state[SessionStateKeys.ADVANCED_SEARCH_MAPPING] = {}
            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_DF] = None
            st.session_state[SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL] = None
            return

        if not results:
            log_with_payload(
                logging.INFO, LogMsg.ADV_SEARCH_NO_RESULTS, payload=payload
            )
            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_HTML] = (
                UiText.MSG_NO_RESULTS_FOUND_ADV
            )
            st.session_state[SessionStateKeys.ADVANCED_SEARCH_MAPPING] = {}
            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_DF] = None
            st.session_state[SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL] = None
        else:
            payload.result_count = len(results)
            log_with_payload(
                logging.INFO,
                LogMsg.ADV_SEARCH_RESULTS_COUNT,
                payload=payload,
                count=len(results),
            )

            results_data_for_df = []
            dropdown_mapping = {}
            for r in results:
                user_cov = r.get(RecipeKeys.USER_COVERAGE, 0.0)
                recipe_cov = r.get(RecipeKeys.RECIPE_COVERAGE, 0.0)
                url = r.get(RecipeKeys.URL, UiText.DEFAULT_RECIPE_URL)
                title = r.get(RecipeKeys.TITLE, UiText.DEFAULT_RECIPE_TITLE)
                recipe_dict = r.get(RecipeKeys.RECIPE, {})

                df_row = {
                    "User Coverage": f"{user_cov:.1%}",
                    "Recipe Coverage": f"{recipe_cov:.1%}",
                    "Source / URL": url,
                    "Recipe Title": title,
                }
                results_data_for_df.append(df_row)

                label = FormatStrings.RECIPE_LABEL.format(
                    coverage=recipe_cov, title=title
                )
                original_label = label
                count = 1
                while label in dropdown_mapping:
                    label = FormatStrings.RECIPE_LABEL_DUPLICATE.format(
                        original_label=original_label, count=count
                    )
                    count += 1

                dropdown_mapping[label] = {
                    RecipeKeys.URL: url,
                    RecipeKeys.RECIPE: recipe_dict,
                }

            results_df = pd.DataFrame(results_data_for_df)

            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_DF] = results_df
            st.session_state[SessionStateKeys.ADVANCED_SEARCH_MAPPING] = (
                dropdown_mapping
            )

            st.session_state[SessionStateKeys.ADVANCED_SEARCH_RESULTS_HTML] = (
                MiscValues.EMPTY
            )

            first_label = next(iter(dropdown_mapping.keys()), None)
            st.session_state[SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL] = (
                first_label
            )

            log_with_payload(
                logging.INFO,
                LogMsg.ADV_SEARCH_PROCESSED,
                payload=payload,
                df_shape=str(results_df.shape),
                map_keys=len(dropdown_mapping),
            )

    def save_profile_action():
        log_with_payload(logging.INFO, LogMsg.PROFILE_SAVE_CLICKED)
        defaults = config.defaults
        username = st.session_state.get(
            SessionStateKeys.USERNAME_INPUT, defaults.username
        )

        if not username or not username.strip():
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_USERNAME_NEEDED_SAVE
            )
            return

        username = username.strip()
        payload = ProfilePayload(username=username)

        options_dict = {
            ProfileDataKeys.INGREDIENTS_TEXT: st.session_state.get(
                SessionStateKeys.ADV_INGREDIENTS_INPUT, defaults.ingredients_text
            ),
            ProfileDataKeys.MUST_USE_TEXT: st.session_state.get(
                SessionStateKeys.ADV_MUST_USE_INPUT, defaults.must_use_text
            ),
            ProfileDataKeys.EXCLUDED_BOX: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDED_INPUT, defaults.excluded_text
            ),
            ProfileDataKeys.KEYWORDS_INCLUDE: st.session_state.get(
                SessionStateKeys.ADV_KEYWORDS_INCLUDE_INPUT, defaults.keywords_include
            ),
            ProfileDataKeys.KEYWORDS_EXCLUDE: st.session_state.get(
                SessionStateKeys.ADV_KEYWORDS_EXCLUDE_INPUT, defaults.keywords_exclude
            ),
            ProfileDataKeys.MIN_ING_MATCHES: int(
                st.session_state.get(
                    SessionStateKeys.ADV_MIN_ING_MATCHES_INPUT, defaults.min_ing_matches
                )
            ),
            ProfileDataKeys.COURSE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_COURSE_FILTER_INPUT, []
            ),
            ProfileDataKeys.MAIN_ING_FILTER: st.session_state.get(
                SessionStateKeys.ADV_MAIN_ING_FILTER_INPUT, []
            ),
            ProfileDataKeys.DISH_TYPE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_DISH_TYPE_FILTER_INPUT, []
            ),
            ProfileDataKeys.RECIPE_TYPE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_RECIPE_TYPE_FILTER_INPUT, []
            ),
            ProfileDataKeys.CUISINE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_CUISINE_FILTER_INPUT, []
            ),
            ProfileDataKeys.EXCLUDE_COURSE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDE_COURSE_FILTER_INPUT, []
            ),
            ProfileDataKeys.EXCLUDE_MAIN_ING_FILTER: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDE_MAIN_ING_FILTER_INPUT, []
            ),
            ProfileDataKeys.EXCLUDE_DISH_TYPE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDE_DISH_TYPE_FILTER_INPUT, []
            ),
            ProfileDataKeys.EXCLUDE_RECIPE_TYPE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDE_RECIPE_TYPE_FILTER_INPUT, []
            ),
            ProfileDataKeys.EXCLUDE_CUISINE_FILTER: st.session_state.get(
                SessionStateKeys.ADV_EXCLUDE_CUISINE_FILTER_INPUT, []
            ),
            ProfileDataKeys.TAG_FILTER_MODE: st.session_state.get(
                SessionStateKeys.ADV_TAG_FILTER_MODE_INPUT, default_tag_filter_mode_enum
            ).value,
            ProfileDataKeys.MAX_STEPS: int(
                st.session_state.get(
                    SessionStateKeys.ADV_MAX_STEPS_INPUT, defaults.max_steps
                )
            ),
            ProfileDataKeys.USER_COVERAGE_SLIDER: float(
                st.session_state.get(
                    SessionStateKeys.ADV_USER_COVERAGE_SLIDER,
                    defaults.user_coverage * 100.0,
                )
            ),
            ProfileDataKeys.RECIPE_COVERAGE_SLIDER: float(
                st.session_state.get(
                    SessionStateKeys.ADV_RECIPE_COVERAGE_SLIDER,
                    defaults.recipe_coverage * 100.0,
                )
            ),
            ProfileDataKeys.SOURCES: st.session_state.get(
                SessionStateKeys.ADV_SOURCE_SELECTOR, []
            ),
        }

        try:
            json_str = json.dumps(options_dict, indent=config.json_indent)
            b64_str = base64.b64encode(
                json_str.encode(FormatStrings.ENCODING_UTF8)
            ).decode(FormatStrings.ENCODING_UTF8)
        except (TypeError, json.JSONDecodeError) as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_ENCODE_FAIL,
                payload=err_payload,
                profile_payload=payload,
                error=str(e),
                exc_info=True,
            )
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_ENCODE_ERROR.format(error=e)
            )
            return

        try:
            saved_ts = save_profile(username, b64_str)
            payload.timestamp = saved_ts
            log_with_payload(
                logging.INFO, "Profile saved via UI action.", payload=payload
            )
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_SAVE_SUCCESS.format(
                    username=username, timestamp=saved_ts
                )
            )
        except ConnectionError as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_SAVE_ACTION_FAIL,
                payload=err_payload,
                profile_payload=payload,
                error=str(e),
            )
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_SAVE_ERROR.format(error=e)
            )
        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_SAVE_ACTION_FAIL,
                payload=err_payload,
                profile_payload=payload,
                error=str(e),
                exc_info=True,
            )
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_SAVE_ERROR.format(error=e)
            )

    def load_profile_action():
        log_with_payload(logging.INFO, LogMsg.PROFILE_LOAD_CLICKED)
        defaults = config.defaults
        username = st.session_state.get(
            SessionStateKeys.USERNAME_INPUT, defaults.username
        )

        if not username or not username.strip():
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_USERNAME_NEEDED_LOAD
            )
            return

        username = username.strip()
        payload = ProfilePayload(username=username)

        try:
            loaded_data = load_profile(username)
            if loaded_data is None:
                st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                    UiText.PROFILE_MSG_LOAD_NOT_FOUND.format(username=username)
                )
            else:
                options = loaded_data.get(ProfileDataKeys.OPTIONS, {})
                timestamp = loaded_data.get(
                    ProfileDataKeys.TIMESTAMP, UiText.DEFAULT_TIMESTAMP
                )
                payload.timestamp = timestamp

                st.session_state[SessionStateKeys.LOADED_INGREDIENTS_TEXT] = (
                    options.get(
                        ProfileDataKeys.INGREDIENTS_TEXT, defaults.ingredients_text
                    )
                )
                st.session_state[SessionStateKeys.LOADED_MUST_USE_TEXT] = options.get(
                    ProfileDataKeys.MUST_USE_TEXT, defaults.must_use_text
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDED_TEXT] = options.get(
                    ProfileDataKeys.EXCLUDED_BOX, defaults.excluded_text
                )
                st.session_state[SessionStateKeys.LOADED_KEYWORDS_INCLUDE] = (
                    options.get(
                        ProfileDataKeys.KEYWORDS_INCLUDE, defaults.keywords_include
                    )
                )
                st.session_state[SessionStateKeys.LOADED_KEYWORDS_EXCLUDE] = (
                    options.get(
                        ProfileDataKeys.KEYWORDS_EXCLUDE, defaults.keywords_exclude
                    )
                )
                st.session_state[SessionStateKeys.LOADED_MIN_ING_MATCHES] = int(
                    options.get(
                        ProfileDataKeys.MIN_ING_MATCHES, defaults.min_ing_matches
                    )
                )
                st.session_state[SessionStateKeys.LOADED_COURSE_FILTER] = options.get(
                    ProfileDataKeys.COURSE_FILTER, []
                )
                st.session_state[SessionStateKeys.LOADED_MAIN_ING_FILTER] = options.get(
                    ProfileDataKeys.MAIN_ING_FILTER, []
                )
                st.session_state[SessionStateKeys.LOADED_DISH_TYPE_FILTER] = (
                    options.get(ProfileDataKeys.DISH_TYPE_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_RECIPE_TYPE_FILTER] = (
                    options.get(ProfileDataKeys.RECIPE_TYPE_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_CUISINE_FILTER] = options.get(
                    ProfileDataKeys.CUISINE_FILTER, []
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDE_COURSE_FILTER] = (
                    options.get(ProfileDataKeys.EXCLUDE_COURSE_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDE_MAIN_ING_FILTER] = (
                    options.get(ProfileDataKeys.EXCLUDE_MAIN_ING_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDE_DISH_TYPE_FILTER] = (
                    options.get(ProfileDataKeys.EXCLUDE_DISH_TYPE_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDE_RECIPE_TYPE_FILTER] = (
                    options.get(ProfileDataKeys.EXCLUDE_RECIPE_TYPE_FILTER, [])
                )
                st.session_state[SessionStateKeys.LOADED_EXCLUDE_CUISINE_FILTER] = (
                    options.get(ProfileDataKeys.EXCLUDE_CUISINE_FILTER, [])
                )

                loaded_mode_str = options.get(
                    ProfileDataKeys.TAG_FILTER_MODE, default_tag_filter_mode_enum.value
                )
                try:
                    st.session_state[SessionStateKeys.LOADED_TAG_FILTER_MODE] = (
                        TagFilterMode(loaded_mode_str)
                    )
                except ValueError:
                    log_with_payload(
                        logging.WARNING,
                        LogMsg.PROFILE_INVALID_MODE_LOADED,
                        payload=payload,
                        mode=loaded_mode_str,
                    )
                    st.session_state[SessionStateKeys.LOADED_TAG_FILTER_MODE] = (
                        default_tag_filter_mode_enum
                    )

                st.session_state[SessionStateKeys.LOADED_MAX_STEPS] = int(
                    options.get(ProfileDataKeys.MAX_STEPS, defaults.max_steps)
                )

                st.session_state[SessionStateKeys.LOADED_USER_COVERAGE] = float(
                    options.get(
                        ProfileDataKeys.USER_COVERAGE_SLIDER,
                        defaults.user_coverage * 100.0,
                    )
                )
                st.session_state[SessionStateKeys.LOADED_RECIPE_COVERAGE] = float(
                    options.get(
                        ProfileDataKeys.RECIPE_COVERAGE_SLIDER,
                        defaults.recipe_coverage * 100.0,
                    )
                )

                valid_current_sources = [
                    s
                    for s in st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, [])
                    if s != UiText.ERROR_SOURCES_DISPLAY
                ]
                loaded_profile_sources = options.get(ProfileDataKeys.SOURCES, [])
                st.session_state[SessionStateKeys.LOADED_SOURCES] = [
                    s for s in loaded_profile_sources if s in valid_current_sources
                ]

                st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                    UiText.PROFILE_MSG_LOAD_SUCCESS.format(
                        username=username, timestamp=timestamp
                    )
                )
                log_with_payload(
                    logging.INFO,
                    LogMsg.PROFILE_LOADED_RERUN,
                    payload=payload,
                    username=username,
                )

        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.PROFILE_LOAD_ACTION_FAIL,
                payload=err_payload,
                profile_payload=payload,
                error=str(e),
                exc_info=True,
            )
            st.session_state[SessionStateKeys.PROFILE_STATUS_MESSAGE] = (
                UiText.PROFILE_MSG_LOAD_ERROR.format(error=e)
            )

    def refresh_sources_action():
        log_with_payload(logging.INFO, LogMsg.SOURCES_REFRESH_CLICKED)

        fetch_sources_cached.clear()
        try:
            db_update_time = fetch_db_last_updated()
            if db_update_time:
                cache_key_time = (
                    db_update_time.strftime(FormatStrings.TIMESTAMP_CACHE_KEY)
                    if isinstance(db_update_time, datetime)
                    else str(db_update_time)
                )
                new_sources = fetch_sources_cached(cache_key_time)
                valid_new_sources = [
                    s for s in new_sources if s != UiText.ERROR_SOURCES_DISPLAY
                ]
                st.session_state[SessionStateKeys.ALL_SOURCES_LIST] = valid_new_sources

                st.session_state[SessionStateKeys.LOADED_SOURCES] = valid_new_sources

                if SessionStateKeys.ADV_SOURCE_SELECTOR in st.session_state:
                    st.session_state[SessionStateKeys.ADV_SOURCE_SELECTOR] = (
                        valid_new_sources
                    )
                log_with_payload(logging.INFO, LogMsg.SOURCES_REFRESHED)
            else:
                log_with_payload(logging.WARNING, LogMsg.SOURCES_REFRESH_DB_TIME_FAIL)
                st.error(LogMsg.SOURCES_REFRESH_DB_TIME_FAIL)
        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.SOURCES_REFRESH_FAIL,
                payload=err_payload,
                error=str(e),
                exc_info=True,
            )
            st.error(UiText.ERROR_SOURCES_LOAD_FAIL.format(error=e))

    def select_all_sources_action():
        log_with_payload(logging.INFO, LogMsg.SOURCES_SELECT_ALL_CLICKED)
        all_sources_list = st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, [])

        valid_sources = [
            s for s in all_sources_list if s != UiText.ERROR_SOURCES_DISPLAY
        ]

        st.session_state[SessionStateKeys.LOADED_SOURCES] = valid_sources

        if SessionStateKeys.ADV_SOURCE_SELECTOR in st.session_state:
            st.session_state[SessionStateKeys.ADV_SOURCE_SELECTOR] = valid_sources
        log_with_payload(
            logging.INFO, LogMsg.SOURCES_SET_ALL, source_count=len(valid_sources)
        )

    def update_selected_recipe():
        """Callback function for the recipe selector dropdown."""

        new_selection = st.session_state.get(SessionStateKeys.RECIPE_SELECTOR_DROPDOWN)

        st.session_state[SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL] = (
            new_selection
        )
        log_with_payload(
            logging.DEBUG, LogMsg.RECIPE_SELECTION_CHANGED, selection=new_selection
        )

    search_col, results_col = st.columns([2, 3])
    defaults = config.defaults
    with search_col:
        st.subheader(UiText.SUBHEADER_INPUTS_FILTERS)

        st.text_area(
            UiText.LABEL_INGREDIENTS,
            height=100,
            key=SessionStateKeys.ADV_INGREDIENTS_INPUT,
            value=st.session_state.get(
                SessionStateKeys.LOADED_INGREDIENTS_TEXT, defaults.ingredients_text
            ),
            placeholder=UiText.PLACEHOLDER_INGREDIENTS,
        )

        st.number_input(
            UiText.LABEL_MIN_MATCHES,
            min_value=0,
            step=1,
            key=SessionStateKeys.ADV_MIN_ING_MATCHES_INPUT,
            value=st.session_state.get(
                SessionStateKeys.LOADED_MIN_ING_MATCHES, defaults.min_ing_matches
            ),
            help=UiText.HELP_MIN_MATCHES,
        )

        st.number_input(
            UiText.LABEL_MAX_STEPS,
            min_value=0,
            step=1,
            key=SessionStateKeys.ADV_MAX_STEPS_INPUT,
            value=st.session_state.get(
                SessionStateKeys.LOADED_MAX_STEPS, defaults.max_steps
            ),
        )

        with st.expander(UiText.EXPANDER_ADV_OPTIONS):
            st.text_area(
                UiText.LABEL_MUST_USE,
                height=75,
                key=SessionStateKeys.ADV_MUST_USE_INPUT,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_MUST_USE_TEXT, defaults.must_use_text
                ),
                placeholder=UiText.PLACEHOLDER_MUST_USE,
            )
            st.text_area(
                UiText.LABEL_EXCLUDE_INGS,
                height=75,
                key=SessionStateKeys.ADV_EXCLUDED_INPUT,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_EXCLUDED_TEXT, defaults.excluded_text
                ),
                placeholder=UiText.PLACEHOLDER_EXCLUDE_INGS,
            )
            st.text_area(
                UiText.LABEL_KEYWORDS_INCLUDE,
                height=75,
                key=SessionStateKeys.ADV_KEYWORDS_INCLUDE_INPUT,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_KEYWORDS_INCLUDE, defaults.keywords_include
                ),
                placeholder=UiText.PLACEHOLDER_KEYWORDS_INCLUDE,
            )
            st.text_area(
                UiText.LABEL_KEYWORDS_EXCLUDE,
                height=75,
                key=SessionStateKeys.ADV_KEYWORDS_EXCLUDE_INPUT,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_KEYWORDS_EXCLUDE, defaults.keywords_exclude
                ),
                placeholder=UiText.PLACEHOLDER_KEYWORDS_EXCLUDE,
            )

        with st.expander(UiText.EXPANDER_TAG_FILTERS):
            tag_filter_options = [TagFilterMode.AND, TagFilterMode.OR]

            current_mode_enum = st.session_state.get(
                SessionStateKeys.LOADED_TAG_FILTER_MODE, default_tag_filter_mode_enum
            )

            st.radio(
                UiText.LABEL_TAG_FILTER_MODE,
                options=tag_filter_options,
                key=SessionStateKeys.ADV_TAG_FILTER_MODE_INPUT,
                index=tag_filter_options.index(current_mode_enum),
                horizontal=True,
                format_func=lambda mode: mode.value,
            )

            include_col, exclude_col = st.columns(2)
            with include_col:
                st.write(UiText.LABEL_INCLUDE_TAGS)

                for cat_key, widget_key, loaded_key in [
                    (
                        CategoryKeys.COURSE,
                        SessionStateKeys.ADV_COURSE_FILTER_INPUT,
                        SessionStateKeys.LOADED_COURSE_FILTER,
                    ),
                    (
                        CategoryKeys.MAIN_INGREDIENT,
                        SessionStateKeys.ADV_MAIN_ING_FILTER_INPUT,
                        SessionStateKeys.LOADED_MAIN_ING_FILTER,
                    ),
                    (
                        CategoryKeys.DISH_TYPE,
                        SessionStateKeys.ADV_DISH_TYPE_FILTER_INPUT,
                        SessionStateKeys.LOADED_DISH_TYPE_FILTER,
                    ),
                    (
                        CategoryKeys.RECIPE_TYPE,
                        SessionStateKeys.ADV_RECIPE_TYPE_FILTER_INPUT,
                        SessionStateKeys.LOADED_RECIPE_TYPE_FILTER,
                    ),
                    (
                        CategoryKeys.CUISINE,
                        SessionStateKeys.ADV_CUISINE_FILTER_INPUT,
                        SessionStateKeys.LOADED_CUISINE_FILTER,
                    ),
                ]:
                    st.multiselect(
                        cat_key.value.replace("_", " ").title(),
                        options=config.category_choices.get(cat_key, []),
                        key=widget_key,
                        default=st.session_state.get(loaded_key, []),
                    )
            with exclude_col:
                st.write(UiText.LABEL_EXCLUDE_TAGS)
                for cat_key, widget_key, loaded_key in [
                    (
                        CategoryKeys.COURSE,
                        SessionStateKeys.ADV_EXCLUDE_COURSE_FILTER_INPUT,
                        SessionStateKeys.LOADED_EXCLUDE_COURSE_FILTER,
                    ),
                    (
                        CategoryKeys.MAIN_INGREDIENT,
                        SessionStateKeys.ADV_EXCLUDE_MAIN_ING_FILTER_INPUT,
                        SessionStateKeys.LOADED_EXCLUDE_MAIN_ING_FILTER,
                    ),
                    (
                        CategoryKeys.DISH_TYPE,
                        SessionStateKeys.ADV_EXCLUDE_DISH_TYPE_FILTER_INPUT,
                        SessionStateKeys.LOADED_EXCLUDE_DISH_TYPE_FILTER,
                    ),
                    (
                        CategoryKeys.RECIPE_TYPE,
                        SessionStateKeys.ADV_EXCLUDE_RECIPE_TYPE_FILTER_INPUT,
                        SessionStateKeys.LOADED_EXCLUDE_RECIPE_TYPE_FILTER,
                    ),
                    (
                        CategoryKeys.CUISINE,
                        SessionStateKeys.ADV_EXCLUDE_CUISINE_FILTER_INPUT,
                        SessionStateKeys.LOADED_EXCLUDE_CUISINE_FILTER,
                    ),
                ]:
                    st.multiselect(
                        cat_key.value.replace("_", " ").title() + " ",
                        options=config.category_choices.get(cat_key, []),
                        key=widget_key,
                        default=st.session_state.get(loaded_key, []),
                    )

            st.slider(
                UiText.LABEL_USER_COVERAGE,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                format=FormatStrings.SLIDER_PERCENT,
                key=SessionStateKeys.ADV_USER_COVERAGE_SLIDER,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_USER_COVERAGE,
                    defaults.user_coverage * 100.0,
                ),
                help=UiText.HELP_USER_COVERAGE,
            )
            st.slider(
                UiText.LABEL_RECIPE_COVERAGE,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                format=FormatStrings.SLIDER_PERCENT,
                key=SessionStateKeys.ADV_RECIPE_COVERAGE_SLIDER,
                value=st.session_state.get(
                    SessionStateKeys.LOADED_RECIPE_COVERAGE,
                    defaults.recipe_coverage * 100.0,
                ),
                help=UiText.HELP_RECIPE_COVERAGE,
            )

        with st.expander(UiText.EXPANDER_SOURCE_SELECT):
            available_sources = [
                s
                for s in st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, [])
                if s != UiText.ERROR_SOURCES_DISPLAY
            ]

            default_loaded_sources = [
                s
                for s in st.session_state.get(SessionStateKeys.LOADED_SOURCES, [])
                if s in available_sources
            ]
            st.multiselect(
                UiText.LABEL_SELECT_SOURCES,
                options=available_sources,
                key=SessionStateKeys.ADV_SOURCE_SELECTOR,
                default=default_loaded_sources,
            )
            scol1, scol2 = st.columns(2)
            with scol1:
                st.button(
                    UiText.BUTTON_REFRESH_SOURCES,
                    on_click=refresh_sources_action,
                    use_container_width=True,
                )
            with scol2:
                st.button(
                    UiText.BUTTON_SELECT_ALL_SOURCES,
                    on_click=select_all_sources_action,
                    use_container_width=True,
                )

        with st.expander(UiText.EXPANDER_USER_PROFILES):
            st.text_input(
                UiText.LABEL_USERNAME,
                key=SessionStateKeys.USERNAME_INPUT,
                value=defaults.username,
            )
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                st.button(
                    UiText.BUTTON_SAVE_PROFILE,
                    on_click=save_profile_action,
                    use_container_width=True,
                )
            with pcol2:
                st.button(
                    UiText.BUTTON_LOAD_PROFILE,
                    on_click=load_profile_action,
                    use_container_width=True,
                )

            st.markdown(
                st.session_state.get(
                    SessionStateKeys.PROFILE_STATUS_MESSAGE, defaults.profile_message
                ),
                unsafe_allow_html=True,
            )

        st.button(
            UiText.BUTTON_SEARCH_RECIPES,
            on_click=run_advanced_search,
            type="primary",
            use_container_width=True,
        )

    with results_col:
        st.subheader(UiText.SUBHEADER_RESULTS)

        st.markdown(UiText.MARKDOWN_MATCHING_RECIPES)

        results_df = st.session_state.get(SessionStateKeys.ADVANCED_SEARCH_RESULTS_DF)
        error_html = st.session_state.get(
            SessionStateKeys.ADVANCED_SEARCH_RESULTS_HTML, defaults.profile_message
        )

        if results_df is not None and not results_df.empty:
            st.dataframe(results_df, height=300, use_container_width=True)
        elif error_html != defaults.profile_message:
            st.markdown(error_html, unsafe_allow_html=True)
        else:
            st.markdown(defaults.profile_message, unsafe_allow_html=True)

        st.markdown("---")

        st.markdown(UiText.MARKDOWN_SELECT_RECIPE)

        recipe_mapping = st.session_state.get(
            SessionStateKeys.ADVANCED_SEARCH_MAPPING, {}
        )
        recipe_options = list(recipe_mapping.keys())

        current_selection_label = st.session_state.get(
            SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL
        )

        selected_index = 0
        if current_selection_label and current_selection_label in recipe_options:
            try:
                selected_index = recipe_options.index(current_selection_label)
            except ValueError:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.RECIPE_LABEL_NOT_FOUND_IN_OPTIONS,
                    label=current_selection_label,
                )
                selected_index = 0
        elif recipe_options:
            selected_index = 0

        if not recipe_options:
            st.selectbox(
                UiText.SELECTBOX_LABEL_RECIPE,
                options=[defaults.no_recipes_found],
                index=0,
                disabled=True,
                key=SessionStateKeys.RECIPE_SELECTOR_DROPDOWN + "_disabled",
            )

            if (
                st.session_state.get(SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL)
                is not None
            ):
                st.session_state[SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL] = None
        else:
            st.selectbox(
                UiText.SELECTBOX_LABEL_RECIPE,
                options=recipe_options,
                index=selected_index,
                key=SessionStateKeys.RECIPE_SELECTOR_DROPDOWN,
                on_change=update_selected_recipe,
            )

        st.markdown(UiText.MARKDOWN_RECIPE_DETAILS)

        selected_label_for_display = st.session_state.get(
            SessionStateKeys.ADVANCED_SELECTED_RECIPE_LABEL
        )

        if selected_label_for_display and selected_label_for_display in recipe_mapping:
            recipe_content_wrapper = recipe_mapping.get(selected_label_for_display)
            if recipe_content_wrapper and isinstance(
                recipe_content_wrapper.get(RecipeKeys.RECIPE), dict
            ):
                recipe_markdown = display_recipe_markdown(
                    recipe_content_wrapper[RecipeKeys.RECIPE]
                )
                st.markdown(recipe_markdown)
            else:
                log_with_payload(
                    logging.ERROR,
                    LogMsg.RECIPE_CONTENT_MISSING,
                    label=selected_label_for_display,
                )
                st.warning(
                    UiText.MSG_COULD_NOT_DISPLAY.format(
                        label=selected_label_for_display
                    )
                )
        elif recipe_options:
            st.markdown(UiText.MSG_SELECT_RECIPE_PROMPT, unsafe_allow_html=True)
        else:
            st.markdown(UiText.MSG_NO_RESULTS_FOUND_ADV, unsafe_allow_html=True)


elif st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_SIMPLE:
    st.header(UiText.HEADER_SIMPLE_SEARCH)
    defaults = config.defaults

    def update_simple_selected_recipe():
        """Callback function for the simple recipe selector dropdown."""

        new_selection = st.session_state.get(
            SessionStateKeys.RECIPE_SELECTOR_DROPDOWN + "_simple"
        )

        st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = new_selection
        log_with_payload(
            logging.DEBUG,
            LogMsg.SIMPLE_RECIPE_SELECTION_CHANGED,
            selection=new_selection,
        )

    def run_simple_search_action():
        log_with_payload(logging.INFO, LogMsg.SIMPLE_SEARCH_CLICKED)
        query_text = st.session_state.get(
            SessionStateKeys.SIMPLE_QUERY_INPUT, MiscValues.EMPTY
        ).strip()

        if not query_text:
            st.warning(UiText.WARN_EMPTY_QUERY)
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML] = (
                UiText.MSG_SIMPLE_QUERY_PROMPT
            )
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_MAPPING] = {}
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF] = None
            st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = None
            return

        all_sources_list = [
            s
            for s in st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, [])
            if s != UiText.ERROR_SOURCES_DISPLAY
        ]

        query_params = dict(
            user_ingredients=[],
            tag_filters={},
            excluded_tags={},
            min_ing_matches=0,
            forbidden_ingredients=[],
            must_use=[],
            tag_filter_mode=TagFilterMode.AND,
            max_steps=0,
            user_coverage_req=0.0,
            recipe_coverage_req=0.0,
            keywords_to_include=[k.strip() for k in query_text.split() if k.strip()],
            keywords_to_exclude=[],
            sources=all_sources_list,
        )

        try:
            params_json = json.dumps(
                query_params, indent=config.json_indent, default=str
            )
        except TypeError:
            params_json = LogMsg.SERIALIZE_PARAMS_FAIL

        payload = SearchPayload(query_params=params_json)
        log_with_payload(
            logging.INFO,
            LogMsg.SIMPLE_SEARCH_PARAMS,
            payload=payload,
            params_json=params_json,
        )

        try:
            results = query_top_k(**query_params)
        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.SIMPLE_SEARCH_QUERY_ERROR,
                payload=err_payload,
                search_payload=payload,
                exc_info=True,
            )
            st.error(UiText.ERROR_DURING_SIMPLE_SEARCH.format(error=e))

            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML] = (
                UiText.ERROR_DURING_SIMPLE_SEARCH.format(error=e)
            )
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_MAPPING] = {}
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF] = None
            st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = None
            return

        if not results:
            log_with_payload(
                logging.INFO, LogMsg.SIMPLE_SEARCH_NO_RESULTS, payload=payload
            )
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML] = (
                UiText.MSG_SIMPLE_NO_RESULTS.format(query_text=query_text)
            )
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_MAPPING] = {}
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF] = None
            st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = None
        else:
            payload.result_count = len(results)
            log_with_payload(
                logging.INFO,
                LogMsg.SIMPLE_SEARCH_RESULTS_COUNT,
                payload=payload,
                count=len(results),
            )

            simple_results_data_for_df = []
            simple_mapping = {}
            for r in results:
                url = r.get(RecipeKeys.URL, UiText.DEFAULT_RECIPE_URL)
                title = r.get(RecipeKeys.TITLE, UiText.DEFAULT_RECIPE_TITLE)
                recipe_content_dict = r.get(RecipeKeys.RECIPE, {})

                simple_df_row = {
                    "Recipe Title": title,
                    "Source / URL": url,
                }
                simple_results_data_for_df.append(simple_df_row)

                label = title
                original_label = label
                count = 1
                while label in simple_mapping:
                    label = FormatStrings.RECIPE_LABEL_DUPLICATE.format(
                        original_label=original_label, count=count
                    )
                    count += 1
                simple_mapping[label] = {
                    RecipeKeys.URL: url,
                    RecipeKeys.RECIPE: recipe_content_dict,
                }

            simple_results_df = pd.DataFrame(simple_results_data_for_df)

            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF] = (
                simple_results_df
            )
            st.session_state[SessionStateKeys.SIMPLE_SEARCH_MAPPING] = simple_mapping

            st.session_state[SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML] = (
                MiscValues.EMPTY
            )

            first_label = next(iter(simple_mapping.keys()), None)
            st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = (
                first_label
            )

            log_with_payload(
                logging.INFO,
                LogMsg.SIMPLE_SEARCH_PROCESSED,
                payload=payload,
                df_shape=str(simple_results_df.shape),
            )

    st.text_input(
        UiText.LABEL_SIMPLE_QUERY,
        key=SessionStateKeys.SIMPLE_QUERY_INPUT,
        value=st.session_state.get(
            SessionStateKeys.SIMPLE_QUERY_INPUT, defaults.simple_query
        ),
        placeholder=UiText.PLACEHOLDER_SIMPLE_QUERY,
    )

    st.button(
        UiText.BUTTON_SIMPLE_SEARCH, on_click=run_simple_search_action, type="primary"
    )

    st.markdown("---")
    st.markdown(UiText.MARKDOWN_SIMPLE_RESULTS)

    simple_results_df = st.session_state.get(SessionStateKeys.SIMPLE_SEARCH_RESULTS_DF)
    error_html = st.session_state.get(
        SessionStateKeys.SIMPLE_SEARCH_RESULTS_HTML, defaults.profile_message
    )

    if simple_results_df is not None and not simple_results_df.empty:
        st.dataframe(simple_results_df, height=300, use_container_width=True)
    elif error_html != defaults.profile_message:
        st.markdown(error_html, unsafe_allow_html=True)
    else:
        st.markdown(UiText.MSG_SIMPLE_QUERY_PROMPT, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("##### Select Recipe for Details")  # Add details section title

    simple_recipe_mapping = st.session_state.get(
        SessionStateKeys.SIMPLE_SEARCH_MAPPING, {}
    )
    simple_recipe_options = list(simple_recipe_mapping.keys())

    current_simple_selection_label = st.session_state.get(
        SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL
    )

    selected_simple_index = 0
    if (
        current_simple_selection_label
        and current_simple_selection_label in simple_recipe_options
    ):
        try:
            selected_simple_index = simple_recipe_options.index(
                current_simple_selection_label
            )
        except ValueError:
            selected_simple_index = 0
    elif simple_recipe_options:
        selected_simple_index = 0

    if not simple_recipe_options:
        st.selectbox(
            UiText.SELECTBOX_LABEL_RECIPE,
            options=[defaults.no_recipes_found],
            index=0,
            disabled=True,
            key=SessionStateKeys.RECIPE_SELECTOR_DROPDOWN + "_simple_disabled",
        )

        if (
            st.session_state.get(SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL)
            is not None
        ):
            st.session_state[SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL] = None
    else:
        st.selectbox(
            UiText.SELECTBOX_LABEL_RECIPE,
            options=simple_recipe_options,
            index=selected_simple_index,
            key=SessionStateKeys.RECIPE_SELECTOR_DROPDOWN + "_simple",
            on_change=update_simple_selected_recipe,
        )

    st.markdown("##### Recipe Details")  # Add details title

    selected_simple_label_for_display = st.session_state.get(
        SessionStateKeys.SIMPLE_SELECTED_RECIPE_LABEL
    )

    if (
        selected_simple_label_for_display
        and selected_simple_label_for_display in simple_recipe_mapping
    ):
        recipe_content_wrapper = simple_recipe_mapping.get(
            selected_simple_label_for_display
        )
        if recipe_content_wrapper and isinstance(
            recipe_content_wrapper.get(RecipeKeys.RECIPE), dict
        ):
            recipe_markdown = display_recipe_markdown(
                recipe_content_wrapper[RecipeKeys.RECIPE]
            )
            st.markdown(recipe_markdown)
        else:
            log_with_payload(
                logging.ERROR,
                LogMsg.RECIPE_CONTENT_MISSING,
                label=selected_simple_label_for_display,
            )
            st.warning(
                UiText.MSG_COULD_NOT_DISPLAY.format(
                    label=selected_simple_label_for_display
                )
            )
    elif simple_recipe_options:
        st.markdown(UiText.MSG_SELECT_RECIPE_PROMPT, unsafe_allow_html=True)
    else:
        st.markdown(
            UiText.MSG_SIMPLE_NO_RESULTS.format(query_text=query_text),
            unsafe_allow_html=True,
        )


elif st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_LIBRARY:

    def on_book_select():
        """Streamlit callback: download + convert the newly-selected book with a spinner."""
        label = st.session_state[SessionStateKeys.LIBRARY_BOOK_SELECTOR]
        if not label:
            return
        mapping = st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING]
        details = mapping[label]
        with st.spinner(UiText.SPINNER_PREPARING_BOOK.format(label=label)):
            local_file = download_gdrive_file(
                details[GDriveKeys.FILE_ID],
                details[GDriveKeys.FILE_NAME],
                config.book_dir,
            )
            pdf = to_pdf_cached(local_file, config.temp_dir)
        st.session_state["_prepared_pdf"] = pdf

    st.header(UiText.HEADER_LIBRARY)
    ebook_convert_available = check_ebook_convert_availability()
    if not ebook_convert_available:
        st.warning(UiText.WARN_EBOOK_CONVERT_MISSING)

    def refresh_book_list():
        log_with_payload(logging.INFO, LogMsg.LIBRARY_REFRESH_CLICKED)

        list_drive_books_cached.clear()
        to_pdf_cached.clear()

        try:
            new_labels, new_mapping = list_drive_books_cached()
            st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING] = new_mapping

            current_selection = st.session_state.get(
                SessionStateKeys.LIBRARY_BOOK_SELECTOR
            )
            if current_selection and current_selection not in new_mapping:
                st.session_state[SessionStateKeys.LIBRARY_BOOK_SELECTOR] = None
                log_with_payload(
                    logging.INFO,
                    LogMsg.LIBRARY_SELECTION_RESET,
                    selection=current_selection,
                )
            log_with_payload(logging.INFO, LogMsg.LIBRARY_LIST_REFRESHED)

        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.LIBRARY_LIST_REFRESH_FAIL,
                payload=err_payload,
                error=str(e),
                exc_info=True,
            )
            st.error(UiText.ERROR_BOOKS_LOAD_FAIL.format(error=e))

    book_mapping_state = st.session_state.get(SessionStateKeys.LIBRARY_BOOK_MAPPING, {})
    book_options = list(book_mapping_state.keys())
    display_book_options = [
        opt for opt in book_options if opt != UiText.ERROR_BOOKS_DISPLAY
    ]

    if not display_book_options:
        if UiText.ERROR_BOOKS_DISPLAY in book_options:
            st.error(UiText.ERROR_BOOKS_DISPLAY)
        else:
            st.warning(UiText.WARN_NO_BOOKS_FOUND)
    else:
        current_book_selection = st.session_state.get(
            SessionStateKeys.LIBRARY_BOOK_SELECTOR
        )
        current_index = 0
        if current_book_selection and current_book_selection in display_book_options:
            try:
                current_index = display_book_options.index(current_book_selection)
            except ValueError:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.LIBRARY_BOOK_SELECTION_INVALID,
                    selection=current_book_selection,
                )
                current_index = 0
        elif display_book_options:
            current_index = 0

        selected_book_label = st.selectbox(
            UiText.SELECTBOX_LABEL_BOOK,
            options=display_book_options,
            key=SessionStateKeys.LIBRARY_BOOK_SELECTOR,
            index=current_index,
            on_change=on_book_select,
        )
        st.session_state["_book_placeholder"] = st.empty()
        if selected_book_label:
            st.markdown("---")

            placeholder = st.empty()
            payload = LibraryPayload(label=selected_book_label)

            placeholder.markdown(
                UiText.SPINNER_PREPARING_BOOK.format(label=selected_book_label),
                unsafe_allow_html=True,
            )

            book_details = book_mapping_state.get(selected_book_label)

            if not book_details:
                log_with_payload(
                    logging.ERROR,
                    LogMsg.LIBRARY_DETAILS_NOT_FOUND,
                    payload=payload,
                    label=selected_book_label,
                )
                placeholder.error(
                    UiText.ERROR_BOOK_DETAILS_NOT_FOUND.format(
                        label=selected_book_label
                    )
                )
            else:
                file_id = book_details.get(GDriveKeys.FILE_ID)
                file_name = book_details.get(GDriveKeys.FILE_NAME)
                book_dir_path = config.book_dir

                payload.gdrive_id = file_id

                if book_dir_path and file_name:
                    payload.file_path = os.path.join(book_dir_path, file_name)
                else:
                    payload.file_path = None

                if not file_id or not file_name or not book_dir_path:
                    log_with_payload(
                        logging.ERROR, LogMsg.LIBRARY_MISSING_DETAILS, payload=payload
                    )
                    placeholder.error(UiText.ERROR_BOOK_MISSING_DETAILS)
                else:
                    with st.spinner(
                        UiText.SPINNER_PROCESSING_BOOK.format(filename=file_name)
                    ):
                        local_file_path = download_gdrive_file(
                            file_id, file_name, book_dir_path
                        )

                    if local_file_path:
                        try:
                            pdf_path = to_pdf_cached(local_file_path, config.temp_dir)

                            payload.file_path = pdf_path

                            log_with_payload(
                                logging.INFO,
                                LogMsg.LIBRARY_ENCODING_PDF,
                                payload=payload,
                                pdf_path=pdf_path,
                            )

                            pdf_path = st.session_state.get("_prepared_pdf")
                            if pdf_path:
                                b64 = base64.b64encode(
                                    open(pdf_path, "rb").read()
                                ).decode("utf-8")
                                html = f'''
                                <style>
                                  /* Inline styles inside the iframe */
                                  #openBtn {{
                                    background-color: var(--primary-color) !important;
                                    color: white !important;
                                    border: none !important;
                                    border-radius: 4px !important;
                                    font-size: 14px !important;
                                    font-weight: 600 !important;
                                    padding: 0.5em 1em !important;
                                    cursor: pointer !important;
                                    display: inline-flex;
                                    align-items: center;
                                    gap: 0.25em;
                                  }}
                                  #openBtn:hover {{
                                    background-color: var(--primary-color-dark) !important;
                                  }}
                                </style>

                                <button id="openBtn">📖 {UiText.BUTTON_OPEN_BOOK_PDF}</button>

                                <script>
                                  document.getElementById("openBtn").onclick = () => {{
                                    const bin = atob("{b64}");
                                    const len = bin.length;
                                    const bytes = new Uint8Array(len);
                                    for (let i = 0; i < len; i++) {{
                                      bytes[i] = bin.charCodeAt(i);
                                    }}
                                    const blob = new Blob([bytes], {{ type: "application/pdf" }});
                                    const url = URL.createObjectURL(blob);
                                    window.open(url, "_blank");
                                  }};
                                </script>
                                '''

                                components.html(html, height=60)

                        except FileNotFoundError as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_PDF_CONVERT_ERROR,
                                payload=err_payload,
                                library_payload=payload,
                                path=local_file_path,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )
                            placeholder.error(
                                UiText.ERROR_BOOK_FILE_NOT_FOUND.format(
                                    filename=file_name
                                )
                            )
                        except (
                            ValueError,
                            RuntimeError,
                            subprocess.CalledProcessError,
                        ) as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_CONVERT_LINK_FAIL,
                                payload=err_payload,
                                library_payload=payload,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )

                            placeholder.error(
                                UiText.ERROR_BOOK_CONVERT_LINK.format(
                                    label=selected_book_label, error=e
                                )
                            )
                        except Exception as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_CONVERT_LINK_FAIL,
                                payload=err_payload,
                                library_payload=payload,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )
                            placeholder.error(
                                UiText.ERROR_BOOK_CONVERT_LINK.format(
                                    label=selected_book_label, error=e
                                )
                            )
                    else:
                        placeholder.empty()
                        log_with_payload(
                            logging.ERROR,
                            LogMsg.LIBRARY_DOWNLOAD_FIND_FAIL,
                            payload=payload,
                            label=selected_book_label,
                        )
                        placeholder.error(
                            UiText.ERROR_BOOK_DOWNLOAD_FAIL.format(
                                label=selected_book_label
                            )
                        )

    st.button(UiText.BUTTON_REFRESH_BOOKS, on_click=refresh_book_list)


log_with_payload(logging.INFO, LogMsg.SCRIPT_EXEC_FINISHED)
