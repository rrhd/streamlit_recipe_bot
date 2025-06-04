import base64
import logging
from enum import StrEnum
from typing import Any

from streamlit.components import v1 as components

from constants import RecipeKeys, MiscValues, LogMsg
from log_utils import ErrorPayload, log_with_payload


class UiText(StrEnum):
    """Static UI text elements like labels, titles, messages."""

    WARNING_NO_INGREDIENTS_FROM_IMAGE = "No ingredients found."
    SUCCESS_INGREDIENTS_FROM_IMAGE = "✓ {count} Ingredients added"
    SPINNER_PROCESSING_IMAGE = "Detecting ingredients…"
    LABEL_FILE_INPUT = "…or upload an image"
    LABEL_CAMERA_INPUT = "Take a picture"
    PREPARING_BOOK = "Preparing '{label}'…"
    SPINNER_LOADING_PDF = "Loading PDF..."
    BUTTON_OPEN_BOOK_PDF = "Open Book PDF"
    PAGE_TITLE = "Recipe Finder"
    TAB_ABOUT = "About"
    TAB_ADVANCED = "Advanced Search"
    TAB_SIMPLE = "Simple Search"
    TAB_LIBRARY = "Library"
    TAB_CHAT = "Chatbot"
    TAB_MISTRAL = "Mistral Docs"
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
        - **Chatbot Tab:**
          Chat with an assistant that can understand free-form requests like "I feel like a summery treat" or lists of ingredients. It may ask follow-up questions and then search for suitable recipes.
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
    BUTTON_RESET_FIELDS = "Reset Fields"
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
from mistralai import Mistral, UserMessage
from mistralai.models import ImageURLChunk, TextChunk

client = Mistral(api_key="YOUR_KEY")
messages = [
    UserMessage(content=[
        ImageURLChunk(image_url={"url": "https://example.com/img.jpg"}),
        TextChunk(text="What's shown here?")
    ])
]
resp = client.chat.complete(model="mistral-large-latest", messages=messages)
    """
    EXAMPLE_EMBEDDINGS = """\
from mistralai import Mistral

client = Mistral(api_key="YOUR_KEY")
emb = client.embeddings.create(model="mistral-embed", inputs=["hello world"])
    """
    EXAMPLE_STREAMING = """\
from mistralai import Mistral, UserMessage

client = Mistral(api_key="YOUR_KEY")
for chunk in client.chat.stream(
    model="mistral-large-latest", messages=[UserMessage(content="Hello")]
):
    print(chunk.data.choices[0].delta.content, end="")
    """
    TOOL_ARGS_INVALID = "I couldn't understand that search request."
    EXPANDER_SEARCH_RESULTS = "Search Results"
    COLUMN_RECIPE_TITLE = "Recipe Title"
    COLUMN_SOURCE_URL = "Source / URL"
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
    ERROR_EBOOK_CONVERT_FAIL_RUNTIME = "The 'epub2pdf' command was not found. Please ensure the 'epub2pdf' Python package is installed correctly."
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
