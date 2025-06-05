import os
import tempfile
from pathlib import Path
from enum import StrEnum, IntEnum
from mistralai.models.function import Function
from mistralai.models.tool import Tool, ToolTypes

_PROMPT_DIR = Path(__file__).parent / "prompts"
HELP_MD = Path(__file__).parent / "help.md"


class FileExt(StrEnum):
    """File extensions."""

    GZ = ".gz"
    PDF = ".pdf"
    EPUB = ".epub"
    MOBI = ".mobi"


class FileMode(StrEnum):
    """File open modes."""

    READ_BINARY = "rb"
    WRITE_BINARY = "wb"




class CategoryKeys(StrEnum):
    COURSE = "course"
    MAIN_INGREDIENT = "main_ingredient"
    DISH_TYPE = "dish_type"
    RECIPE_TYPE = "recipe_type"
    CUISINE = "cuisine"
    HOLIDAY = "holiday"


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
    BYTES_UNDECODABLE = "<Bytes length={length}, undecodable>"
    TRUNCATION_SUFFIX = "..."




class MiscValues(StrEnum):
    """Miscellaneous constant values."""

    TEMP_DIR = tempfile.gettempdir()
    NEWLINE = "\n"
    SPACE = " "
    EMPTY = ""
    HTTP_PREFIX = "http://"
    HTTPS_PREFIX = "https://"
    DEFAULT_STEP = "?"
    CACHE_DIR = "recipe_cache"


class ConfigKeys(StrEnum):
    """Keys for configuration values stored directly."""

    PROFILE_DB_PATH = "profiles_db.sqlite"
    BOOK_DIR_RELATIVE = "cookbooks"
    DOWNLOAD_DEST_DIR = "data"
    RECIPE_DB_FILENAME = "recipe_links.db.gz"


class TagFilterMode(StrEnum):
    AND = "AND"
    OR = "OR"


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


class SupabaseEnv(StrEnum):
    """Environment variable keys for Supabase configuration."""

    URL = "SUPABASE_URL"
    API_KEY = "SUPABASE_API_KEY"
    DB_URL = "SUPABASE_DB_URL"
    ACCESS_TOKEN = "SUPABASE_ACCESS_TOKEN"
    ORG_ID = "SUPABASE_ORG_ID"


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
    SQL_CREATE_PROFILES_PG = """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload_base64 TEXT NOT NULL
        );
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


class ToolNames(StrEnum):
    """Executable tool names."""

    EBOOK_CONVERT = "ebook-convert"


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
        "Convert completed successfully for {source_path}. Output:\n{output}"
    )
    EBOOK_CONVERT_OUTPUT_MISSING = (
        "Convert ran but output file not found: {output_pdf_path}"
    )
    EBOOK_CONVERT_CMD_NOT_FOUND = "`ebook-convert` command not found. Is Calibre installed and in the system PATH?"
    EBOOK_CONVERT_FAILED = (
        "Convert failed for {source_path}. Error: {error}\nStderr:\n{stderr}"
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
    ADV_SEARCH_RESET_CLICKED = "Advanced search reset button clicked."
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


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"


class ContentType(StrEnum):
    TEXT = "text"
    IMAGE_URL = "image_url"


class UserPrompt(StrEnum):
    PROCESS = "Process images"


class ModelName(StrEnum):
    VISION = "mistral-small-2503"
    CHAT_SMALL = "mistral-small-latest"
    CHAT_LARGE = "mistral-large-latest"
    EMBED_BASE = "mistral-embed"


class ToolText(StrEnum):
    """Text for tool descriptions and parameters."""

    SEARCH_DESC = "Search and rank recipes by keywords"
    QUERY_DESC = "Keywords for searching recipes"
    RANK_DESC = "Return a new ordering for the given recipes"
    ORDER_PARAM = "New ordering of recipe numbers"


class ToolCall(StrEnum):
    SEARCH_RECIPES = "search_recipes"
    RANK_RECIPES = "rank_recipes"


class AgentText(StrEnum):
    """Prompts for the chatbot and ranking agents."""

    RERANK_SYSTEM = (_PROMPT_DIR / "rerank_system.md").read_text("utf-8")
    RERANK_USER = (
        "Given the user's intent '{query}', order the following recipe URLs by relevance."
    )

    CHATBOT_SYSTEM = (_PROMPT_DIR / "chatbot_system.md").read_text("utf-8")

    PARSE_SYSTEM = (_PROMPT_DIR / "parse_system.md").read_text("utf-8")
    PARSE_USER = "Request: {query}"


class CacheLimit(IntEnum):
    MAX_TOKENS = 4096
    MAX_IMAGES = 8


class SearchLimit(IntEnum):
    RESULTS = 5


class Suffix(StrEnum):
    ELLIPSIS = "…"


class PathName(StrEnum):
    RECIPE_DB = "recipe_links.db"
    CACHE_DIR = "recipe_cache"
    SPACY_MODEL = "taste_model/model-best"


class NumericDefault(IntEnum):
    DEDUP_THRESHOLD = 95


class DefaultDate(StrEnum):
    DB_MISSING = "2000-01-01"
