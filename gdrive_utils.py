import gzip
import hashlib
import io
import logging
import os
import pathlib
import shutil
from typing import Any

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from config import CONFIG
from constants import FileMode, FileExt, GDriveKeys, LogMsg
from log_utils import (
    FileOperationPayload,
    GDrivePayload,
    LibraryPayload,
    ErrorPayload,
    log_with_payload,
)
from ui_helpers import UiText


def _get_gdrive_service() -> Any | None:
    """Gets an authenticated Google Drive API client."""

    if GDriveKeys.SECRET_ACCOUNT not in st.secrets:
        st.error(LogMsg.GDRIVE_MISSING_SECRET_ACCOUNT)
        log_with_payload(logging.ERROR, LogMsg.GDRIVE_MISSING_SECRET_ACCOUNT)
        return None

    try:
        folder_id = st.secrets[GDriveKeys.SECRET_DRIVE][GDriveKeys.FOLDER_ID]

        if not folder_id:
            log_with_payload(
                logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + "(value is empty)"
            )
            st.error("Google Drive Folder ID secret is present but has no value.")
            return None

    except KeyError:
        st.error(LogMsg.GDRIVE_MISSING_SECRET_FOLDER)
        log_with_payload(logging.ERROR, LogMsg.GDRIVE_MISSING_SECRET_FOLDER)
        return None
    except TypeError:
        st.error(
            f"Streamlit secret '{GDriveKeys.SECRET_DRIVE}' is not structured correctly."
        )
        log_with_payload(
            logging.ERROR,
            f"Streamlit secret '{GDriveKeys.SECRET_DRIVE}' is not dictionary-like.",
        )
        return None

    try:
        creds_info = st.secrets[GDriveKeys.SECRET_ACCOUNT]
        creds = service_account.Credentials.from_service_account_info(creds_info)
        service = build(
            GDriveKeys.API_SERVICE, GDriveKeys.API_VERSION, credentials=creds
        )
        return service
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_SERVICE_FAIL,
            payload=err_payload,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED + f": {e}")
        return None


def calculate_md5(filepath: str, chunk_size: int = CONFIG.md5_chunk_size) -> str | None:
    """Calculates the MD5 checksum of a file."""
    payload = FileOperationPayload(file_path=filepath)
    if not os.path.exists(filepath):
        log_with_payload(
            logging.WARNING,
            LogMsg.MD5_FILE_NOT_FOUND,
            payload=payload,
            filepath=filepath,
        )
        return None

    hash_md5 = hashlib.md5()
    try:
        with open(filepath, FileMode.READ_BINARY) as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        hex_digest = hash_md5.hexdigest()

        return hex_digest
    except OSError as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.MD5_READ_ERROR,
            payload=err_payload,
            filepath=filepath,
            error=str(e),
            exc_info=True,
        )
        return None
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.MD5_UNEXPECTED_ERROR,
            payload=err_payload,
            filepath=filepath,
            exc_info=True,
        )
        return None


