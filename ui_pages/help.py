import streamlit as st

from config import AppConfig
from ui_helpers import UiText


def render_help_page(st: st, config: AppConfig) -> None:
    st.header(UiText.HEADER_HELP)
    st.markdown(UiText.HELP_MARKDOWN)
