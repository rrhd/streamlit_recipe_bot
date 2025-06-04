# Streamlit Recipe Finder

Streamlit Recipe Finder is a web application that lets you search a large recipe database using either advanced filters or simple keyword queries. It also provides a small cookbook library that is synchronized from Google Drive. The app loads its configuration from environment variables or `st.secrets` and stores user profiles in a local SQLite database.  All tunable settings are defined via Pydantic models.

## Features

- **Advanced recipe search** – Filter recipes by ingredients, cuisine tags, maximum steps, keywords, coverage requirements and more. The user interface explains each option in detail, for example how to set minimum ingredient matches or select sources from Google Drive.
- **Simple keyword search** – A streamlined page for quick searches over the recipe title and description.
- **Cookbook library** – Browse cookbooks stored on Google Drive. Non‑PDF files are converted using the `ebook-convert` tool so they can be opened directly in the browser.
- **Profile management** – Save and load search settings under a username so frequent queries can be reused.
- **Ingredient detection from images** – Upload or capture a photo to extract ingredient names using an external vision model.
- **Google Drive integration** – At startup the app downloads essential data files from Drive and keeps them cached locally.
- **Structured logging and caching** – Logs include structured payloads for important operations and expensive queries are cached to disk.

## Getting Started

1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.streamlit/secrets.toml` file containing your Google service account credentials and Drive folder ID. The keys are named `google_service_account_*` and `google_drive.folder_id` as referenced in the code.
3. Optionally set environment variables in an `.env` file for any additional configuration values defined in `config.py`.
4. Run the application:
   ```bash
   streamlit run streamlit_app.py
   ```

On startup the script calls `download_essential_files()` and `init_profile_db()` to ensure required data is present before rendering the UI. These calls can be seen in `streamlit_app.py`:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

download_essential_files()

init_profile_db()
```

## Searching for Recipes

The advanced search page exposes many options, including ingredient lists, tag filters, keyword inclusion or exclusion, and coverage sliders. The UI text describing these options is defined in `ui_helpers.py`:
```python
        - **Library Tab:**
          Browse cookbooks downloaded from Google Drive. Requires `ebook-convert` (from Calibre) to be installed and in the PATH for non-PDF files.
```

When you click **Search Recipes**, the app compiles the parameters and calls `query_top_k()` from `query_top_k.py`. This function retrieves candidate recipes via SQL, computes fuzzy ingredient coverage using a spaCy model and the Hungarian assignment algorithm, and returns the best matches sorted by coverage.

## Library Tab

The library page lists books discovered in the configured Google Drive folder. When a book is selected the app downloads the file if necessary, converts it to PDF using `ebook-convert`, and displays a button that opens the PDF in a new tab. The core of this logic lives in `ui_pages/library.py` where the button and conversion are handled:
```python
        with st.spinner(UiText.SPINNER_PROCESSING_BOOK.format(filename=file_name)):
            local_file = download_gdrive_file(
                details[GDriveKeys.FILE_ID],
                details[GDriveKeys.FILE_NAME],
                config.book_dir,
            )
            pdf = to_pdf_cached(local_file, config.temp_dir)
```

## Image Ingredient Recognition

`image_parser.py` defines a helper used by the advanced search page to extract ingredients from uploaded images:
```python
_logger = LoggerManager(CONFIG)         # build once
_cache  = CacheManager(CONFIG)
_api    = MistralInterface(CONFIG, _cache)

_prompt = CONFIG.prompt_path.read_text("utf-8")

def parse_image_bytes(data: bytes) -> list[str]:
    b64 = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    result = _api.parse_images(_prompt, [b64])[0]
    return list(map(lambda x: x.lower(), result.ingredients)) or []
```

## Repository Layout

- `streamlit_app.py` – entry point that sets up the UI and initializes the application state.
- `config.py` – Pydantic configuration classes loaded from environment variables or Streamlit secrets.
- `constants.py` – enumerations and string constants used throughout the codebase.
- `cache_manager.py` – disk‑based caching with invalidation when the recipe database changes.
- `db_utils.py` – SQLite profile database management and helper functions to fetch recipe sources.
- `gdrive_utils.py` – Google Drive operations: downloading essential files, verifying checksums and listing cookbooks.
- `query_top_k.py` – Implements the recipe search algorithm: SQL querying, deduplication and coverage calculations.
- `ui_pages/` – Streamlit page implementations for advanced search, simple search and the cookbook library.

## Data Files

The `data/` directory contains a small sample database used for tests. In production the full recipe database and profile database are downloaded from Google Drive as described above. Required filenames are assembled in `config.py` when the configuration loads.

## Notes

- The application relies heavily on Pydantic models for configuration and structured logging.
- Google Drive credentials must be provided for the synchronization features to work.
- Non‑PDF books require Calibre’s `ebook-convert` command in the system path.

Streamlit Recipe Finder provides a convenient interface for exploring a large collection of recipes with robust search capabilities and Google Drive integration.
