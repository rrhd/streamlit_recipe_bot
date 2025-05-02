import logging
import os
import pathlib
import subprocess

import streamlit as st

from constants import FileExt, FormatStrings, ToolNames, LogMsg
from log_utils import FileOperationPayload, ErrorPayload, log_with_payload
from ui_helpers import UiText


@st.cache_resource(max_entries=5)
def to_pdf_cached(source_path: str, temp_dir: str) -> str:
    """
    Converts an ebook (epub, mobi) to PDF using the 'epub2pdf' command-line tool
    (installed as a Python package dependency via Poetry).
    Returns the path to the PDF. Requires the 'epub2pdf' Python package.
    Raises exceptions on failure.
    """
    payload = FileOperationPayload(file_path=source_path)
    log_with_payload(
        logging.INFO, LogMsg.EBOOK_CONVERT_REQ, payload=payload, source_path=source_path
    )

    if not os.path.exists(source_path):
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_SRC_NOT_FOUND,
            payload=payload,
            source_path=source_path,
        )
        raise FileNotFoundError(f"Source file not found: {source_path}")

    source_lower = source_path.lower()
    if source_lower.endswith(FileExt.PDF):
        log_with_payload(
            logging.INFO, LogMsg.EBOOK_CONVERT_ALREADY_PDF, payload=payload
        )
        return source_path

    if not (source_lower.endswith(FileExt.EPUB) or source_lower.endswith(FileExt.MOBI)):
        log_with_payload(
            logging.WARNING,
            LogMsg.LIBRARY_UNSUPPORTED_TYPE,
            payload=payload,
            path=source_path,
        )
        raise ValueError(
            f"Cannot convert unsupported file type: {pathlib.Path(source_path).suffix}"
        )

    output_pdf_path = os.path.join(
        temp_dir, pathlib.Path(source_path).stem + FileExt.PDF
    )

    output_payload = FileOperationPayload(file_path=output_pdf_path)

    if os.path.exists(output_pdf_path):
        log_with_payload(
            logging.INFO,
            LogMsg.EBOOK_CONVERT_FOUND_EXISTING,
            payload=output_payload,
            output_pdf_path=output_pdf_path,
        )
        return output_pdf_path

    log_with_payload(
        logging.INFO,
        LogMsg.EBOOK_CONVERT_CONVERTING,
        payload=output_payload,
        source_path=source_path,
        output_pdf_path=output_pdf_path,
    )
    try:
        os.makedirs(temp_dir, exist_ok=True)
        source_filename = pathlib.Path(source_path).name

        with st.spinner(UiText.SPINNER_CONVERTING_PDF.format(filename=source_filename)):
            result = subprocess.run(
                [
                    ToolNames.EBOOK_CONVERT,
                    source_path,
                    ToolNames.OUTPUT_FLAG,
                    output_pdf_path,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding=FormatStrings.ENCODING_UTF8,
            )
        log_with_payload(
            logging.INFO,
            LogMsg.EBOOK_CONVERT_SUCCESS,
            payload=output_payload,
            source_path=source_path,
            output=result.stdout,
        )

        if not os.path.exists(output_pdf_path):
            log_with_payload(
                logging.ERROR,
                LogMsg.EBOOK_CONVERT_OUTPUT_MISSING,
                payload=output_payload,
                output_pdf_path=output_pdf_path,
            )
            raise RuntimeError(
                f"epub2pdf failed to create output file: {output_pdf_path}. Stderr: {result.stderr}"
            )
        return output_pdf_path

    except FileNotFoundError:
        log_with_payload(
            logging.ERROR, LogMsg.EBOOK_CONVERT_CMD_NOT_FOUND, payload=payload
        )
        st.error(UiText.ERROR_EBOOK_CONVERT_MISSING_RUNTIME)
        raise
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "<No Stderr>"
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_FAILED,
            payload=err_payload,
            file_payload=payload,
            source_path=source_path,
            error=str(e),
            stderr=stderr,
            exc_info=True,
        )
        st.error(UiText.ERROR_EBOOK_CONVERT_FAIL_RUNTIME)
        raise
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.EBOOK_CONVERT_UNEXPECTED_ERROR,
            payload=err_payload,
            file_payload=payload,
            source_path=source_path,
            exc_info=True,
        )
        st.error(UiText.ERROR_EBOOK_CONVERT_UNEXPECTED_RUNTIME.format(error=e))
        raise
