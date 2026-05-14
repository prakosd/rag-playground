from __future__ import annotations

import html
import mimetypes
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import streamlit as st
from pydantic import ValidationError
from streamlit.components.v2 import component as component_v2

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.i18n import CATALOG, get_strings
from crawl4md_streamlit.support import (
    _DEFAULT_ACTIVITY_LOG_SIZE,
    _DEFAULT_SESSION_LANGUAGE,
    _PLAYWRIGHT_MISSING_BROWSER_MESSAGE,
    CrawlJob,
    GeneratedFile,
    SessionRecord,
    activity_log_path,
    bootstrap_gate_state,
    build_configs,
    cleanup_old_sessions_with_lock,
    count_new_log_entries,
    create_session_record,
    drain_events,
    elapsed_time_display,
    ensure_within_root,
    find_latest_crawl_dir,
    format_eta_seconds,
    generate_crawl_id,
    is_text_previewable,
    job_state_from_event,
    latest_session_id,
    list_generated_files,
    normalize_session_records,
    read_recent_lines,
    read_text_preview,
    request_cancel,
    serialize_session_records,
    session_dir,
    start_crawl_job,
)

_URL_RE = re.compile(r"https?://[^\s<>\"]+")
_DEFAULT_DELAY = 3.0
_DEFAULT_EXCLUDE_PATHS = "ato.gov.au/api/"
_DEFAULT_EXCLUDE_TAGS = "nav, script, form, style"
_DEFAULT_FLUSH_INTERVAL = 1
_DEFAULT_INCLUDE_ONLY_PATHS = "ato.gov.au"
_DEFAULT_LIMIT = 9999
_DEFAULT_MAX_DEPTH = 5
_DEFAULT_MAX_FILE_SIZE_MB = 10.0
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_URLS = "https://www.ato.gov.au/"
_DEFAULT_WAIT_FOR = 3.0
_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_PREVIEW_BUTTON_WIDTH_PX = 44
_PREVIEW_DIALOG_WIDTH = "large"
_PREVIEW_CODE_CONTAINER_HEIGHT_PX = 560
_PREVIEW_LIMIT_BYTES = 256 * 1024
_PREVIEW_LIMIT_KIB = _PREVIEW_LIMIT_BYTES // 1024
_OUTPUT_EXTENSION_OPTIONS = [".md", ".txt"]
_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_DEFAULT_LANGUAGE = _DEFAULT_SESSION_LANGUAGE
_TOAST_PAGE_SUCCESS_ICON = "✅"
_TOAST_PAGE_FAIL_ICON = "❌"
_TOAST_PAGE_DISCOVERED_ICON = "🔎"
_STATE_CANCEL_REQUESTED = "cancel_requested"
_STATE_CANCELLED = "cancelled"
_STATE_COMPLETED = "completed"
_STATE_FAILED = "failed"
_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_STATE_STOPPED = "stopped"
_REFRESH_FORM_STATES = {
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_STOPPED,
}
_TERMINAL_STATES = {_STATE_COMPLETED, _STATE_FAILED, _STATE_STOPPED}
_FORM_MAX_WIDTH_PX = 980
_STATUS_ROW_STYLE = "display:flex;justify-content:space-between;font-size:0.875rem;opacity:0.6"
_SESSION_STORAGE_COMPONENT_KEY = "browser_session_storage"
_SESSION_STORAGE_KEY = "crawl4md.streamlit.sessions.v1"
_SESSION_STORAGE_HTML = """
<div id="crawl4md-session-storage" hidden></div>
"""
_SESSION_STORAGE_JS = """
const SESSION_ID_PATTERN = /^[a-z0-9_-]+$/
const SUPPORTED_LANGUAGES = new Set(["EN", "ID"])

function normalizeRecords(records) {
    const byId = new Map()
    for (const record of records || []) {
        if (!record || typeof record.session_id !== "string") continue
        if (!SESSION_ID_PATTERN.test(record.session_id)) continue
        if (typeof record.created_at !== "string") continue
        const createdAt = new Date(record.created_at)
        if (Number.isNaN(createdAt.getTime())) continue
        const rawLang = typeof record.language === "string" ? record.language.trim().toUpperCase() : ""
        const language = SUPPORTED_LANGUAGES.has(rawLang) ? rawLang : "EN"
        const normalized = {
            session_id: record.session_id,
            created_at: createdAt.toISOString().replace(".000Z", "Z"),
            language,
        }
        const existing = byId.get(normalized.session_id)
        if (!existing || createdAt >= new Date(existing.created_at)) {
            byId.set(normalized.session_id, normalized)
        }
    }
    return Array.from(byId.values()).sort((left, right) => {
        const timeDelta = new Date(right.created_at) - new Date(left.created_at)
        if (timeDelta !== 0) return timeDelta
        return right.session_id.localeCompare(left.session_id)
    })
}

function readRecords(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) return []
        const parsed = JSON.parse(rawValue)
        if (Array.isArray(parsed)) return normalizeRecords(parsed)
        if (Array.isArray(parsed.sessions)) return normalizeRecords(parsed.sessions)
    } catch {
        return []
    }
    return []
}

function writeRecords(storageKey, records) {
    try {
        const payload = JSON.stringify({ version: 1, sessions: records })
        window.localStorage.setItem(storageKey, payload)
        return true
    } catch {
        return false
    }
}

export default function (component) {
    const { data, setStateValue } = component
    const storageKey = data.storageKey
    const storedRecords = readRecords(storageKey)
    const pendingRecords = Array.isArray(data.pendingRecords) ? data.pendingRecords : []
    const nextRecords = normalizeRecords([...storedRecords, ...pendingRecords])
    const nextSerialized = JSON.stringify(nextRecords)
    const storedSerialized = JSON.stringify(storedRecords)
    let storedPending = pendingRecords.length === 0
    if (pendingRecords.length > 0 || nextSerialized !== storedSerialized) {
        storedPending = writeRecords(storageKey, nextRecords)
    }
    const storageWriteFailed = pendingRecords.length > 0 && storedPending === false
    if (pendingRecords.length > 0 && storedPending) {
        setStateValue("stored_records", nextRecords)
    }
    if (data.storageWriteFailed !== storageWriteFailed) {
        setStateValue("storage_write_failed", storageWriteFailed)
    }

    const pythonRecords = normalizeRecords(Array.isArray(data.records) ? data.records : [])
    if (JSON.stringify(pythonRecords) !== nextSerialized) {
        setStateValue("records", nextRecords)
    }
    if (data.hydrated !== true) {
        setStateValue("hydrated", true)
    }
}
"""