def download_essential_files() -> None:
    """
    Downloads essential compressed files (e.g., DBs ending in .gz) from Google Drive
    if they don't exist locally, if their MD5 differs, or if the decompressed
    target file is missing. Decompresses them after successful download/verification.
    """
    func_name = "download_essential_files"
    service = _get_gdrive_service()
    if not service:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})"
        )
        st.error(
            UiText.ERROR_GDRIVE_CONNECTION_FAILED + " Cannot download essential files."
        )
        return

    folder_id = st.secrets.get(GDriveKeys.SECRET_DRIVE, {}).get(GDriveKeys.FOLDER_ID)
    dest_dir = CONFIG.download_dest_dir
    essential_compressed_files = set(CONFIG.essential_filenames or [])

    if not essential_compressed_files:
        log_with_payload(logging.WARNING, "No essential files configured to download.")
        return
    if not folder_id:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + f"({func_name})"
        )
        st.error(
            "Google Drive Folder ID is missing in configuration. Cannot download essential files."
        )
        return

    gdrive_payload = GDrivePayload(gdrive_folder=folder_id)
    log_with_payload(logging.INFO, f"Ensuring local directory '{dest_dir}' exists.")
    os.makedirs(dest_dir, exist_ok=True)

    log_with_payload(
        logging.INFO,
        f"Checking essential files {essential_compressed_files} against GDrive in '{dest_dir}'.",
        payload=gdrive_payload,
    )
    download_needed_count = 0
    verification_failed_count = 0
    decompression_needed_count = 0
    decompression_failed_count = 0
    checked_count = 0
    skipped_download_count = 0

    try:
        page_token = None
        drive_files_details: dict[str, dict[str, Any]] = {}

        log_with_payload(
            logging.INFO, LogMsg.GDRIVE_LISTING_FILES, payload=gdrive_payload
        )
        while True:
            resp = (
                service.files()
                .list(
                    q=GDriveKeys.QUERY_FOLDER_FILES.format(folder_id=folder_id),
                    fields=GDriveKeys.FIELDS_FILE_LIST,
                    pageToken=page_token,
                )
                .execute()
            )
            files_in_page = resp.get(GDriveKeys.FILES, [])
            if not files_in_page and page_token is None:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_NO_FILES_FOUND,
                    payload=gdrive_payload,
                    folder_id=folder_id,
                )
                st.warning(
                    UiText.ERROR_GDRIVE_NO_FILES.format(
                        files=essential_compressed_files
                    )
                )
                return

            for f in files_in_page:
                file_name = f.get(GDriveKeys.FILE_NAME)
                if file_name in essential_compressed_files:
                    file_id = f.get(GDriveKeys.FILE_ID)
                    md5_checksum = f.get(GDriveKeys.FILE_MD5)
                    drive_files_details[file_name] = {
                        GDriveKeys.FILE_ID: file_id,
                        GDriveKeys.FILE_MD5: md5_checksum,
                    }

            page_token = resp.get(GDriveKeys.NEXT_PAGE_TOKEN)
            if not page_token:
                break
        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_LISTING_DONE,
            payload=gdrive_payload,
            count=len(drive_files_details),
        )

        missing_essentials_on_drive = essential_compressed_files - set(
            drive_files_details.keys()
        )
        if missing_essentials_on_drive:
            missing_files_str = ", ".join(missing_essentials_on_drive)
            log_with_payload(
                logging.WARNING,
                LogMsg.GDRIVE_MISSING_ESSENTIALS,
                payload=GDrivePayload(gdrive_folder=folder_id),
                missing_files=missing_files_str,
            )
            st.warning(
                UiText.ERROR_GDRIVE_ESSENTIAL_MISSING.format(files=missing_files_str)
            )

        for compressed_filename, details in drive_files_details.items():
            checked_count += 1
            local_gz_path = os.path.join(dest_dir, compressed_filename)
            drive_file_id = details.get(GDriveKeys.FILE_ID)
            drive_md5 = details.get(GDriveKeys.FILE_MD5)

            file_payload = GDrivePayload(
                file_path=local_gz_path,
                gdrive_id=drive_file_id,
                gdrive_folder=folder_id,
                md5_hash=drive_md5,
            )

            is_compressed = compressed_filename.lower().endswith(FileExt.GZ)
            decompressed_filename = (
                compressed_filename[: -len(FileExt.GZ)]
                if is_compressed
                else compressed_filename
            )
            local_final_path = os.path.join(dest_dir, decompressed_filename)

            decompression_payload = GDrivePayload(
                file_path=local_final_path,
                gdrive_id=drive_file_id,
                gdrive_folder=folder_id,
            )

            if not drive_file_id:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_SKIPPING_NO_ID,
                    payload=file_payload,
                    filename=compressed_filename,
                )
                continue
            if not drive_md5 and is_compressed:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_WARN_NO_MD5,
                    payload=file_payload,
                    filename=compressed_filename,
                )

            should_download = False
            download_verified = False

            if os.path.exists(local_gz_path):
                if drive_md5:
                    local_md5 = calculate_md5(local_gz_path)
                    if local_md5 == drive_md5:
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_LOCAL_VERIFIED_SKIP,
                            payload=file_payload,
                            filename=compressed_filename,
                        )
                        skipped_download_count += 1
                        download_verified = True
                    else:
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_DOWNLOAD_MD5_MISMATCH,
                            payload=file_payload,
                            filename=compressed_filename,
                            local_md5=local_md5,
                            drive_md5=drive_md5,
                        )
                        should_download = True
                else:
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DOWNLOAD_NO_MD5_VERIFY,
                        payload=file_payload,
                        filename=compressed_filename,
                    )
                    should_download = True
            else:
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DOWNLOAD_NEEDED,
                    payload=file_payload,
                    filename=compressed_filename,
                )
                should_download = True

            if should_download:
                download_needed_count += 1
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DOWNLOAD_START,
                    payload=file_payload,
                    filename=compressed_filename,
                    file_id=drive_file_id,
                    path=local_gz_path,
                )
                request = service.files().get_media(fileId=drive_file_id)
                try:
                    with io.FileIO(local_gz_path, FileMode.WRITE_BINARY) as fh:
                        with st.spinner(
                            UiText.SPINNER_DOWNLOADING.format(
                                filename=compressed_filename
                            )
                        ):
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while not done:
                                _, done = downloader.next_chunk(
                                    num_retries=CONFIG.gdrive_download_retries
                                )
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DOWNLOAD_DONE,
                        payload=file_payload,
                        filename=compressed_filename,
                    )

                    if drive_md5:
                        post_download_md5 = calculate_md5(local_gz_path)
                        if post_download_md5 == drive_md5:
                            log_with_payload(
                                logging.INFO,
                                LogMsg.GDRIVE_VERIFY_SUCCESS,
                                payload=file_payload,
                                filename=compressed_filename,
                                md5=drive_md5,
                            )
                            download_verified = True
                        else:
                            verify_fail_payload = file_payload.model_copy(
                                update={"md5_hash": post_download_md5}
                            )
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_VERIFY_FAIL,
                                payload=verify_fail_payload,
                                filename=compressed_filename,
                                local_md5=post_download_md5,
                                drive_md5=drive_md5,
                            )
                            st.error(
                                UiText.ERROR_GDRIVE_VERIFY_FAIL.format(
                                    filename=compressed_filename
                                )
                            )
                            verification_failed_count += 1
                            try:
                                os.remove(local_gz_path)
                            except OSError as rm_err:
                                log_with_payload(
                                    logging.ERROR,
                                    LogMsg.GDRIVE_REMOVE_MISMATCHED,
                                    payload=file_payload,
                                    path=local_gz_path,
                                    error=str(rm_err),
                                )
                            continue
                    else:
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_DOWNLOAD_NO_VERIFY,
                            payload=file_payload,
                            filename=compressed_filename,
                        )
                        download_verified = True

                except Exception as download_err:
                    err_payload = ErrorPayload(error_message=str(download_err))
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_DOWNLOAD_FAILED,
                        payload=err_payload,
                        file_payload=file_payload,
                        filename=compressed_filename,
                        file_id=drive_file_id,
                        error=str(download_err),
                        exc_info=True,
                    )
                    st.error(
                        UiText.ERROR_GDRIVE_DOWNLOAD_FAIL_UI.format(
                            filename=compressed_filename, error=download_err
                        )
                    )
                    verification_failed_count += 1
                    if os.path.exists(local_gz_path):
                        try:
                            os.remove(local_gz_path)
                        except OSError as rm_err:
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_REMOVE_INCOMPLETE,
                                payload=file_payload,
                                path=local_gz_path,
                                error=str(rm_err),
                            )
                    continue

            needs_decompression = False
            if download_verified:
                if is_compressed:
                    if not os.path.exists(local_final_path):
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_DECOMPRESS_NEEDED_MISSING,
                            payload=decompression_payload,
                            decompressed_filename=decompressed_filename,
                            compressed_filename=compressed_filename,
                        )
                        needs_decompression = True
                    elif should_download:
                        log_with_payload(
                            logging.INFO,
                            LogMsg.GDRIVE_DECOMPRESS_NEEDED_OVERWRITE,
                            payload=decompression_payload,
                            compressed_filename=compressed_filename,
                            decompressed_filename=decompressed_filename,
                        )
                        needs_decompression = True

                elif not os.path.exists(local_final_path):
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_MISSING_NON_COMPRESSED,
                        payload=file_payload,
                        filename=compressed_filename,
                    )
                    st.error(
                        UiText.ERROR_CRITICAL_FILE_MISSING.format(
                            filename=compressed_filename
                        )
                    )

            if needs_decompression:
                decompression_needed_count += 1
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_DECOMPRESSING,
                    payload=decompression_payload,
                    gz_path=local_gz_path,
                    final_path=local_final_path,
                )
                try:
                    with gzip.open(local_gz_path, FileMode.READ_BINARY) as f_in:
                        with open(local_final_path, FileMode.WRITE_BINARY) as f_out:
                            with st.spinner(
                                UiText.SPINNER_DECOMPRESSING.format(
                                    filename=compressed_filename
                                )
                            ):
                                shutil.copyfileobj(f_in, f_out)
                    log_with_payload(
                        logging.INFO,
                        LogMsg.GDRIVE_DECOMPRESS_SUCCESS,
                        payload=decompression_payload,
                        final_path=local_final_path,
                    )

                except Exception as decomp_err:
                    err_payload = ErrorPayload(error_message=str(decomp_err))
                    log_with_payload(
                        logging.ERROR,
                        LogMsg.GDRIVE_DECOMPRESS_FAILED,
                        payload=err_payload,
                        decompression_payload=decompression_payload,
                        gz_path=local_gz_path,
                        error=str(decomp_err),
                        exc_info=True,
                    )
                    st.error(
                        UiText.ERROR_GDRIVE_DECOMPRESS_FAIL.format(
                            filename=compressed_filename, error=decomp_err
                        )
                    )
                    decompression_failed_count += 1
                    if os.path.exists(local_final_path):
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_REMOVE_INCOMPLETE_DECOMPRESS,
                            payload=decompression_payload,
                            path=local_final_path,
                        )
                        try:
                            os.remove(local_final_path)
                        except OSError as rm_err:
                            log_with_payload(
                                logging.ERROR,
                                LogMsg.GDRIVE_FAILED_REMOVE_INCOMPLETE_DECOMPRESS,
                                payload=ErrorPayload(error_message=str(rm_err)),
                                path=local_final_path,
                                error=str(rm_err),
                            )

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ESSENTIALS_SUMMARY,
            checked=checked_count,
            skipped=skipped_download_count,
            attempted=download_needed_count,
            verify_failed=verification_failed_count,
            decompress_needed=decompression_needed_count,
            decompress_failed=decompression_failed_count,
        )

    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.CRITICAL,
            LogMsg.UNHANDLED_ERROR,
            payload=err_payload,
            gdrive_payload=gdrive_payload,
            error="essential files processing",
            exc_info=True,
        )
        st.error(UiText.ERROR_GDRIVE_UNEXPECTED.format(error=e))


