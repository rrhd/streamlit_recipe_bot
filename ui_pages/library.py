import base64
import logging
import os
import subprocess

import streamlit as st
from streamlit.components import v1 as components
from types import ModuleType

from config import AppConfig
from ebook_utils import to_pdf_cached
from gdrive_utils import download_gdrive_file, list_drive_books_cached
from log_utils import LibraryPayload, ErrorPayload, log_with_payload
from session_state import SessionStateKeys
from constants import GDriveKeys, LogMsg
from ui_helpers import UiText


def render_library_page(st: ModuleType, config: AppConfig) -> None:
    def on_book_select():
        """Streamlit callback: download + convert the newly-selected book with a spinner."""
        label = st.session_state[SessionStateKeys.LIBRARY_BOOK_SELECTOR]
        if not label:
            return
        mapping = st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING]
        details = mapping[label]
        with st.spinner(UiText.SPINNER_PREPARING_BOOK.format(label=label)):
            local_file = download_gdrive_file(
                details[GDriveKeys.FILE_ID],
                details[GDriveKeys.FILE_NAME],
                config.book_dir,
            )
            pdf = to_pdf_cached(local_file, config.temp_dir)
        st.session_state["_prepared_pdf"] = pdf

    st.header(UiText.HEADER_LIBRARY)

    def refresh_book_list():
        log_with_payload(logging.INFO, LogMsg.LIBRARY_REFRESH_CLICKED)

        list_drive_books_cached.clear()
        to_pdf_cached.clear()

        try:
            new_labels, new_mapping = list_drive_books_cached()
            st.session_state[SessionStateKeys.LIBRARY_BOOK_MAPPING] = new_mapping

            current_selection = st.session_state.get(
                SessionStateKeys.LIBRARY_BOOK_SELECTOR
            )
            if current_selection and current_selection not in new_mapping:
                st.session_state[SessionStateKeys.LIBRARY_BOOK_SELECTOR] = None
                log_with_payload(
                    logging.INFO,
                    LogMsg.LIBRARY_SELECTION_RESET,
                    selection=current_selection,
                )
            log_with_payload(logging.INFO, LogMsg.LIBRARY_LIST_REFRESHED)

        except Exception as e:
            err_payload = ErrorPayload(error_message=str(e))
            log_with_payload(
                logging.ERROR,
                LogMsg.LIBRARY_LIST_REFRESH_FAIL,
                payload=err_payload,
                error=str(e),
                exc_info=True,
            )
            st.error(UiText.ERROR_BOOKS_LOAD_FAIL.format(error=e))

    book_mapping_state = st.session_state.get(SessionStateKeys.LIBRARY_BOOK_MAPPING, {})
    book_options = list(book_mapping_state.keys())
    display_book_options = [
        opt for opt in book_options if opt != UiText.ERROR_BOOKS_DISPLAY
    ]
    if not display_book_options:
        if UiText.ERROR_BOOKS_DISPLAY in book_options:
            st.error(UiText.ERROR_BOOKS_DISPLAY)
        else:
            st.warning(UiText.WARN_NO_BOOKS_FOUND)
    else:
        current_book_selection = st.session_state.get(
            SessionStateKeys.LIBRARY_BOOK_SELECTOR
        )
        current_index = 0
        if current_book_selection and current_book_selection in display_book_options:
            try:
                current_index = display_book_options.index(current_book_selection)
            except ValueError:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.LIBRARY_BOOK_SELECTION_INVALID,
                    selection=current_book_selection,
                )
                current_index = 0
        elif display_book_options:
            current_index = 0

        selected_book_label = st.selectbox(
            UiText.SELECTBOX_LABEL_BOOK,
            options=display_book_options,
            key=SessionStateKeys.LIBRARY_BOOK_SELECTOR,
            index=current_index,
            on_change=on_book_select,
        )
        st.session_state["_book_placeholder"] = st.empty()
        if selected_book_label:
            st.markdown("---")

            placeholder = st.empty()
            payload = LibraryPayload(label=selected_book_label)

            placeholder.markdown(
                UiText.SPINNER_PREPARING_BOOK.format(label=selected_book_label),
                unsafe_allow_html=True,
            )

            book_details = book_mapping_state.get(selected_book_label)

            if not book_details:
                log_with_payload(
                    logging.ERROR,
                    LogMsg.LIBRARY_DETAILS_NOT_FOUND,
                    payload=payload,
                    label=selected_book_label,
                )
                placeholder.error(
                    UiText.ERROR_BOOK_DETAILS_NOT_FOUND.format(
                        label=selected_book_label
                    )
                )
            else:
                file_id = book_details.get(GDriveKeys.FILE_ID)
                file_name = book_details.get(GDriveKeys.FILE_NAME)
                book_dir_path = config.book_dir

                payload.gdrive_id = file_id

                if book_dir_path and file_name:
                    payload.file_path = os.path.join(book_dir_path, file_name)
                else:
                    payload.file_path = None

                if not file_id or not file_name or not book_dir_path:
                    log_with_payload(
                        logging.ERROR, LogMsg.LIBRARY_MISSING_DETAILS, payload=payload
                    )
                    placeholder.error(UiText.ERROR_BOOK_MISSING_DETAILS)
                else:
                    with st.spinner(
                        UiText.SPINNER_PROCESSING_BOOK.format(filename=file_name)
                    ):
                        local_file_path = download_gdrive_file(
                            file_id, file_name, book_dir_path
                        )

                    if local_file_path:
                        try:
                            pdf_path = to_pdf_cached(local_file_path, config.temp_dir)

                            payload.file_path = pdf_path

                            log_with_payload(
                                logging.INFO,
                                LogMsg.LIBRARY_ENCODING_PDF,
                                payload=payload,
                                pdf_path=pdf_path,
                            )

                            pdf_path = st.session_state.get("_prepared_pdf")
                            if pdf_path:
                                b64 = base64.b64encode(
                                    open(pdf_path, "rb").read()
                                ).decode("utf-8")
                                html = f'''
                                <style>
                                  /* Inline styles inside the iframe */
                                  #openBtn {{
                                    background-color: var(--primary-color) !important;
                                    color: white !important;
                                    border: none !important;
                                    border-radius: 4px !important;
                                    font-size: 14px !important;
                                    font-weight: 600 !important;
                                    padding: 0.5em 1em !important;
                                    cursor: pointer !important;
                                    display: inline-flex;
                                    align-items: center;
                                    gap: 0.25em;
                                  }}
                                  #openBtn:hover {{
                                    background-color: var(--primary-color-dark) !important;
                                  }}
                                </style>

                                <button id="openBtn">📖 {UiText.BUTTON_OPEN_BOOK_PDF}</button>

                                <script>
                                  document.getElementById("openBtn").onclick = () => {{
                                    const bin = atob("{b64}");
                                    const len = bin.length;
                                    const bytes = new Uint8Array(len);
                                    for (let i = 0; i < len; i++) {{
                                      bytes[i] = bin.charCodeAt(i);
                                    }}
                                    const blob = new Blob([bytes], {{ type: "application/pdf" }});
                                    const url = URL.createObjectURL(blob);
                                    window.open(url, "_blank");
                                  }};
                                </script>
                                '''

                                components.html(html, height=60)

                        except FileNotFoundError as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_PDF_CONVERT_ERROR,
                                payload=err_payload,
                                library_payload=payload,
                                path=local_file_path,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )
                            placeholder.error(
                                UiText.ERROR_BOOK_FILE_NOT_FOUND.format(
                                    filename=file_name
                                )
                            )
                        except (
                            ValueError,
                            RuntimeError,
                            subprocess.CalledProcessError,
                        ) as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_CONVERT_LINK_FAIL,
                                payload=err_payload,
                                library_payload=payload,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )

                            placeholder.error(
                                UiText.ERROR_BOOK_CONVERT_LINK.format(
                                    label=selected_book_label, error=e
                                )
                            )
                        except Exception as e:
                            placeholder.empty()
                            err_payload = ErrorPayload(error_message=str(e))
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.LIBRARY_CONVERT_LINK_FAIL,
                                payload=err_payload,
                                library_payload=payload,
                                label=selected_book_label,
                                error=str(e),
                                exc_info=True,
                            )
                            placeholder.error(
                                UiText.ERROR_BOOK_CONVERT_LINK.format(
                                    label=selected_book_label, error=e
                                )
                            )
                    else:
                        placeholder.empty()
                        log_with_payload(
                            logging.ERROR,
                            LogMsg.LIBRARY_DOWNLOAD_FIND_FAIL,
                            payload=payload,
                            label=selected_book_label,
                        )
                        placeholder.error(
                            UiText.ERROR_BOOK_DOWNLOAD_FAIL.format(
                                label=selected_book_label
                            )
                        )
    st.button(UiText.BUTTON_REFRESH_BOOKS, on_click=refresh_book_list)