st.set_page_config(
    page_title="crawl4md — Website Crawler",
    page_icon=":material/travel_explore:",
    layout="wide",
)


_SESSION_STORAGE_COMPONENT = component_v2(
    "crawl4md_session_storage",
    html=_SESSION_STORAGE_HTML,
    js=_SESSION_STORAGE_JS,
)


@st.cache_resource(show_spinner=False)
def _run_startup_cleanup(active_session_ids: tuple[str, ...]) -> None:
    cleanup_old_sessions_with_lock(_SESSIONS_ROOT, active_session_ids=active_session_ids)


def _init_state() -> None:
    st.session_state.setdefault("session_id", "")
    st.session_state.setdefault("browser_session_records", [])
    st.session_state.setdefault("browser_sessions_hydrated", False)
    st.session_state.setdefault("pending_browser_session_records", [])
    st.session_state.setdefault("pending_bootstrap_session_id", "")
    st.session_state.setdefault("session_storage_write_failed", False)
    st.session_state.setdefault("preferred_session_id", "")
    st.session_state.setdefault("job", None)
    st.session_state.setdefault("job_state", _STATE_IDLE)
    st.session_state.setdefault("crawl_id", "")
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("latest_event", {})
    st.session_state.setdefault("active_output_dir", "")
    st.session_state.setdefault("started_at", None)
    st.session_state.setdefault("last_elapsed", "")
    st.session_state.setdefault("activity_log_size", _DEFAULT_ACTIVITY_LOG_SIZE)
    st.session_state.setdefault("activity_log_latest_line", None)
    st.session_state.setdefault("preview_file_relative_path", "")
    st.session_state.setdefault("form_defaults", _default_form_values())
    st.session_state.setdefault("stop_confirmation_open", False)
    st.session_state.setdefault("language", _DEFAULT_LANGUAGE)


def _browser_session_records() -> list[SessionRecord]:
    records = st.session_state.get("browser_session_records", [])
    if isinstance(records, list) and all(isinstance(record, SessionRecord) for record in records):
        return records
    return normalize_session_records(records)


def _component_field(result: Any, field: str) -> Any:
    value = getattr(result, field, None)
    if value is not None:
        return value
    component_state = st.session_state.get(_SESSION_STORAGE_COMPONENT_KEY, {})
    getter = getattr(component_state, "get", None)
    if callable(getter):
        return getter(field)
    return getattr(component_state, field, None)


def _component_result_field(result: Any, field: str) -> Any:
    return getattr(result, field, None)


def _mount_session_storage() -> None:
    result = _SESSION_STORAGE_COMPONENT(
        key=_SESSION_STORAGE_COMPONENT_KEY,
        data={
            "storageKey": _SESSION_STORAGE_KEY,
            "records": serialize_session_records(_browser_session_records()),
            "pendingRecords": st.session_state.pending_browser_session_records,
            "hydrated": st.session_state.browser_sessions_hydrated,
            "storageWriteFailed": st.session_state.session_storage_write_failed,
        },
        on_records_change=lambda: None,
        on_stored_records_change=lambda: None,
        on_storage_write_failed_change=lambda: None,
        on_hydrated_change=lambda: None,
    )
    _apply_session_storage_result(result)


def _apply_session_storage_result(result: Any) -> None:
    records_payload = _component_field(result, "records")
    if records_payload is not None:
        st.session_state.browser_session_records = normalize_session_records(
            [
                *serialize_session_records(normalize_session_records(records_payload)),
                *st.session_state.pending_browser_session_records,
            ]
        )
    storage_write_failed = _component_result_field(result, "storage_write_failed")
    if storage_write_failed is not None:
        st.session_state.session_storage_write_failed = bool(storage_write_failed)
    if _component_field(result, "hydrated") is True:
        st.session_state.browser_sessions_hydrated = True

    pending = normalize_session_records(st.session_state.pending_browser_session_records)
    stored_payload = _component_result_field(result, "stored_records")
    if pending and stored_payload is not None:
        stored_ids = {record.session_id for record in normalize_session_records(stored_payload)}
        if {record.session_id for record in pending}.issubset(stored_ids):
            st.session_state.pending_browser_session_records = []
        if st.session_state.pending_bootstrap_session_id in stored_ids:
            st.session_state.pending_bootstrap_session_id = ""
            st.session_state.session_storage_write_failed = False


def _normalize_language(value: object) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in CATALOG else _DEFAULT_LANGUAGE


def _language_widget_key() -> str:
    session_id = str(st.session_state.get("session_id", "")).strip()
    return f"language_selector_{session_id or 'bootstrap'}"


def _sync_language_widget_state() -> str:
    widget_key = _language_widget_key()
    language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.session_state.language = language
    if st.session_state.get(widget_key) != language:
        st.session_state[widget_key] = language
    return widget_key