def _upload_file_to_drive(local_path: str, drive_folder_id: str, mime_type: str):
    service = _get_gdrive_service()
    if not service:
        return

    # look for an existing file
    query = (
        f"name = '{os.path.basename(local_path)}' "
        f"and '{drive_folder_id}' in parents "
        "and trashed = false"
    )
    resp = service.files().list(q=query, fields="files(id)").execute()
    files = resp.get("files", [])
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

    if files:
        file_id = files[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": os.path.basename(local_path), "parents": [drive_folder_id]}
        service.files().create(body=metadata, media_body=media, fields="id").execute()


@st.cache_resource(ttl=600)
def list_drive_books_cached() -> tuple[list[str], dict[str, dict[str, str]]]:
    """Lists cookbook files from Google Drive, returning labels and a mapping to file ID and name."""
    func_name = "list_drive_books_cached"
    service = _get_gdrive_service()
    if not service:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})"
        )
        st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED + " Cannot list books.")

        return [], {}

    folder_id = st.secrets.get(GDriveKeys.SECRET_DRIVE, {}).get(GDriveKeys.FOLDER_ID)
    if not folder_id:
        log_with_payload(
            logging.ERROR, LogMsg.GDRIVE_FOLDER_ID_MISSING + f"({func_name})"
        )
        st.error("Google Drive Folder ID is missing. Cannot list books.")

        return [], {}

    payload = GDrivePayload(gdrive_folder=folder_id)
    log_with_payload(
        logging.INFO, LogMsg.GDRIVE_LISTING_BOOKS, payload=payload, folder_id=folder_id
    )
    book_labels = []
    book_mapping: dict[str, dict[str, str]] = {}
    all_files_count = 0

    try:
        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=GDriveKeys.QUERY_FOLDER_FILES.format(folder_id=folder_id),
                    fields=GDriveKeys.FIELDS_FILE_LIST_NO_MD5,
                    pageToken=page_token,
                )
                .execute()
            )

            files = resp.get(GDriveKeys.FILES, [])
            if not files and page_token is None:
                log_with_payload(
                    logging.WARNING,
                    LogMsg.GDRIVE_NO_BOOKS_FOUND_LISTING,
                    payload=payload,
                )

                return [], {}

            for f in files:
                all_files_count += 1
                file_name = f.get(GDriveKeys.FILE_NAME)
                file_id = f.get(GDriveKeys.FILE_ID)

                if (
                    file_name
                    and file_id
                    and file_name.lower().endswith(CONFIG.valid_book_extensions)
                ):
                    label = pathlib.Path(file_name).stem
                    if label not in book_mapping:
                        book_labels.append(label)

                        book_mapping[label] = {
                            GDriveKeys.FILE_ID: file_id,
                            GDriveKeys.FILE_NAME: file_name,
                        }
                    else:
                        dup_payload = LibraryPayload(
                            label=label, gdrive_id=file_id, file_path=file_name
                        )
                        log_with_payload(
                            logging.WARNING,
                            LogMsg.GDRIVE_LIST_DUPLICATE_LABEL,
                            payload=dup_payload,
                            label=label,
                            filename=file_name,
                            file_id=file_id,
                        )

            page_token = resp.get(GDriveKeys.NEXT_PAGE_TOKEN)
            if not page_token:
                break

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_LIST_BOOK_COUNT,
            payload=payload,
            count=len(book_labels),
        )
        book_labels.sort()
        return book_labels, book_mapping

    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_LIST_BOOK_ERROR,
            payload=err_payload,
            gdrive_payload=payload,
            folder_id=folder_id,
            error=str(e),
            exc_info=True,
        )
        st.error(UiText.ERROR_BOOKS_LOAD_FAIL.format(error=e))

        return [], {}


