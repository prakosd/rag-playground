"""Background crawl job helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import html
import queue
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter

from crawl4md_streamlit.form_defaults import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    DEFAULT_MAX_CONCURRENT,
)
from crawl4md_streamlit.session_manager import (
    DEFAULT_SESSIONS_ROOT,
    SESSION_PREFIX,
    prepare_crawl_output_base,
)

_EVENT_CANCEL_REQUESTED = "cancel_requested"
_EVENT_CANCELLED = "cancelled"
_EVENT_COMPLETED = "completed"
_EVENT_FAILED = "failed"
_EVENT_STARTED = "started"
_STATE_RUNNING = "running"
_ELAPSED_ACTIVE_STATES = frozenset({_STATE_RUNNING, _EVENT_CANCEL_REQUESTED})

_PLAYWRIGHT_INSTALL_HINT = "playwright install"
_PLAYWRIGHT_MISSING_EXECUTABLE_MARKER = "BrowserType.launch: Executable doesn't exist at"
PLAYWRIGHT_MISSING_BROWSER_MESSAGE = (
    "Playwright browser binaries are missing in this Python environment. "
    "Install Chromium and then retry the crawl:\n"
    "python -m playwright install chromium"
)


@dataclass(frozen=True)
class ProgressEstimate:
    """Estimated progress for a crawl whose final URL count may change."""

    fraction: float
    percent: int
    label: str


@dataclass(frozen=True)
class CrawlJob:
    """Background crawl job state shared with the Streamlit session."""

    session_id: str
    crawl_id: str
    output_base: Path
    events: queue.Queue[dict[str, object]]
    cancel_event: threading.Event
    thread: threading.Thread


def build_configs(values: Mapping[str, Any]) -> tuple[CrawlerConfig, PageConfig, int]:
    """Build crawl configs from Streamlit form values."""
    crawler_config = CrawlerConfig(
        urls=values["urls"],
        exclude_paths=values.get("exclude_paths", ""),
        include_only_paths=values.get("include_only_paths", ""),
        limit=int(values.get("limit", 1)),
        max_depth=int(values.get("max_depth", 1)),
        max_concurrent=int(values.get("max_concurrent", DEFAULT_MAX_CONCURRENT)),
        flush_interval=int(values.get("flush_interval", 1)),
        delay=float(values.get("delay", 0)),
        max_retries=int(values.get("max_retries", 2)),
    )
    page_config = PageConfig(
        exclude_tags=values.get("exclude_tags", ""),
        include_only_tags=values.get("include_only_tags", ""),
        wait_for=float(values.get("wait_for", 0)),
        timeout=float(values.get("timeout", 30)),
        max_file_size_mb=float(values.get("max_file_size_mb", 15)),
        extract_main_content=bool(values.get("extract_main_content", True)),
        output_extension=values.get("output_extension", ".md"),
    )
    activity_log_size = int(values.get("activity_log_size", DEFAULT_ACTIVITY_LOG_SIZE))
    if activity_log_size < 1:
        raise ValueError("Activity log size must be at least 1.")
    return crawler_config, page_config, activity_log_size


def estimate_progress(
    processed_pages: int, limit: int, *, is_finished: bool = False
) -> ProgressEstimate:
    """Estimate progress from processed pages and configured page limit."""
    if is_finished:
        return ProgressEstimate(fraction=1.0, percent=100, label="Complete")
    if limit < 1:
        return ProgressEstimate(fraction=0.0, percent=0, label="Estimating")
    fraction = min(max(processed_pages / limit, 0.0), 1.0)
    percent = int(fraction * 100)
    return ProgressEstimate(
        fraction=fraction,
        percent=percent,
        label=f"Estimated from {processed_pages} of {limit} configured pages",
    )


def elapsed_time_display(
    *,
    started_at: datetime | None,
    job_state: str,
    frozen_elapsed: str = "",
    now: datetime | None = None,
) -> str:
    """Return elapsed time, live while active and frozen after terminal states."""
    if started_at is None or job_state not in _ELAPSED_ACTIVE_STATES:
        return frozen_elapsed
    elapsed = (now or datetime.now(timezone.utc)) - started_at
    return str(elapsed).split(".")[0]


def format_eta_seconds(seconds: float | None, strings: Mapping[str, Any]) -> str:
    """Return localized ETA text from numeric seconds (None -> estimating placeholder)."""
    if seconds is None:
        return str(strings["ETA_ESTIMATING"])
    secs = int(seconds)
    if secs < 60:
        return str(strings["ETA_LESS_THAN_MINUTE"])
    hours, mins = divmod(secs // 60, 60)
    if hours > 0:
        return str(strings["ETA_HOURS_MINUTES"]).format(h=hours, m=mins)
    return str(strings["ETA_MINUTES"]).format(n=mins)


def format_status_row(
    *,
    url: str,
    url_template: str,
    right_text: str,
    style: str,
) -> str:
    """Return status-row HTML with crawler-provided URL text escaped."""
    escaped_url = html.escape(url, quote=True)
    url_html = (
        f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a>'
        if url
        else ""
    )
    left = url_template.format(url_html=url_html) if url else ""
    return (
        f'<div style="{html.escape(style, quote=True)}">'
        f"<span>{left}</span><span>{html.escape(right_text, quote=True)}</span>"
        "</div>"
    )


def start_crawl_job(
    *,
    session_id: str,
    crawl_id: str,
    crawler_config: CrawlerConfig,
    page_config: PageConfig,
    activity_log_size: int,
    sessions_root: Path | str = DEFAULT_SESSIONS_ROOT,
) -> CrawlJob:
    """Start a crawl in a background thread and return its job handle."""
    output_base = prepare_crawl_output_base(sessions_root, session_id, crawl_id)
    event_queue: queue.Queue[dict[str, object]] = queue.Queue()
    cancel_event = threading.Event()

    def emit(event: Mapping[str, object]) -> None:
        event_queue.put(dict(event))

    def run() -> None:
        emit(
            {
                "event": _EVENT_STARTED,
                "session_id": session_id,
                "crawl_id": crawl_id,
                "output_base": str(output_base),
                "limit": crawler_config.limit,
            }
        )
        try:
            extractor = ContentExtractor(page_config)
            writer = FileWriter(
                max_file_size_mb=page_config.max_file_size_mb,
                file_extension=page_config.output_extension,
            )
            crawler = SiteCrawler(
                crawler_config,
                page_config,
                output_base=output_base,
                session_id=f"{SESSION_PREFIX}{session_id}",
                extractor=extractor,
                writer=writer,
                activity_log_size=activity_log_size,
                progress_callback=emit,
                should_cancel=cancel_event.is_set,
            )
            results = crawler.crawl()
            success_count = sum(1 for result in results if result.success)
            fail_count = len(results) - success_count
            state = _EVENT_CANCELLED if cancel_event.is_set() else _EVENT_COMPLETED
            emit(
                {
                    "event": state,
                    "session_id": session_id,
                    "crawl_id": crawl_id,
                    "output_dir": str(crawler.output_dir) if crawler.output_dir else "",
                    "processed_pages": len(results),
                    "successful_pages": success_count,
                    "failed_pages": fail_count,
                    "limit": crawler_config.limit,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface background errors to the UI.
            emit(
                {
                    "event": _EVENT_FAILED,
                    "session_id": session_id,
                    "crawl_id": crawl_id,
                    "error": _format_crawl_error(exc),
                    "limit": crawler_config.limit,
                }
            )

    thread = threading.Thread(target=run, name=f"crawl4md-{crawl_id}", daemon=True)
    thread.start()
    return CrawlJob(
        session_id=session_id,
        crawl_id=crawl_id,
        output_base=output_base,
        events=event_queue,
        cancel_event=cancel_event,
        thread=thread,
    )


def request_cancel(job: CrawlJob) -> None:
    """Request cooperative cancellation for a running crawl job."""
    job.cancel_event.set()
    job.events.put({"event": _EVENT_CANCEL_REQUESTED, "crawl_id": job.crawl_id})


def _format_crawl_error(exc: Exception) -> str:
    details = str(exc)
    if _PLAYWRIGHT_MISSING_EXECUTABLE_MARKER in details and _PLAYWRIGHT_INSTALL_HINT in details:
        return PLAYWRIGHT_MISSING_BROWSER_MESSAGE
    return f"{type(exc).__name__}: {exc}"


def drain_events(job: CrawlJob) -> list[dict[str, object]]:
    """Drain queued job events without blocking."""
    events: list[dict[str, object]] = []
    while True:
        try:
            events.append(job.events.get_nowait())
        except queue.Empty:
            return events


def job_state_from_event(
    event_name: str,
) -> Literal["running", "completed", "failed", "cancel_requested", "cancelled"]:
    """Map a worker event name to the user-facing job state."""
    if event_name == _EVENT_STARTED:
        return "running"
    if event_name == _EVENT_COMPLETED:
        return "completed"
    if event_name == _EVENT_FAILED:
        return "failed"
    if event_name == _EVENT_CANCEL_REQUESTED:
        return "cancel_requested"
    if event_name == _EVENT_CANCELLED:
        return _EVENT_CANCELLED
    return "running"