def _select_session_id(session_id: str, *, restore_language: bool = True) -> None:
    if not session_id:
        return
    records = _browser_session_records()
    known_ids = {record.session_id for record in records}
    if session_id not in known_ids:
        return
    if st.session_state.session_id != session_id:
        st.session_state.preview_file_relative_path = ""
    st.session_state.session_id = session_id
    st.session_state.preferred_session_id = session_id
    if not restore_language:
        return
    for record in records:
        if record.session_id == session_id:
            st.session_state.language = _normalize_language(record.language)
            break


def _create_new_session() -> None:
    record = create_session_record()
    st.session_state.language = record.language
    records = normalize_session_records(
        [
            *serialize_session_records(_browser_session_records()),
            *serialize_session_records([record]),
        ]
    )
    pending_records = normalize_session_records(
        [
            *st.session_state.pending_browser_session_records,
            *serialize_session_records([record]),
        ]
    )
    st.session_state.browser_session_records = records
    st.session_state.pending_browser_session_records = serialize_session_records(pending_records)
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False
    _select_session_id(record.session_id)
    st.rerun()


def _ensure_selected_session() -> None:
    records = _browser_session_records()
    if records:
        known_ids = {record.session_id for record in records}
        preferred_session_id = str(st.session_state.get("preferred_session_id", ""))
        current_session_id = str(st.session_state.get("session_id", ""))
        selected_session_id = current_session_id
        if preferred_session_id in known_ids:
            selected_session_id = preferred_session_id
        elif current_session_id not in known_ids:
            selected_session_id = latest_session_id(records)
        restore_language = (
            selected_session_id != current_session_id
            or str(st.session_state.get("language", "")).strip().upper() not in CATALOG
        )
        _select_session_id(
            selected_session_id,
            restore_language=restore_language,
        )
        return

    record = create_session_record()
    st.session_state.browser_session_records = [record]
    st.session_state.pending_browser_session_records = serialize_session_records([record])
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False
    _select_session_id(record.session_id)
    st.rerun()


def _on_language_change(widget_key: str) -> None:
    new_lang = _normalize_language(st.session_state.get(widget_key, _DEFAULT_LANGUAGE))
    st.session_state.language = new_lang
    session_id = st.session_state.session_id
    records = _browser_session_records()
    updated = [
        SessionRecord(r.session_id, r.created_at, new_lang) if r.session_id == session_id else r
        for r in records
    ]
    st.session_state.browser_session_records = updated
    updated_record = next((r for r in updated if r.session_id == session_id), None)
    if updated_record is not None:
        pending = normalize_session_records(
            [
                *st.session_state.pending_browser_session_records,
                *serialize_session_records([updated_record]),
            ]
        )
        st.session_state.pending_browser_session_records = serialize_session_records(pending)


def _session_options() -> list[str]:
    return [record.session_id for record in _browser_session_records()]


def _session_selector_index(options: list[str]) -> int:
    if st.session_state.session_id in options:
        return options.index(st.session_state.session_id)
    return 0


def _default_form_values() -> dict[str, Any]:
    return {
        "urls": _DEFAULT_URLS,
        "include_only_paths": _DEFAULT_INCLUDE_ONLY_PATHS,
        "exclude_paths": _DEFAULT_EXCLUDE_PATHS,
        "limit": _DEFAULT_LIMIT,
        "max_depth": _DEFAULT_MAX_DEPTH,
        "flush_interval": _DEFAULT_FLUSH_INTERVAL,
        "delay": _DEFAULT_DELAY,
        "max_retries": _DEFAULT_MAX_RETRIES,
        "exclude_tags": _DEFAULT_EXCLUDE_TAGS,
        "include_only_tags": "",
        "wait_for": _DEFAULT_WAIT_FOR,
        "timeout": _DEFAULT_TIMEOUT,
        "max_file_size_mb": _DEFAULT_MAX_FILE_SIZE_MB,
        "extract_main_content": True,
        "output_extension": ".md",
        "activity_log_size": _DEFAULT_ACTIVITY_LOG_SIZE,
    }


def _job_is_alive(job: CrawlJob | None = None) -> bool:
    current_job = st.session_state.job if job is None else job
    return bool(current_job is not None and current_job.thread.is_alive())


def _drain_job_events(job: CrawlJob | None) -> bool:
    """Apply worker events to the Streamlit-facing crawl state."""
    if job is None:
        return False
    state_changed = False
    for event in drain_events(job):
        event_name = str(event.get("event", ""))
        st.session_state.events.append(event)
        st.session_state.latest_event.update(event)
        output_dir = str(event.get("output_dir", ""))
        if output_dir:
            st.session_state.active_output_dir = output_dir
        next_state = job_state_from_event(event_name)
        # Keep the UI in Stop-pending state if older worker events arrive late.
        if st.session_state.job_state == _STATE_CANCEL_REQUESTED and next_state in {
            _STATE_RUNNING,
            _STATE_CANCEL_REQUESTED,
        }:
            next_state = _STATE_CANCEL_REQUESTED
        elif next_state == _STATE_CANCELLED:
            next_state = _STATE_STOPPED
        if next_state != st.session_state.job_state:
            state_changed = True
        st.session_state.job_state = next_state
        if next_state in _TERMINAL_STATES:
            started_at = st.session_state.started_at
            if started_at is not None:
                elapsed = datetime.now(timezone.utc) - started_at
                st.session_state.last_elapsed = str(elapsed).split(".")[0]
            st.session_state.started_at = None
            st.session_state.job = None
            st.session_state.form_defaults = _default_form_values()
    return state_changed


def _session_root(session_id: str | None = None) -> Path:
    current_session_id = session_id or st.session_state.session_id
    if not current_session_id:
        return _SESSIONS_ROOT
    return session_dir(_SESSIONS_ROOT, current_session_id)


