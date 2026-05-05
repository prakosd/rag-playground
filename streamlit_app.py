from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

from crawl4md.streamlit_support import (
    CrawlJob,
    activity_log_path,
    build_configs,
    cleanup_old_sessions_with_lock,
    drain_events,
    estimate_progress,
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
_STATE_COMPLETED = "completed"
_STATE_FAILED = "failed"
_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_TERMINAL_STATES = {_STATE_COMPLETED, _STATE_FAILED, "cancelled"}


st.set_page_config(page_title="crawl4md — Website to Markdown Crawler", page_icon=":material/travel_explore:", layout="wide")


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


def _drain_job_events(job: CrawlJob | None) -> None:
    if job is None:
        return
    for event in drain_events(job):
        event_name = str(event.get("event", ""))
        st.session_state.events.append(event)
        st.session_state.latest_event.update(event)
        st.session_state.job_state = job_state_from_event(event_name)
        output_dir = str(event.get("output_dir", ""))
        if output_dir:
            st.session_state.active_output_dir = output_dir


def _session_root() -> Path:
    return prepare_session_dir(_SESSIONS_ROOT, st.session_state.session_id)


def _form_values() -> dict[str, Any]:
    with st.form("crawl_settings"):
        st.subheader("Set up your crawl")
        st.caption("Configure the starting URLs, filtering rules, and crawl behaviour before starting.")
        urls = st.text_area(
            "Website URLs",
            value=_DEFAULT_URLS,
            height=68,
            help="Paste one or more starting pages. Use one line per site or separate with commas.",
        )
        include_only_paths = st.text_area(
            "Only include URL patterns",
            value=_DEFAULT_INCLUDE_ONLY_PATHS,
            height=68,
            help="Leave blank to allow all pages on the same site. Use regex patterns to stay inside a section.",
        )
        exclude_paths = st.text_area(
            "Skip URL patterns",
            value=_DEFAULT_EXCLUDE_PATHS,
            height=68,
            help="Pages matching these regex patterns will be skipped.",
        )
        basic_cols = st.columns(3)
        with basic_cols[0]:
            limit = st.number_input(
                "Page limit",
                min_value=1,
                value=_DEFAULT_LIMIT,
                help="Stops after this many pages so a crawl cannot grow forever.",
            )
            delay = st.number_input(
                "Delay between pages",
                min_value=0.0,
                value=_DEFAULT_DELAY,
                step=0.5,
                help="Adds a pause between pages to reduce blocking by websites.",
            )
        with basic_cols[1]:
            max_depth = st.number_input(
                "Link depth",
                min_value=1,
                value=_DEFAULT_MAX_DEPTH,
                help="How many clicks deep to follow links.",
            )
            max_retries = st.number_input(
                "Retry rounds",
                min_value=2,
                value=_DEFAULT_MAX_RETRIES,
                help="Tries failed pages again after a cooldown.",
            )
        with basic_cols[2]:
            output_extension = st.segmented_control(
                "Output format",
                _OUTPUT_EXTENSION_OPTIONS,
                default=".md",
                help="Choose Markdown for formatted text or TXT for plain text.",
            )
            extract_main_content = st.checkbox(
                "Extract main content only",
                value=True,
                help="Keeps article/product text and strips most menus, footers, and sidebars.",
            )

        with st.expander("Advanced options"):
            advanced_cols = st.columns(3)
            with advanced_cols[0]:
                flush_interval = st.number_input(
                    "Save every N pages",
                    min_value=1,
                    value=_DEFAULT_FLUSH_INTERVAL,
                    help="Saves progress periodically so partial results survive interruption.",
                )
                max_file_size_mb = st.number_input(
                    "Max file size (MB)",
                    min_value=0.1,
                    value=_DEFAULT_MAX_FILE_SIZE_MB,
                    step=0.5,
                    help="Splits output into files that are easier to open and download.",
                )
            with advanced_cols[1]:
                wait_for = st.number_input(
                    "Extra render wait",
                    min_value=0.0,
                    value=_DEFAULT_WAIT_FOR,
                    step=0.5,
                    help="Helps JavaScript-heavy pages finish loading before extraction.",
                )
                timeout = st.number_input(
                    "Page timeout",
                    min_value=0.0,
                    value=_DEFAULT_TIMEOUT,
                    step=5.0,
                    help="Maximum seconds to spend loading one page.",
                )
            with advanced_cols[2]:
                activity_log_size = st.number_input(
                    "Activity log entries",
                    min_value=1,
                    value=int(st.session_state.activity_log_size),
                    help="Controls how many newest entries are shown in the Activity log panel.",
                )
            exclude_tags = st.text_input(
                "HTML tags to remove",
                value=_DEFAULT_EXCLUDE_TAGS,
                help="Common values remove menus, scripts, forms, and styles from extracted text.",
            )
            include_only_tags = st.text_input(
                "Only keep these HTML tags",
                value="",
                help="Advanced: only extract content from these HTML tags. Leave blank for normal use.",
            )

        submitted = st.form_submit_button(
            "Start crawl", type="primary", icon=":material/play_arrow:"
        )
    return {
        "submitted": submitted,
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


def _render_status() -> None:
    job = st.session_state.job
    _drain_job_events(job)
    latest = st.session_state.latest_event
    processed_pages = int(latest.get("processed_pages", 0) or 0)
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    limit = int(latest.get("limit", _DEFAULT_LIMIT) or _DEFAULT_LIMIT)
    is_finished = st.session_state.job_state in _TERMINAL_STATES
    progress = estimate_progress(processed_pages, limit, is_finished=is_finished)
    st.progress(progress.fraction, text=progress.label)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Processed", processed_pages)
    metric_cols[1].metric("Successful", successful_pages)
    metric_cols[2].metric("Failed", failed_pages)
    metric_cols[3].metric("Discovered", discovered_pages)
    metric_cols[4].metric("Limit", limit)
    metric_cols[5].metric("State", st.session_state.job_state.replace("_", " ").title())

    current_url = str(latest.get("current_url", ""))
    if current_url:
        st.caption(f"Current URL: {current_url}")
    started_at = st.session_state.started_at
    if started_at is not None:
        elapsed = datetime.now(timezone.utc) - started_at
        st.caption(f"Elapsed time: {str(elapsed).split('.')[0]}")

    if job is not None and job.thread.is_alive():
        if st.button("Stop after current page", icon=":material/stop_circle:"):
            request_cancel(job)
            st.session_state.job_state = _STATE_CANCEL_REQUESTED
            st.rerun()
    elif st.session_state.job_state == _STATE_FAILED:
        st.error(str(latest.get("error", "The crawl failed.")))
    elif st.session_state.job_state in _TERMINAL_STATES:
        st.success("Crawl finished. Generated files are available below.")


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


def _render_activity_log() -> None:
    log_path = activity_log_path(_active_file_root())
    max_lines = int(st.session_state.activity_log_size or _DEFAULT_ACTIVITY_LOG_SIZE)
    lines = read_recent_lines(log_path, max_lines=max_lines) if log_path else []
    if lines:
        st.markdown("**Activity log**")
        with st.container(height=200):
            st.code("\n".join(reversed(lines)), language="text")


def _render_files() -> None:
    session_root = _session_root()
    file_root = _active_file_root()
    files = list_generated_files(
        session_root,
        file_root,
        download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
    )
    if not files:
        st.info("Generated files will appear here as the crawler saves progress.")
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

st.title(":material/travel_explore: crawl4md — Website to Markdown Crawler")
st.write("Point it at any website and crawl4md will follow links, extract the main content from each page, and save everything as clean, readable Markdown files — ready to use in notebooks, RAG pipelines, or documentation.")
st.caption(f"Session: {st.session_state.session_id}")

values = _form_values()
if values["submitted"]:
    current_job = st.session_state.job
    if current_job is not None and current_job.thread.is_alive():
        st.warning("A crawl is already running in this browser session.")
    else:
        _start_job(values)

st.subheader("Progress and files")
_render_live_area()
