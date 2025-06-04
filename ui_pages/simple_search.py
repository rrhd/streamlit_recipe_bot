import json
import logging

import pandas as pd
import streamlit as st

from config import AppConfig
from constants import MiscValues, RecipeKeys, FormatStrings, TagFilterMode, LogMsg
from log_utils import SearchPayload, ErrorPayload, log_with_payload
from query_top_k import query_top_k
from session_state import SessionStateKeys
from ui_helpers import UiText, display_recipe_markdown


def render_simple_search_page(st: st, config: AppConfig) -> None:
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
                    UiText.COLUMN_RECIPE_TITLE: title,
                    UiText.COLUMN_SOURCE_URL: url,
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
