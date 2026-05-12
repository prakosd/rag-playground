from __future__ import annotations

import html
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.i18n import CATALOG, get_strings
from crawl4md_streamlit.support import (
    _DEFAULT_ACTIVITY_LOG_SIZE,
    _PLAYWRIGHT_MISSING_BROWSER_MESSAGE,
    CrawlJob,
    activity_log_path,
    build_configs,
    cleanup_old_sessions_with_lock,
    count_new_log_entries,
    drain_events,
    find_latest_crawl_dir,
    generate_crawl_id,
    generate_safe_id,
    job_state_from_event,
    list_generated_files,
    prepare_session_dir,
    read_recent_lines,
    request_cancel,
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
_OUTPUT_EXTENSION_OPTIONS = [".md", ".txt"]
_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_DEFAULT_LANGUAGE = "English"
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


st.set_page_config(
    page_title="crawl4md — Website Crawler",
    page_icon=":material/travel_explore:",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def _run_startup_cleanup() -> None:
    cleanup_old_sessions_with_lock(_SESSIONS_ROOT)


def _init_state() -> None:
    st.session_state.setdefault("session_id", generate_safe_id())
    st.session_state.setdefault("job", None)
    st.session_state.setdefault("job_state", _STATE_IDLE)
    st.session_state.setdefault("crawl_id", "")
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("latest_event", {})
    st.session_state.setdefault("active_output_dir", "")
    st.session_state.setdefault("started_at", None)
    st.session_state.setdefault("activity_log_size", _DEFAULT_ACTIVITY_LOG_SIZE)
    st.session_state.setdefault("activity_log_latest_line", None)
    st.session_state.setdefault("form_defaults", _default_form_values())
    st.session_state.setdefault("stop_confirmation_open", False)
    st.session_state.setdefault("language", "English")


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
            st.session_state.job = None
            st.session_state.form_defaults = _default_form_values()
    return state_changed


def _session_root() -> Path:
    return prepare_session_dir(_SESSIONS_ROOT, st.session_state.session_id)


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
    progress_ratio = min(max(processed / denominator, 0.0), 1.0)
    progress_pct = progress_ratio * 100
    normalized_state = (state or "unknown").strip().lower()
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

    with st.container():
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;font-size:0.875rem;opacity:0.6">'
            f"<span>📄 {processed:,} / {denominator_label}</span>"
            f"<span>⏳ {progress_pct:.2f}% {strings['PROGRESS_COMPLETE']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(progress_ratio)

        row1 = st.columns(3)
        row1[0].metric(
            label=strings["METRIC_PROCESSED_LABEL"],
            value=f"{processed:,}",
            delta=strings["METRIC_PROCESSED_DELTA"].format(n=f"{processed:,}"),
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
        started_at = st.session_state.started_at
        elapsed_str = ""
        if started_at is not None:
            elapsed = datetime.now(timezone.utc) - started_at
            elapsed_str = str(elapsed).split(".")[0]
        if current_url or elapsed_str:
            url_html = f'<a href="{current_url}" target="_blank" rel="noopener noreferrer">{current_url}</a>'
            left = strings["STATUS_CRAWLING"].format(url_html=url_html) if current_url else ""
            right = strings["STATUS_ELAPSED"].format(elapsed=elapsed_str) if elapsed_str else ""
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;font-size:0.875rem;opacity:0.6">'
                f"<span>{left}</span><span>{right}</span>"
                f"</div>",
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
    active_output_dir = st.session_state.active_output_dir
    if active_output_dir:
        return Path(active_output_dir)
    job = st.session_state.job
    if job is not None:
        latest = find_latest_crawl_dir(job.output_base)
        if latest is not None:
            return latest
        return job.output_base
    return _session_root()


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


def render_file_download(file_path: Path, root_path: Path) -> None:
    relative_path = file_path.relative_to(root_path)
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with file_path.open("rb") as file_obj:
        file_bytes = file_obj.read()
    st.download_button(
        label=f"📄 {file_path.name}",
        data=file_bytes,
        file_name=file_path.name,
        mime=mime_type,
        key=f"download_{relative_path.as_posix()}",
    )


def render_tree(path: Path, root_path: Path) -> None:
    entries = sorted(path.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
    for entry in entries:
        if entry.is_dir():
            with st.expander(f"📁 {entry.name}"):
                render_tree(entry, root_path)
            continue
        if entry.is_file():
            render_file_download(entry, root_path)


def _render_files() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_folder = _session_root()
    file_root = _active_file_root()
    files = list_generated_files(
        session_folder,
        file_root,
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
    if session_folder.exists():
        with st.expander(f"📁 {session_folder.name}", expanded=True):
            render_tree(session_folder, session_folder)
        st.caption(strings["FILES_SESSION_CAPTION"].format(path=session_folder))
    else:
        st.warning(strings["ERROR_SESSION_FOLDER_MISSING"])


@st.fragment(run_every="1s")
def _render_live_area() -> None:
    _render_status()
    _render_activity_log()
    _render_files()


_run_startup_cleanup()
_init_state()
_drain_job_events(st.session_state.job)

strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

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

col_session, col_lang = st.columns([3, 1], vertical_alignment="center")
with col_session:
    st.caption(strings["SESSION_PREFIX"].format(session_id=st.session_state.session_id))
with col_lang:
    st.segmented_control(
        label=strings["LANG_SELECTOR_LABEL"],
        options=list(CATALOG.keys()),
        key="language",
        label_visibility="collapsed",
        disabled=fields_disabled,
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
