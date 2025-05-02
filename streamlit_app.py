import logging
from datetime import datetime

import streamlit as st

from cache_manager import fetch_db_last_updated
from config import CONFIG
from constants import FormatStrings, LogMsg
from db_utils import init_profile_db, fetch_sources_cached
from gdrive_utils import download_essential_files, list_drive_books_cached
from log_utils import ErrorPayload, log_with_payload
from session_state import SessionStateKeys
from ui_helpers import UiText
from ui_pages.advanced_search import render_advanced_search_page
from ui_pages.library import render_library_page
from ui_pages.simple_search import render_simple_search_page

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

default_tag_filter_mode_enum = CONFIG._validated_default_tag_filter_mode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

download_essential_files()

init_profile_db()


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

    defaults = CONFIG.defaults

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
    render_advanced_search_page(
        st,
        CONFIG,
        default_tag_filter_mode_enum,
    )


elif st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_SIMPLE:
    render_simple_search_page(
        st,
        CONFIG,
    )

elif st.session_state[SessionStateKeys.SELECTED_PAGE] == UiText.TAB_LIBRARY:
    render_library_page(
        st,
        CONFIG,
    )

log_with_payload(logging.INFO, LogMsg.SCRIPT_EXEC_FINISHED)