def download_gdrive_file(
    file_id: str, file_name: str, destination_dir: str
) -> str | None:
    """Downloads a single file from GDrive if not already present locally."""
    func_name = "download_gdrive_file"
    dest_path = os.path.join(destination_dir, file_name)
    payload = GDrivePayload(file_path=dest_path, gdrive_id=file_id)

    try:
        os.makedirs(destination_dir, exist_ok=True)

        if os.path.exists(dest_path):
            log_with_payload(
                logging.INFO,
                LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_SKIP,
                payload=payload,
                filename=file_name,
                path=dest_path,
            )
            return dest_path

        service = _get_gdrive_service()
        if not service:
            log_with_payload(
                logging.ERROR,
                LogMsg.GDRIVE_SERVICE_UNAVAILABLE + f"({func_name})",
                payload=payload,
            )
            st.error(UiText.ERROR_GDRIVE_CONNECTION_FAILED)
            return None

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_START,
            payload=payload,
            filename=file_name,
            file_id=file_id,
            path=dest_path,
        )
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(dest_path, FileMode.WRITE_BINARY) as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            with st.spinner(
                UiText.SPINNER_DOWNLOADING_ON_DEMAND.format(filename=file_name)
            ):
                while not done:
                    status, done = downloader.next_chunk(
                        num_retries=CONFIG.gdrive_download_retries
                    )

        log_with_payload(
            logging.INFO,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_DONE,
            payload=payload,
            filename=file_name,
        )
        return dest_path
    except Exception as e:
        err_payload = ErrorPayload(error_message=str(e))
        log_with_payload(
            logging.ERROR,
            LogMsg.GDRIVE_ONDEMAND_DOWNLOAD_FAILED,
            payload=err_payload,
            file_payload=payload,
            filename=file_name,
            file_id=file_id,
            error=str(e),
            exc_info=True,
        )
        st.error(
            UiText.ERROR_GDRIVE_DOWNLOAD_FAIL_UI.format(filename=file_name, error=e)
        )

        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
                log_with_payload(
                    logging.INFO,
                    LogMsg.GDRIVE_ONDEMAND_REMOVE_INCOMPLETE,
                    payload=payload,
                    path=dest_path,
                )
            except OSError as rm_err:
                err_payload = ErrorPayload(error_message=str(rm_err))
                log_with_payload(
                    logging.ERROR,
                    LogMsg.GDRIVE_ONDEMAND_FAILED_REMOVE,
                    payload=err_payload,
                    file_payload=payload,
                    path=dest_path,
                    error=str(rm_err),
                )
        return None