def _form_values(
    *,
    fields_disabled: bool,
    state: str,
    job_alive: bool,
) -> dict[str, Any]:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    defaults = st.session_state.form_defaults
    with st.form("crawl_settings", enter_to_submit=False):
        st.subheader(strings["FORM_SUBHEADER"])
        st.caption(strings["FORM_CAPTION"])
        urls = st.text_area(
            strings["FORM_URLS_LABEL"],
            value=str(defaults.get("urls", _DEFAULT_URLS)),
            height=68,
            help=strings["FORM_URLS_HELP"],
            disabled=fields_disabled,
        )
        include_only_paths = st.text_area(
            strings["FORM_INCLUDE_PATHS_LABEL"],
            value=str(defaults.get("include_only_paths", _DEFAULT_INCLUDE_ONLY_PATHS)),
            height=68,
            help=strings["FORM_INCLUDE_PATHS_HELP"],
            disabled=fields_disabled,
        )
        exclude_paths = st.text_area(
            strings["FORM_EXCLUDE_PATHS_LABEL"],
            value=str(defaults.get("exclude_paths", _DEFAULT_EXCLUDE_PATHS)),
            height=68,
            help=strings["FORM_EXCLUDE_PATHS_HELP"],
            disabled=fields_disabled,
        )
        basic_cols = st.columns(3)
        with basic_cols[0]:
            limit = st.number_input(
                strings["FORM_LIMIT_LABEL"],
                min_value=1,
                value=int(defaults.get("limit", _DEFAULT_LIMIT)),
                help=strings["FORM_LIMIT_HELP"],
                disabled=fields_disabled,
            )
            delay = st.number_input(
                strings["FORM_DELAY_LABEL"],
                min_value=0.0,
                value=float(defaults.get("delay", _DEFAULT_DELAY)),
                step=0.5,
                help=strings["FORM_DELAY_HELP"],
                disabled=fields_disabled,
            )
        with basic_cols[1]:
            max_depth = st.number_input(
                strings["FORM_DEPTH_LABEL"],
                min_value=1,
                value=int(defaults.get("max_depth", _DEFAULT_MAX_DEPTH)),
                help=strings["FORM_DEPTH_HELP"],
                disabled=fields_disabled,
            )
            max_retries = st.number_input(
                strings["FORM_RETRIES_LABEL"],
                min_value=2,
                value=int(defaults.get("max_retries", _DEFAULT_MAX_RETRIES)),
                help=strings["FORM_RETRIES_HELP"],
                disabled=fields_disabled,
            )
        with basic_cols[2]:
            output_extension = st.segmented_control(
                strings["FORM_OUTPUT_FORMAT_LABEL"],
                _OUTPUT_EXTENSION_OPTIONS,
                default=str(defaults.get("output_extension", ".md")),
                help=strings["FORM_OUTPUT_FORMAT_HELP"],
                disabled=fields_disabled,
            )
            extract_main_content = st.checkbox(
                strings["FORM_EXTRACT_MAIN_LABEL"],
                value=bool(defaults.get("extract_main_content", True)),
                help=strings["FORM_EXTRACT_MAIN_HELP"],
                disabled=fields_disabled,
            )

        with st.expander(strings["FORM_ADVANCED_LABEL"]):
            advanced_cols = st.columns(3)
            with advanced_cols[0]:
                flush_interval = st.number_input(
                    strings["FORM_FLUSH_LABEL"],
                    min_value=1,
                    value=int(defaults.get("flush_interval", _DEFAULT_FLUSH_INTERVAL)),
                    help=strings["FORM_FLUSH_HELP"],
                    disabled=fields_disabled,
                )
                max_file_size_mb = st.number_input(
                    strings["FORM_MAX_FILE_SIZE_LABEL"],
                    min_value=0.1,
                    value=float(defaults.get("max_file_size_mb", _DEFAULT_MAX_FILE_SIZE_MB)),
                    step=0.5,
                    help=strings["FORM_MAX_FILE_SIZE_HELP"],
                    disabled=fields_disabled,
                )
            with advanced_cols[1]:
                wait_for = st.number_input(
                    strings["FORM_WAIT_FOR_LABEL"],
                    min_value=0.0,
                    value=float(defaults.get("wait_for", _DEFAULT_WAIT_FOR)),
                    step=0.5,
                    help=strings["FORM_WAIT_FOR_HELP"],
                    disabled=fields_disabled,
                )
                timeout = st.number_input(
                    strings["FORM_TIMEOUT_LABEL"],
                    min_value=0.0,
                    value=float(defaults.get("timeout", _DEFAULT_TIMEOUT)),
                    step=5.0,
                    help=strings["FORM_TIMEOUT_HELP"],
                    disabled=fields_disabled,
                )
            with advanced_cols[2]:
                activity_log_size = st.number_input(
                    strings["FORM_ACTIVITY_LOG_LABEL"],
                    min_value=1,
                    value=int(
                        defaults.get("activity_log_size", st.session_state.activity_log_size)
                    ),
                    help=strings["FORM_ACTIVITY_LOG_HELP"],
                    disabled=fields_disabled,
                )
            exclude_tags = st.text_input(
                strings["FORM_EXCLUDE_TAGS_LABEL"],
                value=str(defaults.get("exclude_tags", _DEFAULT_EXCLUDE_TAGS)),
                help=strings["FORM_EXCLUDE_TAGS_HELP"],
                disabled=fields_disabled,
            )
            include_only_tags = st.text_input(
                strings["FORM_INCLUDE_ONLY_TAGS_LABEL"],
                value=str(defaults.get("include_only_tags", "")),
                help=strings["FORM_INCLUDE_ONLY_TAGS_HELP"],
                disabled=fields_disabled,
            )

        submitted = False
        stop_submitted = False
        action_cols = st.columns([1.5, 3], vertical_alignment="bottom")
        for action_col, action_button in zip(
            action_cols,
            crawl_action_buttons(state, job_alive=job_alive, strings=strings),
            strict=False,
        ):
            with action_col:
                pressed = st.form_submit_button(
                    action_button.label,
                    type=action_button.button_type,
                    icon=action_button.icon,
                    disabled=action_button.disabled,
                    key=action_button.action.capitalize(),
                )
            if action_button.action == "start":
                submitted = pressed
            elif action_button.action == "stop":
                stop_submitted = pressed
    return {
        "submitted": submitted,
        "stop_submitted": stop_submitted,
        "urls": urls,
        "include_only_paths": include_only_paths,
        "exclude_paths": exclude_paths,
        "limit": limit,
        "max_depth": max_depth,
        "flush_interval": flush_interval,
        "delay": delay,
        "max_retries": max_retries,
        "exclude_tags": exclude_tags,
        "include_only_tags": include_only_tags,
        "wait_for": wait_for,
        "timeout": timeout,
        "max_file_size_mb": max_file_size_mb,
        "extract_main_content": extract_main_content,
        "output_extension": output_extension or ".md",
        "activity_log_size": activity_log_size,
    }


