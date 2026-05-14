"""Shared type definition for the crawl4md translation catalog."""

from __future__ import annotations

from typing import TypedDict


class Strings(TypedDict):
    # ── Page ──────────────────────────────────────────────────────────────
    PAGE_TITLE: str
    PAGE_SUBTITLE: str
    SESSION_PREFIX: str  # template: {session_id}
    SESSION_LOADING: str
    SESSION_SELECTOR_LABEL: str
    SESSION_CREATE_BUTTON: str
    PROGRESS_HEADER: str
    LANG_SELECTOR_LABEL: str
    # ── Form ──────────────────────────────────────────────────────────────
    FORM_SUBHEADER: str
    FORM_CAPTION: str
    FORM_URLS_LABEL: str
    FORM_URLS_HELP: str
    FORM_INCLUDE_PATHS_LABEL: str
    FORM_INCLUDE_PATHS_HELP: str
    FORM_EXCLUDE_PATHS_LABEL: str
    FORM_EXCLUDE_PATHS_HELP: str
    FORM_LIMIT_LABEL: str
    FORM_LIMIT_HELP: str
    FORM_DELAY_LABEL: str
    FORM_DELAY_HELP: str
    FORM_DEPTH_LABEL: str
    FORM_DEPTH_HELP: str
    FORM_RETRIES_LABEL: str
    FORM_RETRIES_HELP: str
    FORM_OUTPUT_FORMAT_LABEL: str
    FORM_OUTPUT_FORMAT_HELP: str
    FORM_EXTRACT_MAIN_LABEL: str
    FORM_EXTRACT_MAIN_HELP: str
    FORM_ADVANCED_LABEL: str
    FORM_FLUSH_LABEL: str
    FORM_FLUSH_HELP: str
    FORM_MAX_FILE_SIZE_LABEL: str
    FORM_MAX_FILE_SIZE_HELP: str
    FORM_WAIT_FOR_LABEL: str
    FORM_WAIT_FOR_HELP: str
    FORM_TIMEOUT_LABEL: str
    FORM_TIMEOUT_HELP: str
    FORM_ACTIVITY_LOG_LABEL: str
    FORM_ACTIVITY_LOG_HELP: str
    FORM_EXCLUDE_TAGS_LABEL: str
    FORM_EXCLUDE_TAGS_HELP: str
    FORM_INCLUDE_ONLY_TAGS_LABEL: str
    FORM_INCLUDE_ONLY_TAGS_HELP: str
    # ── Action buttons ────────────────────────────────────────────────────
    BTN_START: str
    BTN_STOP: str
    # ── Stop dialog ───────────────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    DIALOG_STOP_BODY: str
    DIALOG_BTN_KEEP: str
    DIALOG_BTN_STOP: str
    # ── Toast messages — {n} is the page count ────────────────────────────
    TOAST_SUCCESS: str
    TOAST_FAILED: str
    TOAST_DISCOVERED: str
    # ── Progress metrics ──────────────────────────────────────────────────
    METRIC_PROCESSED_LABEL: str
    METRIC_PROCESSED_DELTA: str  # template: {n}
    METRIC_PROCESSED_DELTA_RETRY: str  # template: {n}
    METRIC_PROCESSED_TOOLTIP: str
    METRIC_SUCCESSFUL_LABEL: str
    METRIC_SUCCESSFUL_DELTA: str  # template: {n}
    METRIC_SUCCESSFUL_TOOLTIP: str
    METRIC_FAILED_LABEL: str
    METRIC_FAILED_DELTA: str  # template: {n}
    METRIC_FAILED_TOOLTIP: str
    METRIC_DISCOVERED_LABEL: str
    METRIC_DISCOVERED_DELTA: str  # template: {n}, {m}
    METRIC_DISCOVERED_TOOLTIP: str
    METRIC_LIMIT_LABEL: str
    METRIC_LIMIT_TOOLTIP: str
    METRIC_LIMIT_DELTA_REACHED: str
    METRIC_LIMIT_DELTA_MORE: str
    METRIC_STATE_WORD: str
    METRIC_STATE_DELTA: str
    METRIC_STATE_TOOLTIP: str
    # ── Progress bar labels ───────────────────────────────────────────────
    DENOM_DISCOVERED: str  # template: {n}
    DENOM_LIMIT: str  # template: {n}
    PROGRESS_ATTEMPTS: str  # template: {n}
    PROGRESS_COMPLETE: str
    PROGRESS_RETRYING: str
    # ── Status line ───────────────────────────────────────────────────────
    STATUS_CRAWLING: str  # template: {url_html}
    STATUS_ELAPSED: str  # template: {elapsed}
    STATUS_NEXT_URL: str  # template: {url_html}
    # ── ETA phrases ───────────────────────────────────────────────────────
    ETA_ESTIMATING: str
    ETA_LESS_THAN_MINUTE: str
    ETA_MINUTES: str  # template: {n}
    ETA_HOURS_MINUTES: str  # template: {h}, {m}
    # ── State banners ─────────────────────────────────────────────────────
    BANNER_FAILED: str
    BANNER_CANCEL_REQUESTED: str
    BANNER_STOPPED: str
    # ── Error messages ────────────────────────────────────────────────────
    ERROR_NO_ACTIVE_CRAWL: str
    ERROR_CRAWL_ALREADY_RUNNING: str
    ERROR_SESSION_STORAGE_WRITE: str
    ERROR_SESSION_FOLDER_MISSING: str
    ERROR_CRAWL_FAILED_FALLBACK: str
    ERROR_PLAYWRIGHT_MISSING: str
    # ── Activity log ──────────────────────────────────────────────────────
    ACTIVITY_LOG_HEADER: str
    # ── Files section ─────────────────────────────────────────────────────
    FILES_HEADER: str
    FILES_DOWNLOADS_SUBHEADER: str
    FILES_COL_NAME: str
    FILES_COL_TYPE: str
    FILES_COL_SIZE: str
    FILES_COL_MODIFIED: str
    FILES_SESSION_CAPTION: str  # template: {path}
    FILES_DOWNLOAD_TOO_LARGE: str  # template: {file}
    FILES_DOWNLOADS_IN_PROGRESS: str
    FILES_PREVIEW_BUTTON: str
    FILES_PREVIEW_HELP: str  # template: {file}
    FILES_PREVIEW_DIALOG_TITLE: str  # template: {file}
    FILES_PREVIEW_DETAILS: str  # template: {path}, {size_kib}
    FILES_PREVIEW_UNSUPPORTED: str  # template: {file}
    FILES_PREVIEW_MISSING: str  # template: {file}
    FILES_PREVIEW_READ_ERROR: str  # template: {file}
    FILES_PREVIEW_EMPTY: str  # template: {file}
    FILES_PREVIEW_TRUNCATED: str  # template: {limit_kib}
    # ── State display labels (state_key -> display name) ──────────────────
    STATE_LABELS: dict[str, str]
