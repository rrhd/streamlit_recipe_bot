import base64
import json
from typing import Any
try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback for tests
    import types
    st = types.SimpleNamespace(
        secrets={},
        session_state={},
        sidebar=types.SimpleNamespace(expander=lambda *a, **k: types.SimpleNamespace(markdown=lambda *_: None)),
    )
from mistralai.models import (
    AssistantMessage,
    UserMessage,
    ToolMessage,
    TextChunk,
    ImageURLChunk,
    SystemMessage,
)

from config import AppConfig
from constants import ModelName, AgentText
from chat_agent import SEARCH_TOOL, search_and_rerank
from models import RecipeSearchArgs
from session_state import SessionStateKeys
from ui_helpers import UiText
from mistral_utils import chat_complete


def _prep_history(history: list) -> list:
    first_user = next(
        (i for i, m in enumerate(history) if isinstance(m, UserMessage)),
        len(history),
    )
    return [history[0]] + history[first_user:]


def render_chatbot_page(st: st, config: AppConfig) -> None:
    st.header(UiText.HEADER_CHAT)
    st.info(UiText.CHAT_ABOUT)

    if SessionStateKeys.CHAT_HISTORY not in st.session_state:
        st.session_state[SessionStateKeys.CHAT_HISTORY] = [
            SystemMessage(content=AgentText.CHATBOT_SYSTEM)
        ]

    chat_history: list = st.session_state[SessionStateKeys.CHAT_HISTORY]

    for msg in chat_history[1:]:
        st.chat_message(msg.role).markdown(msg.content)

    if len(chat_history) == 1:
        st.chat_message("assistant").markdown(UiText.CHAT_INIT_MESSAGE)

    uploaded_files = st.file_uploader(
        UiText.CHAT_FILE_LABEL,
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    user_input = st.chat_input(UiText.CHAT_PLACEHOLDER)

    if user_input or uploaded_files:
        content_chunks = []
        if user_input:
            content_chunks.append(TextChunk(text=user_input))
        for file in uploaded_files or []:
            b64 = base64.b64encode(file.read()).decode()
            data_uri = f"data:image/jpeg;base64,{b64}"
            content_chunks.append(ImageURLChunk(image_url={"url": data_uri}))

        chat_history.append(UserMessage(content=content_chunks))

        try:
            response = chat_complete(
                config,
                messages=_prep_history(chat_history),
                model=ModelName.CHAT_SMALL,
                tools=[SEARCH_TOOL],
                tool_choice="auto",
            )
        except Exception as e:
            st.error(f"Chat API error: {e}")
            return

        msg = response.choices[0].message
        if msg.content:
            assistant_msg = AssistantMessage(content=msg.content)
            chat_history.append(assistant_msg)
            st.chat_message(assistant_msg.role).markdown(assistant_msg.content)

        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            try:
                args = RecipeSearchArgs.model_validate_json(tool_call.function.arguments)
            except Exception:
                error_msg = UiText.TOOL_ARGS_INVALID
                assistant_error = AssistantMessage(content=error_msg)
                chat_history.append(assistant_error)
                st.chat_message(assistant_error.role).markdown(assistant_error.content)
                return

            results = search_and_rerank(
                args.query,
                config,
                st.session_state.get(SessionStateKeys.ALL_SOURCES_LIST, []),
            )
            results_short = [
                {"title": r.get("title"), "url": r.get("url")}
                for r in results
            ]
            with st.sidebar.expander(UiText.EXPANDER_SEARCH_RESULTS, expanded=True):
                for i, item in enumerate(results_short, 1):
                    st.markdown(f"{i}. [{item['title']}]({item['url']})")
            tool_result = json.dumps(results_short)
            chat_history.append(
                ToolMessage(tool_call_id=tool_call.id, content=tool_result)
            )
            try:
                follow = chat_complete(
                    config,
                    messages=_prep_history(chat_history),
                    model=ModelName.CHAT_SMALL,
                )
            except Exception as e:
                st.error(f"Chat API error: {e}")
                return
            final_msg = follow.choices[0].message
            if final_msg.content:
                final_assistant = AssistantMessage(content=final_msg.content)
                chat_history.append(final_assistant)
                st.chat_message(final_assistant.role).markdown(final_assistant.content)

