from enum import StrEnum


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
