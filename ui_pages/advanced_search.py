import base64
import json
import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from cache_manager import fetch_db_last_updated
from config import AppConfig
from constants import (
    MiscValues,
    CategoryKeys,
    RecipeKeys,
    FormatStrings,
    TagFilterMode,
    ProfileDataKeys,
    LogMsg,
)
from db_utils import save_profile, load_profile, fetch_sources_cached
from image_parser import parse_image_bytes
from log_utils import SearchPayload, ProfilePayload, ErrorPayload, log_with_payload
from query_top_k import query_top_k
from session_state import SessionStateKeys
from ui_helpers import UiText, display_recipe_markdown


def render_advanced_search_page(
    st: st.session_state, config: AppConfig, default_tag_filter_mode_enum: TagFilterMode
) -> None:
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

        cam_file = st.camera_input(UiText.LABEL_CAMERA_INPUT)
        up_file  = st.file_uploader(
            UiText.LABEL_FILE_INPUT,
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=False,
        )
        img_file = cam_file or up_file
        if img_file:
            with st.spinner(UiText.SPINNER_PROCESSING_IMAGE):
                ings = parse_image_bytes(img_file.getvalue())
            if ings:
                existing = st.session_state.get(SessionStateKeys.ADV_INGREDIENTS_INPUT, "")
                joined = "\n".join(filter(None, [existing.strip(), *ings]))
                st.session_state[SessionStateKeys.LOADED_INGREDIENTS_TEXT] = joined
                st.session_state[SessionStateKeys.ADV_INGREDIENTS_INPUT] = joined
                st.success(UiText.SUCCESS_INGREDIENTS_FROM_IMAGE.format(count=len(ings)))
            else:
                st.warning(UiText.WARNING_NO_INGREDIENTS_FROM_IMAGE)

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
