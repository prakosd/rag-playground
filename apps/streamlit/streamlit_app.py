from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.support import (
    CrawlJob,
    activity_log_path,
    build_configs,
    cleanup_old_sessions_with_lock,
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

_DEFAULT_ACTIVITY_LOG_SIZE = 10
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
    st.session_state.setdefault("form_defaults", _default_form_values())


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
    defaults = st.session_state.form_defaults
    with st.form("crawl_settings", enter_to_submit=False):
        st.subheader("Set up your crawl")
        st.caption(
            "Configure the starting URLs, filtering rules, and crawl behaviour before starting."
        )
        urls = st.text_area(
            "Website URLs",
            value=str(defaults.get("urls", _DEFAULT_URLS)),
            height=68,
            help="Paste one or more starting pages. Use one line per site or separate with commas.",
            disabled=fields_disabled,
        )
        include_only_paths = st.text_area(
            "Only include URL patterns",
            value=str(defaults.get("include_only_paths", _DEFAULT_INCLUDE_ONLY_PATHS)),
            height=68,
            help="Leave blank to allow all pages on the same site. Use regex patterns to stay inside a section.",
            disabled=fields_disabled,
        )
        exclude_paths = st.text_area(
            "Skip URL patterns",
            value=str(defaults.get("exclude_paths", _DEFAULT_EXCLUDE_PATHS)),
            height=68,
            help="Pages matching these regex patterns will be skipped.",
            disabled=fields_disabled,
        )
        basic_cols = st.columns(3)
        with basic_cols[0]:
            limit = st.number_input(
                "Page limit",
                min_value=1,
                value=int(defaults.get("limit", _DEFAULT_LIMIT)),
                help="Stops after this many pages so a crawl cannot grow forever.",
                disabled=fields_disabled,
            )
            delay = st.number_input(
                "Delay between pages",
                min_value=0.0,
                value=float(defaults.get("delay", _DEFAULT_DELAY)),
                step=0.5,
                help="Adds a pause between pages to reduce blocking by websites.",
                disabled=fields_disabled,
            )
        with basic_cols[1]:
            max_depth = st.number_input(
                "Link depth",
                min_value=1,
                value=int(defaults.get("max_depth", _DEFAULT_MAX_DEPTH)),
                help="How many clicks deep to follow links.",
                disabled=fields_disabled,
            )
            max_retries = st.number_input(
                "Retry rounds",
                min_value=2,
                value=int(defaults.get("max_retries", _DEFAULT_MAX_RETRIES)),
                help="Tries failed pages again after a cooldown.",
                disabled=fields_disabled,
            )
        with basic_cols[2]:
            output_extension = st.segmented_control(
                "Output format",
                _OUTPUT_EXTENSION_OPTIONS,
                default=str(defaults.get("output_extension", ".md")),
                help="Choose Markdown for formatted text or TXT for plain text.",
                disabled=fields_disabled,
            )
            extract_main_content = st.checkbox(
                "Extract main content only",
                value=bool(defaults.get("extract_main_content", True)),
                help="Keeps article/product text and strips most menus, footers, and sidebars.",
                disabled=fields_disabled,
            )

        with st.expander("Advanced options"):
            advanced_cols = st.columns(3)
            with advanced_cols[0]:
                flush_interval = st.number_input(
                    "Write every N pages",
                    min_value=1,
                    value=int(defaults.get("flush_interval", _DEFAULT_FLUSH_INTERVAL)),
                    help="Writes generated files periodically during the crawl.",
                    disabled=fields_disabled,
                )
                max_file_size_mb = st.number_input(
                    "Max file size (MB)",
                    min_value=0.1,
                    value=float(defaults.get("max_file_size_mb", _DEFAULT_MAX_FILE_SIZE_MB)),
                    step=0.5,
                    help="Splits output into files that are easier to open and download.",
                    disabled=fields_disabled,
                )
            with advanced_cols[1]:
                wait_for = st.number_input(
                    "Extra render wait",
                    min_value=0.0,
                    value=float(defaults.get("wait_for", _DEFAULT_WAIT_FOR)),
                    step=0.5,
                    help="Helps JavaScript-heavy pages finish loading before extraction.",
                    disabled=fields_disabled,
                )
                timeout = st.number_input(
                    "Page timeout",
                    min_value=0.0,
                    value=float(defaults.get("timeout", _DEFAULT_TIMEOUT)),
                    step=5.0,
                    help="Maximum seconds to spend loading one page.",
                    disabled=fields_disabled,
                )
            with advanced_cols[2]:
                activity_log_size = st.number_input(
                    "Activity log entries",
                    min_value=1,
                    value=int(
                        defaults.get("activity_log_size", st.session_state.activity_log_size)
                    ),
                    help="Controls how many newest entries are shown in the Activity log panel.",
                    disabled=fields_disabled,
                )
            exclude_tags = st.text_input(
                "HTML tags to remove",
                value=str(defaults.get("exclude_tags", _DEFAULT_EXCLUDE_TAGS)),
                help="Common values remove menus, scripts, forms, and styles from extracted text.",
                disabled=fields_disabled,
            )
            include_only_tags = st.text_input(
                "Only keep these HTML tags",
                value=str(defaults.get("include_only_tags", "")),
                help="Advanced: only extract content from these HTML tags. Leave blank for normal use.",
                disabled=fields_disabled,
            )

        submitted = False
        stop_submitted = False
        action_cols = st.columns([1.5, 3], vertical_alignment="bottom")
        for action_col, action_button in zip(
            action_cols,
            crawl_action_buttons(state, job_alive=job_alive),
            strict=False,
        ):
            with action_col:
                pressed = st.form_submit_button(
                    action_button.label,
                    type=action_button.button_type,
                    icon=action_button.icon,
                    disabled=action_button.disabled,
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
    st.rerun()


def _stop_job() -> None:
    job = st.session_state.job
    if job is not None and job.thread.is_alive():
        st.session_state.job_state = _STATE_CANCEL_REQUESTED
        request_cancel(job)
        st.rerun()
        return
    st.warning("There is no active crawl to stop.")


def render_progress_and_files(
    processed: int,
    successful: int,
    failed: int,
    discovered: int,
    limit: int,
    state: str,
) -> None:
    safe_limit = max(limit, 1)
    progress_ratio = min(max(processed / safe_limit, 0.0), 1.0)
    progress_pct = progress_ratio * 100
    normalized_state = (state or "unknown").strip().lower()
    state_label = normalized_state.replace("_", " ").title()
    state_icon = {
        _STATE_IDLE: "🟡",
        _STATE_RUNNING: "🟢",
        _STATE_FAILED: "🔴",
        _STATE_COMPLETED: "✅",
        _STATE_CANCEL_REQUESTED: "🟠",
        _STATE_STOPPED: "⏹️",
    }.get(normalized_state, "⚠️")

    with st.container():
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;font-size:0.875rem;opacity:0.6">'
            f'<span>📄 {processed:,} / {limit:,} pages processed</span>'
            f'<span>⏳ {progress_pct:.2f}% complete</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.progress(progress_ratio)

        row1 = st.columns(3)
        row1[0].metric(
            label="📄 Processed",
            value=f"{processed:,}",
            delta=f"{processed:,} total",
            delta_color="off",
            help="Number of pages processed so far",
            border=True,
        )
        row1[1].metric(
            label="✅ Successful",
            value=f"{successful:,}",
            delta=f"{successful:,} completed",
            delta_color="normal",
            help="Pages processed successfully",
            border=True,
        )
        row1[2].metric(
            label="❌ Failed",
            value=f"{failed:,}",
            delta=f"{failed:,} failed",
            delta_color="inverse",
            help="Pages that failed during processing",
            border=True,
        )

        row2 = st.columns(3)
        row2[0].metric(
            label="🔎 Discovered",
            value=f"{discovered:,}",
            delta=f"{discovered:,} found",
            delta_color="normal",
            help="URLs discovered and queued so far",
            border=True,
        )
        row2[1].metric(
            label="🎯 Limit",
            value=f"{limit:,}",
            delta=f"{max(limit - processed, 0):,} remaining",
            delta_color="off",
            help="Configured processing limit",
            border=True,
        )
        row2[2].metric(
            label=f"{state_icon} State",
            value=state_label,
            delta="Current lifecycle stage",
            delta_color="off",
            help="Current crawl lifecycle state",
            border=True,
        )

        if normalized_state == _STATE_IDLE:
            st.info("🟡 Idle — waiting to start")
        elif normalized_state == _STATE_RUNNING:
            st.success("🟢 Running — processing files")
        elif normalized_state == _STATE_FAILED:
            st.error("🔴 Failed — processing encountered errors")
        elif normalized_state == _STATE_COMPLETED:
            st.success("✅ Completed — all files processed")
        elif normalized_state == _STATE_CANCEL_REQUESTED:
            st.info("🟡 Stop requested — waiting for worker to finish")
        elif normalized_state == _STATE_STOPPED:
            st.info("🟡 Stopped — generated files remain available")
        else:
            st.warning("⚠️ Unknown state")




def _render_status() -> None:
    job = st.session_state.job
    state_changed = _drain_job_events(job)
    if state_changed and st.session_state.job_state in _REFRESH_FORM_STATES:
        st.rerun()
    latest = st.session_state.latest_event
    processed_pages = int(latest.get("processed_pages", 0) or 0)
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    limit = int(latest.get("limit", _DEFAULT_LIMIT) or _DEFAULT_LIMIT)
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
        left = f'Crawling: <a href="{current_url}" target="_blank" rel="noopener noreferrer">{current_url}</a>' if current_url else ""
        right = f"Elapsed time: {elapsed_str}" if elapsed_str else ""
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;font-size:0.875rem;opacity:0.6">'
            f'<span>{left}</span><span>{right}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.job_state == _STATE_FAILED:
        st.error(str(latest.get("error", "The crawl failed.")))


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
        lambda m: f'<a href="{m.group()}" target="_blank" rel="noopener noreferrer">{m.group()}</a>',
        escaped,
    )


def _render_activity_log() -> None:
    log_path = activity_log_path(_active_file_root())
    max_lines = int(st.session_state.activity_log_size or _DEFAULT_ACTIVITY_LOG_SIZE)
    lines = read_recent_lines(log_path, max_lines=max_lines) if log_path else []
    if lines:
        st.markdown("**Activity log**")
        with st.container(height=200):
            rendered = "<br>".join(_linkify_log_line(line) for line in reversed(lines))
            st.markdown(
                f'<div style="font-family:monospace;font-size:0.85rem;white-space:pre-wrap;line-height:1.5">{rendered}</div>',
                unsafe_allow_html=True,
            )


def _render_files() -> None:
    session_root = _session_root()
    file_root = _active_file_root()
    files = list_generated_files(
        session_root,
        file_root,
        download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
    )
    if not files:
        st.info("Generated files will appear here as the crawler writes output.")
        return
    rows = [
        {
            "File": file.relative_path,
            "Type": file.file_type,
            "Size (MB)": round(file.size_bytes / (1024 * 1024), 3),
            "Modified": file.modified_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        for file in files
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.markdown("**Downloads**")
    for file in files:
        if not file.download_allowed:
            st.caption(f"{file.relative_path} is large. Open it from the workspace folder instead.")
            continue
        st.download_button(
            label=file.relative_path,
            data=file.path.read_bytes(),
            file_name=file.name,
            mime="text/plain"
            if file.file_type in {"txt", "csv", "log"}
            else "application/octet-stream",
            icon=":material/download:",
        )
    st.caption(f"Session folder: {session_root}")


@st.fragment(run_every="1s")
def _render_live_area() -> None:
    _render_status()
    st.divider()
    _render_activity_log()
    st.divider()
    _render_files()


_run_startup_cleanup()
_init_state()
_drain_job_events(st.session_state.job)

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
    div[class*="st-key-FormSubmitter-crawl_settings-Stop"] button {{
        background-color: #dc2626;
        border-color: #dc2626;
        color: white;
    }}
    div[class*="st-key-FormSubmitter-crawl_settings-Stop"] button:hover {{
        background-color: #b91c1c;
        border-color: #b91c1c;
        color: white;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(":material/travel_explore: crawl4md — Website Crawler")
st.write(
    "Point it at any website and crawl4md will follow links, extract the main content from each page, and save everything as clean, readable Markdown files."
)
st.caption(f"Session: {st.session_state.session_id}")

current_job = st.session_state.job
current_state = st.session_state.job_state
job_alive = _job_is_alive(current_job)
fields_disabled = (
    current_state == _STATE_RUNNING and job_alive
) or current_state == _STATE_CANCEL_REQUESTED

values = _form_values(
    fields_disabled=fields_disabled,
    state=current_state,
    job_alive=job_alive,
)
if values["submitted"]:
    if current_job is not None and current_job.thread.is_alive():
        st.warning("A crawl is already running in this browser session.")
    else:
        _start_job(values)
elif values["stop_submitted"]:
    _stop_job()

st.subheader("📊 Progress")
_render_live_area()
