import streamlit as st

from config import AppConfig
from ui_helpers import UiText


def render_mistral_doc_page(st: st, config: AppConfig) -> None:
    st.header(UiText.HEADER_MISTRAL_DOCS)
    st.markdown(UiText.MISTRAL_OVERVIEW)

    st.subheader(UiText.SUBHEADER_IMAGES)
    st.code(UiText.EXAMPLE_IMAGES, language="python")

    st.subheader(UiText.SUBHEADER_EMBEDDINGS)
    st.code(UiText.EXAMPLE_EMBEDDINGS, language="python")

    st.subheader(UiText.SUBHEADER_STREAMING)
    st.code(UiText.EXAMPLE_STREAMING, language="python")
