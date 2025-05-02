import json
import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from config import CONFIG
from constants import FormatStrings, LogMsg

logger = logging.getLogger(__name__)


class LogPayloadKeys(StrEnum):
    """Keys for structured logging payloads."""

    FILE_PATH = "file_path"
    GDRIVE_ID = "gdrive_id"
    GDRIVE_FOLDER = "gdrive_folder"
    USERNAME = "username"
    TIMESTAMP = "timestamp"
    QUERY_PARAMS = "query_params"
    ERROR_MESSAGE = "error_message"
    STACK_TRACE = "stack_trace"
    SOURCE_COUNT = "source_count"
    BOOK_COUNT = "book_count"
    RESULT_COUNT = "result_count"
    MD5_HASH = "md5_hash"
    LABEL = "label"
    FUNCTION_NAME = "function_name"
    LOG_FORMATTING_ERROR = "_log_formatting_error"
    ORIGINAL_KWARGS = "_original_kwargs"
    PAYLOAD_DATA = "payload_data"
    MISSING_KEY = "missing_key"
    TEMPLATE = "template"


class LogPayloadBase(BaseModel):
    """Base model for structured log payloads."""

    pass


class FileOperationPayload(LogPayloadBase):
    """Payload for file operations."""

    file_path: str | None = None


class GDrivePayload(FileOperationPayload):
    """Payload for Google Drive operations."""

    gdrive_id: str | None = None
    gdrive_folder: str | None = None
    md5_hash: str | None = None


def truncate_string(text: str | bytes, max_length: int) -> str:
    """Truncates a string or bytes object if it exceeds max_length."""
    if isinstance(text, bytes):
        try:
            text_str = text.decode(
                FormatStrings.ENCODING_UTF8,
                errors=FormatStrings.ENCODING_ERRORS_REPLACE,
            )
        except Exception:
            text_str = FormatStrings.BYTES_UNDECODABLE.format(length=len(text))
    else:
        text_str = str(text)

    if len(text_str) > max_length:
        effective_max = max(max_length, len(FormatStrings.TRUNCATION_SUFFIX))
        return (
            text_str[: effective_max - len(FormatStrings.TRUNCATION_SUFFIX)]
            + FormatStrings.TRUNCATION_SUFFIX
        )
    return text_str


def _prepare_log_payload(
    payload: LogPayloadBase | dict[str, Any] | None, max_len: int
) -> dict[str, Any]:
    """Prepares the payload dictionary for logging, truncating long values."""
    if payload is None:
        return {}
    if isinstance(payload, LogPayloadBase):
        dumped_payload = payload.model_dump(exclude_unset=True, exclude_none=True)
    elif isinstance(payload, dict):
        dumped_payload = {k: v for k, v in payload.items() if v is not None}
    else:
        return {LogPayloadKeys.PAYLOAD_DATA: truncate_string(str(payload), max_len)}

    truncated_payload: dict[str, Any] = {}
    for key, value in dumped_payload.items():
        if isinstance(value, (str, bytes)):
            truncated_payload[key] = truncate_string(value, max_len)
        elif isinstance(value, (list, dict, tuple, set)):
            try:
                value_str = json.dumps(value, default=str)
            except TypeError:
                value_str = str(value)
            truncated_payload[key] = truncate_string(value_str, max_len)
        else:
            truncated_payload[key] = value

    return truncated_payload


class DbPayload(LogPayloadBase):
    """Payload for database operations."""

    db_path: str | None = None
    username: str | None = None
    timestamp: str | None = None


class SearchPayload(LogPayloadBase):
    """Payload for search operations."""

    query_params: str | None = None
    result_count: int | None = None


class ProfilePayload(DbPayload):
    """Payload specific to profile operations."""

    pass


class LibraryPayload(GDrivePayload):
    """Payload for library operations."""

    label: str | None = None


class ErrorPayload(LogPayloadBase):
    """Payload for error logging."""

    error_message: str | None = None


class FuncPayload(LogPayloadBase):
    """Payload including a function name."""

    function_name: str | None = None


class FormatErrorPayload(ErrorPayload):
    """Payload for logging formatting errors."""

    missing_key: str | None = None
    template: str | None = None


def log_with_payload(
    level: int,
    msg_template: LogMsg | str,
    payload: LogPayloadBase | dict[str, Any] | None = None,
    exc_info: bool = False,
    **kwargs: Any,
) -> None:
    """
    Logs a message formatted ONLY with **kwargs, including a structured payload in 'extra'.

    Args:
        level: Logging level (e.g., logging.INFO).
        msg_template: A LogMsg enum member or a format string template.
        payload: A Pydantic model or dictionary for the structured payload (passed to 'extra').
        exc_info: If exception info should be added to the log.
        **kwargs: Arguments used ONLY to format the msg_template string.
    """
    prepared_payload = _prepare_log_payload(payload, CONFIG.log_config.truncate_length)
    message = str(msg_template)

    try:
        message = str(msg_template).format(**kwargs)
    except KeyError as e:
        missing_key = str(e)
        error_message = LogMsg.LOG_MISSING_FORMAT_KEY.format(
            key=missing_key, template=msg_template
        )

        format_error_payload = FormatErrorPayload(
            error_message=error_message,
            missing_key=missing_key,
            template=str(msg_template),
        )
        logger.warning(
            error_message,
            exc_info=False,
            extra={
                "struct_payload": _prepare_log_payload(
                    format_error_payload, CONFIG.log_config.truncate_length
                ),
                "_original_payload": prepared_payload,
                "_original_kwargs": kwargs,
            },
        )

        message = str(msg_template)

    logger.log(
        level, message, exc_info=exc_info, extra={"struct_payload": prepared_payload}
    )