def _start_job(values: dict[str, Any]) -> None:
    try:
        crawler_config, page_config, activity_log_size = build_configs(values)
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    crawl_id = generate_crawl_id()
    job = start_crawl_job(
        session_id=st.session_state.session_id,
        crawl_id=crawl_id,
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.job = job
    st.session_state.crawl_id = crawl_id
    st.session_state.job_state = _STATE_RUNNING
    st.session_state.started_at = datetime.now(timezone.utc)
    st.session_state.last_elapsed = ""
    st.session_state.events = []
    st.session_state.latest_event = {"limit": crawler_config.limit}
    st.session_state.active_output_dir = ""
    st.session_state.activity_log_size = activity_log_size
    st.session_state.activity_log_latest_line = None
    st.rerun()


def _stop_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    if job is not None and job.thread.is_alive():
        st.session_state.job_state = _STATE_CANCEL_REQUESTED
        request_cancel(job)
        st.rerun()
        return
    st.warning(strings["ERROR_NO_ACTIVE_CRAWL"])


@st.dialog("Stop crawl?", width="small")
def _stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.markdown(
        """
        <style>
        div[data-testid="stElementContainer"].st-key-stop_cancel_button button {
            background-color: #28a745; border-color: #28a745; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_cancel_button button:hover {
            background-color: #218838; border-color: #1e7e34; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_confirm_button button {
            background-color: #dc3545; border-color: #dc3545; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_confirm_button button:hover {
            background-color: #c82333; border-color: #bd2130; color: white;
        }
        div[data-testid="stColumn"]:has(.st-key-stop_confirm_button) [data-testid="stVerticalBlock"] {
            align-items: flex-end;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.write(strings["DIALOG_STOP_BODY"])
    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button(strings["DIALOG_BTN_KEEP"], key="stop_cancel_button"):
            st.session_state.stop_confirmation_open = False
            st.rerun()
    with action_cols[1]:
        if st.button(
            strings["DIALOG_BTN_STOP"],
            type="secondary",
            icon=":material/stop_circle:",
            key="stop_confirm_button",
        ):
            st.session_state.stop_confirmation_open = False
            _stop_job()


def render_progress_and_files(
    processed: int,
    successful: int,
    failed: int,
    discovered: int,
    limit: int,
    state: str,
) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    denominator = discovered if discovered > 0 else max(limit, 1)
    covered_unique_pages = min(processed, denominator)
    progress_ratio = min(max(covered_unique_pages / denominator, 0.0), 1.0)
    progress_pct = progress_ratio * 100
    extra_attempts = max(processed - discovered, 0) if discovered > 0 else 0
    normalized_state = (state or "unknown").strip().lower()
    is_retry_phase = extra_attempts > 0 and normalized_state in {
        _STATE_RUNNING,
        _STATE_CANCEL_REQUESTED,
    }
    state_label = strings["STATE_LABELS"].get(
        normalized_state, normalized_state.replace("_", " ").title()
    )
    state_icon = {
        _STATE_IDLE: "🟡",
        _STATE_RUNNING: "🟢",
        _STATE_FAILED: "🔴",
        _STATE_COMPLETED: "✅",
        _STATE_CANCEL_REQUESTED: "🟠",
        _STATE_STOPPED: "⏹️",
    }.get(normalized_state, "⚠️")
    denominator_label = (
        strings["DENOM_DISCOVERED"].format(n=f"{discovered:,}")
        if discovered > 0
        else strings["DENOM_LIMIT"].format(n=f"{limit:,}")
    )
    processed_delta = (
        strings["METRIC_PROCESSED_DELTA_RETRY"].format(n=f"{extra_attempts:,}")
        if extra_attempts > 0
        else strings["METRIC_PROCESSED_DELTA"].format(n=f"{processed:,}")
    )
    progress_status = (
        strings["PROGRESS_RETRYING"]
        if is_retry_phase
        else f"{progress_pct:.2f}% {strings['PROGRESS_COMPLETE']}"
    )
    attempts_label = strings["PROGRESS_ATTEMPTS"].format(n=f"{processed:,}")

    with st.container():
        st.markdown(
            f'<div style="{_STATUS_ROW_STYLE}">'
            f"<span>📄 {attempts_label} / {denominator_label}</span>"
            f"<span>⏳ {progress_status}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(progress_ratio)

        row1 = st.columns(3)
        row1[0].metric(
            label=strings["METRIC_PROCESSED_LABEL"],
            value=f"{processed:,}",
            delta=processed_delta,
            delta_color="off",
            help=strings["METRIC_PROCESSED_TOOLTIP"],
            border=True,
        )
        row1[1].metric(
            label=strings["METRIC_SUCCESSFUL_LABEL"],
            value=f"{successful:,}",
            delta=strings["METRIC_SUCCESSFUL_DELTA"].format(n=f"{successful:,}"),
            delta_color="normal",
            help=strings["METRIC_SUCCESSFUL_TOOLTIP"],
            border=True,
        )
        row1[2].metric(
            label=strings["METRIC_FAILED_LABEL"],
            value=f"{failed:,}",
            delta=strings["METRIC_FAILED_DELTA"].format(n=f"{failed:,}"),
            delta_color="inverse",
            help=strings["METRIC_FAILED_TOOLTIP"],
            border=True,
        )

        row2 = st.columns(3)
        discovered_remaining = max(limit - discovered, 0)
        limit_reached = discovered >= limit
        limit_status_delta = (
            strings["METRIC_LIMIT_DELTA_REACHED"]
            if limit_reached
            else strings["METRIC_LIMIT_DELTA_MORE"]
        )
        row2[0].metric(
            label=strings["METRIC_DISCOVERED_LABEL"],
            value=f"{discovered:,}",
            delta=strings["METRIC_DISCOVERED_DELTA"].format(
                n=f"{discovered:,}", m=f"{discovered_remaining:,}"
            ),
            delta_color="normal",
            help=strings["METRIC_DISCOVERED_TOOLTIP"],
            border=True,
        )
        row2[1].metric(
            label=strings["METRIC_LIMIT_LABEL"],
            value=f"{limit:,}",
            delta=limit_status_delta,
            delta_color="off",
            help=strings["METRIC_LIMIT_TOOLTIP"],
            border=True,
        )
        with row2[2]:
            st.metric(
                label=f"{state_icon} {strings['METRIC_STATE_WORD']}",
                value=state_label,
                delta=strings["METRIC_STATE_DELTA"],
                delta_color="off",
                help=strings["METRIC_STATE_TOOLTIP"],
                border=True,
            )

        if normalized_state == _STATE_FAILED:
            st.error(strings["BANNER_FAILED"])
        elif normalized_state == _STATE_CANCEL_REQUESTED:
            st.info(strings["BANNER_CANCEL_REQUESTED"])
        elif normalized_state == _STATE_STOPPED:
            st.info(strings["BANNER_STOPPED"])


def _render_status() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    state_changed = _drain_job_events(job)
    if state_changed and st.session_state.job_state in _REFRESH_FORM_STATES:
        st.rerun()
    latest = st.session_state.latest_event
    processed_pages = int(latest.get("processed_pages", 0) or 0)
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    new_success = successful_pages - int(st.session_state.get("prev_successful_pages", 0))
    new_fail = failed_pages - int(st.session_state.get("prev_failed_pages", 0))
    new_discovered = discovered_pages - int(st.session_state.get("prev_discovered_pages", 0))
    if new_success > 0:
        st.toast(
            strings["TOAST_SUCCESS"].format(n=successful_pages),
            icon=_TOAST_PAGE_SUCCESS_ICON,
        )
    if new_fail > 0:
        st.toast(
            strings["TOAST_FAILED"].format(n=failed_pages),
            icon=_TOAST_PAGE_FAIL_ICON,
        )
    if new_discovered > 0:
        st.toast(
            strings["TOAST_DISCOVERED"].format(n=discovered_pages),
            icon=_TOAST_PAGE_DISCOVERED_ICON,
        )
    st.session_state.prev_successful_pages = successful_pages
    st.session_state.prev_failed_pages = failed_pages
    st.session_state.prev_discovered_pages = discovered_pages
    limit = int(latest.get("limit", _DEFAULT_LIMIT) or _DEFAULT_LIMIT)

    def _render_status_content() -> None:
        render_progress_and_files(
            processed=processed_pages,
            successful=successful_pages,
            failed=failed_pages,
            discovered=discovered_pages,
            limit=limit,
            state=st.session_state.job_state,
        )

        current_url = str(latest.get("current_url", ""))
        elapsed_str = elapsed_time_display(
            started_at=st.session_state.started_at,
            job_state=st.session_state.job_state,
            frozen_elapsed=st.session_state.last_elapsed,
        )
        if current_url or elapsed_str:
            url_html = (
                f'<a href="{html.escape(current_url)}" target="_blank" rel="noopener noreferrer">'
                f"{html.escape(current_url)}</a>"
            )
            left = strings["STATUS_CRAWLING"].format(url_html=url_html) if current_url else ""
            right = strings["STATUS_ELAPSED"].format(elapsed=elapsed_str) if elapsed_str else ""
            st.markdown(
                f'<div style="{_STATUS_ROW_STYLE}"><span>{left}</span><span>{right}</span></div>',
                unsafe_allow_html=True,
            )

        next_url = str(latest.get("next_url", ""))
        eta_seconds_raw = latest.get("eta_remaining_seconds")
        eta_seconds = float(eta_seconds_raw) if eta_seconds_raw is not None else None
        eta_text = format_eta_seconds(eta_seconds, strings)
        if next_url or eta_seconds is not None:
            next_url_html = (
                f'<a href="{html.escape(next_url)}" target="_blank" rel="noopener noreferrer">'
                f"{html.escape(next_url)}</a>"
                if next_url
                else ""
            )
            left2 = strings["STATUS_NEXT_URL"].format(url_html=next_url_html) if next_url else ""
            right2 = eta_text
            st.markdown(
                f'<div style="{_STATUS_ROW_STYLE}"><span>{left2}</span><span>{right2}</span></div>',
                unsafe_allow_html=True,
            )

    _render_status_content()

    if st.session_state.job_state == _STATE_FAILED:
        err = str(latest.get("error", ""))
        if err == _PLAYWRIGHT_MISSING_BROWSER_MESSAGE:
            st.error(strings["ERROR_PLAYWRIGHT_MISSING"])
        else:
            st.error(err or strings["ERROR_CRAWL_FAILED_FALLBACK"])


def _active_file_root() -> Path:
    session_folder = _session_root()
    active_output_dir = st.session_state.active_output_dir
    if active_output_dir:
        try:
            return ensure_within_root(session_folder, active_output_dir)
        except ValueError:
            pass
    job = st.session_state.job
    if job is not None and job.session_id == st.session_state.session_id:
        latest = find_latest_crawl_dir(job.output_base)
        if latest is not None:
            return ensure_within_root(session_folder, latest)
        return ensure_within_root(session_folder, job.output_base)
    return session_folder


def _linkify_log_line(line: str) -> str:
    escaped = html.escape(line)
    return _URL_RE.sub(
        lambda m: (
            f'<a href="{m.group()}" target="_blank" rel="noopener noreferrer">{m.group()}</a>'
        ),
        escaped,
    )


def _render_activity_log() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    log_path = activity_log_path(_active_file_root())
    max_lines = int(st.session_state.activity_log_size)
    lines = read_recent_lines(log_path, max_lines=max_lines) if log_path else []
    new_entries, latest_line = count_new_log_entries(
        lines,
        st.session_state.activity_log_latest_line,
    )
    st.session_state.activity_log_latest_line = latest_line
    if lines:
        st.write("")
        st.markdown(f"**{strings['ACTIVITY_LOG_HEADER']}**")
        rows_html = "".join(
            f"<div style='padding:4px 8px;border-bottom:1px solid rgba(49,51,63,0.1);font-size:14px;font-family:sans-serif'>{_linkify_log_line(line)}</div>"
            for line in reversed(lines)
        )
        st.html(
            f"<div style='height:200px;overflow-y:auto;border:1px solid rgba(49,51,63,0.1);border-radius:8px'>{rows_html}</div>"
        )


def _open_file_preview_dialog(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    @st.dialog(
        strings["FILES_PREVIEW_DIALOG_TITLE"].format(file=file.name),
        width=_PREVIEW_DIALOG_WIDTH,
    )
    def _file_preview_dialog() -> None:
        if not file.path.exists() or not file.path.is_file():
            st.warning(strings["FILES_PREVIEW_MISSING"].format(file=file.relative_path))
            return
        if not is_text_previewable(file.name):
            st.info(strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file.name))
            return
        try:
            current_size = file.path.stat().st_size
        except OSError:
            st.warning(strings["FILES_PREVIEW_MISSING"].format(file=file.relative_path))
            return

        st.caption(
            strings["FILES_PREVIEW_DETAILS"].format(
                path=file.relative_path,
                size_kib=round(current_size / 1024, 1),
            )
        )
        try:
            preview = read_text_preview(file.path, max_bytes=_PREVIEW_LIMIT_BYTES)
        except OSError:
            st.warning(strings["FILES_PREVIEW_READ_ERROR"].format(file=file.relative_path))
            return

        if preview.text:
            with st.container(height=_PREVIEW_CODE_CONTAINER_HEIGHT_PX):
                st.code(preview.text, language="text")
        else:
            st.info(strings["FILES_PREVIEW_EMPTY"].format(file=file.name))
        if preview.truncated:
            st.caption(strings["FILES_PREVIEW_TRUNCATED"].format(limit_kib=_PREVIEW_LIMIT_KIB))

    _file_preview_dialog()


def _render_file_preview_button(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    previewable = is_text_previewable(file.name)
    preview_help = (
        strings["FILES_PREVIEW_HELP"].format(file=file.name)
        if previewable
        else strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file.name)
    )
    if st.button(
        label=strings["FILES_PREVIEW_BUTTON"],
        width=_PREVIEW_BUTTON_WIDTH_PX,
        key=f"preview_{st.session_state.session_id}_{file.relative_path}",
        help=preview_help,
        disabled=not previewable,
    ):
        st.session_state.preview_file_relative_path = file.relative_path
        st.rerun()


def render_generated_file_download(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    try:
        current_size = file.path.stat().st_size
    except OSError:
        return
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        width="content",
        gap="xxsmall",
    ):
        _render_file_preview_button(file)
        if not file.download_allowed or current_size > _DOWNLOAD_LIMIT_BYTES:
            st.button(
                label=f"📄 {file.name}",
                disabled=True,
                help=strings["FILES_DOWNLOAD_TOO_LARGE"].format(file=file.name),
                key=f"download_blocked_{st.session_state.session_id}_{file.relative_path}",
            )
        else:
            mime_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            with file.path.open("rb") as file_obj:
                file_bytes = file_obj.read()
            st.download_button(
                label=f"📄 {file.name}",
                data=file_bytes,
                file_name=file.name,
                mime=mime_type,
                key=f"download_{st.session_state.session_id}_{file.relative_path}",
            )


def build_download_tree(files: list[GeneratedFile]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for file in files:
        parts = PurePosixPath(file.relative_path).parts
        if not parts:
            continue
        node = tree
        for folder in parts[:-1]:
            node = node.setdefault(folder, {})
        node[parts[-1]] = file
    return tree


def render_download_tree(tree: Mapping[str, Any]) -> None:
    entries = sorted(
        tree.items(), key=lambda item: (not isinstance(item[1], dict), item[0].lower())
    )
    for name, entry in entries:
        if isinstance(entry, dict):
            with st.expander(f"📁 {name}"):
                render_download_tree(entry)
            continue
        render_generated_file_download(entry)


def _render_open_preview_dialog(files: list[GeneratedFile]) -> None:
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    file_by_relative_path = {file.relative_path: file for file in files}
    selected_file = file_by_relative_path.get(preview_relative_path)
    if selected_file is None:
        st.session_state.preview_file_relative_path = ""
        return
    st.session_state.preview_file_relative_path = ""
    _open_file_preview_dialog(selected_file)


@st.fragment(run_every="1s")
def _render_downloads() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_folder = _session_root()
    files = list_generated_files(
        session_folder,
        session_folder,
        download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
    )
    if files:
        st.markdown(f"**{strings['FILES_HEADER']}**")
        rows = [
            {
                strings["FILES_COL_NAME"]: file.relative_path,
                strings["FILES_COL_TYPE"]: file.file_type,
                strings["FILES_COL_SIZE"]: round(file.size_bytes / (1024 * 1024), 3),
                strings["FILES_COL_MODIFIED"]: file.modified_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
            for file in files
        ]
        st.dataframe(rows, hide_index=True, width="stretch")

    st.subheader(strings["FILES_DOWNLOADS_SUBHEADER"])
    if _job_is_alive(st.session_state.job):
        st.caption(strings["FILES_DOWNLOADS_IN_PROGRESS"])
        if files:
            with st.expander(f"📁 {session_folder.name}", expanded=True):
                render_download_tree(build_download_tree(files))
    elif session_folder.exists():
        with st.expander(f"📁 {session_folder.name}", expanded=True):
            render_download_tree(build_download_tree(files))
        st.caption(strings["FILES_SESSION_CAPTION"].format(path=session_folder))
    else:
        st.caption(strings["FILES_SESSION_CAPTION"].format(path=session_folder))

    _render_open_preview_dialog(files)


@st.fragment(run_every="1s")
def _render_live_area() -> None:
    _render_status()
    _render_activity_log()


_init_state()
_mount_session_storage()
strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
if bootstrap_state == "hydrating":
    st.title(strings["PAGE_TITLE"])
    st.write(strings["PAGE_SUBTITLE"])
    st.info(strings["SESSION_LOADING"])
    st.stop()

_ensure_selected_session()
bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
if bootstrap_state != "ready":
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(strings["PAGE_TITLE"])
    st.write(strings["PAGE_SUBTITLE"])
    if bootstrap_state == "storage_error":
        st.error(strings["ERROR_SESSION_STORAGE_WRITE"])
        st.stop()
    st.info(strings["SESSION_LOADING"])
    st.stop()

_run_startup_cleanup(tuple(_session_options()))
_drain_job_events(st.session_state.job)

strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
language_widget_key = _sync_language_widget_state()

st.markdown(
    f"""
    <style>
    div[data-testid="stMainBlockContainer"],
    section.main .block-container {{
        max-width: {_FORM_MAX_WIDTH_PX}px !important;
        margin-left: auto;
        margin-right: auto;
    }}
    div[data-testid="stForm"] {{
        max-width: {_FORM_MAX_WIDTH_PX}px;
        margin-left: auto;
        margin-right: auto;
    }}
    div[class*="st-key-Stop"] button {{
        background-color: #dc2626;
        border-color: #dc2626;
        color: white;
    }}
    div[class*="st-key-Stop"] button:hover {{
        background-color: #b91c1c;
        border-color: #b91c1c;
        color: white;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(strings["PAGE_TITLE"])
st.write(strings["PAGE_SUBTITLE"])
current_job = st.session_state.job
current_state = st.session_state.job_state
job_alive = _job_is_alive(current_job)
fields_disabled = (
    current_state == _STATE_RUNNING and job_alive
) or current_state == _STATE_CANCEL_REQUESTED

session_options = _session_options()
session_controls_col, language_col = st.columns([5, 1], vertical_alignment="bottom")
with session_controls_col:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container(horizontal=True, vertical_alignment="center", width="content"):
            st.markdown(strings["SESSION_SELECTOR_LABEL"])
            selected_session = st.selectbox(
                label=strings["SESSION_SELECTOR_LABEL"],
                options=session_options,
                index=_session_selector_index(session_options),
                key=f"session_selector_{st.session_state.session_id}",
                label_visibility="collapsed",
                width=170,
                disabled=fields_disabled,
            )
        if st.button(
            strings["SESSION_CREATE_BUTTON"],
            icon=":material/add:",
            disabled=fields_disabled,
        ):
            _create_new_session()
    if selected_session != st.session_state.session_id:
        _select_session_id(str(selected_session))
        st.rerun()
with language_col, st.container(horizontal_alignment="right"):
    st.segmented_control(
        label=strings["LANG_SELECTOR_LABEL"],
        options=list(CATALOG.keys()),
        key=language_widget_key,
        label_visibility="collapsed",
        disabled=fields_disabled,
        on_change=_on_language_change,
        args=(language_widget_key,),
    )

values = _form_values(
    fields_disabled=fields_disabled,
    state=current_state,
    job_alive=job_alive,
)
if values["submitted"]:
    st.session_state.stop_confirmation_open = False
    if current_job is not None and current_job.thread.is_alive():
        st.warning(strings["ERROR_CRAWL_ALREADY_RUNNING"])
    else:
        _start_job(values)
elif values["stop_submitted"]:
    st.session_state.stop_confirmation_open = True

if st.session_state.stop_confirmation_open and not job_alive:
    st.session_state.stop_confirmation_open = False

if st.session_state.stop_confirmation_open:
    _stop_confirmation_dialog()

st.subheader(strings["PROGRESS_HEADER"])
_render_live_area()
_render_downloads()
