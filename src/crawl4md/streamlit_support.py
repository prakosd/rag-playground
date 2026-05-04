"""Support helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import os
import queue
import secrets
import shutil
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter

_ACTIVITY_LOG_FILE = "activity_log.txt"
_CLEANUP_LOCK_FILE = ".cleanup.lock"
_CLEANUP_LOG_FILE = "cleanup.log"
_CRAWL_PREFIX = "crawl_"
_DEFAULT_ACTIVITY_LOG_SIZE = 10
_DEFAULT_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DEFAULT_RETENTION_DAYS = 7
_DEFAULT_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_ID_BYTES = 9
_LOCK_STALE_SECONDS = 60 * 60
_SESSION_PREFIX = "session_"
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

_EVENT_CANCEL_REQUESTED = "cancel_requested"
_EVENT_COMPLETED = "completed"
_EVENT_FAILED = "failed"
_EVENT_STARTED = "started"

_PLAYWRIGHT_INSTALL_HINT = "playwright install"
_PLAYWRIGHT_MISSING_EXECUTABLE_MARKER = "BrowserType.launch: Executable doesn't exist at"
_PLAYWRIGHT_MISSING_BROWSER_MESSAGE = (
    "Playwright browser binaries are missing in this Python environment. "
    "Install Chromium and then retry the crawl:\n"
    "python -m playwright install chromium"
)

_HIDDEN_FILE_PREFIX = "."
_SAFE_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")


@dataclass(frozen=True)
class GeneratedFile:
    """Metadata for a generated file that can be shown in Streamlit."""

    path: Path
    relative_path: str
    name: str
    size_bytes: int
    modified_at: datetime
    file_type: str
    download_allowed: bool


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


def generate_safe_id() -> str:
    """Return a short lowercase ID safe for directory names."""
    raw_id = secrets.token_urlsafe(_ID_BYTES).lower()
    return "".join(char if char in _SAFE_ID_CHARS else "_" for char in raw_id)


def validate_safe_id(value: str) -> str:
    """Validate an ID before using it in a server-side path."""
    if not value or any(char not in _SAFE_ID_CHARS for char in value):
        raise ValueError("ID contains unsafe characters.")
    return value


def generate_crawl_id(now: datetime | None = None) -> str:
    """Return a crawl ID that sorts by start time and remains unique."""
    timestamp = (now or datetime.now(timezone.utc)).strftime(_TIMESTAMP_FORMAT)
    return f"{timestamp}_{generate_safe_id()}"


def session_dir(sessions_root: Path | str, session_id: str) -> Path:
    """Return the directory for one Streamlit browser session."""
    safe_session_id = validate_safe_id(session_id)
    return Path(sessions_root) / f"{_SESSION_PREFIX}{safe_session_id}"


def crawl_output_base(sessions_root: Path | str, session_id: str, crawl_id: str) -> Path:
    """Return the output base directory for one crawl run."""
    safe_crawl_id = validate_safe_id(crawl_id)
    return session_dir(sessions_root, session_id) / f"{_CRAWL_PREFIX}{safe_crawl_id}"


def ensure_within_root(root: Path | str, path: Path | str) -> Path:
    """Resolve *path* and reject it if it escapes *root*."""
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError("Path is outside the allowed session folder.")
    return resolved_path


def prepare_session_dir(sessions_root: Path | str, session_id: str) -> Path:
    """Create and return the current Streamlit session directory."""
    path = session_dir(sessions_root, session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_crawl_output_base(sessions_root: Path | str, session_id: str, crawl_id: str) -> Path:
    """Create and return the output base for one crawl run."""
    path = crawl_output_base(sessions_root, session_id, crawl_id)
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_configs(values: Mapping[str, Any]) -> tuple[CrawlerConfig, PageConfig, int]:
    """Build crawl configs from Streamlit form values."""
    crawler_config = CrawlerConfig(
        urls=values["urls"],
        exclude_paths=values.get("exclude_paths", ""),
        include_only_paths=values.get("include_only_paths", ""),
        limit=int(values.get("limit", 1)),
        max_depth=int(values.get("max_depth", 1)),
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
    activity_log_size = int(values.get("activity_log_size", _DEFAULT_ACTIVITY_LOG_SIZE))
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


def list_generated_files(
    session_root: Path | str,
    search_root: Path | str | None = None,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> list[GeneratedFile]:
    """List generated files under the current session only."""
    root = Path(session_root).resolve()
    target_root = ensure_within_root(root, search_root or root)
    files: list[GeneratedFile] = []
    if not target_root.exists():
        return files
    for path in sorted(target_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(_HIDDEN_FILE_PREFIX) for part in relative.parts):
            continue
        safe_path = ensure_within_root(root, path)
        stat = safe_path.stat()
        file_type = safe_path.suffix.lower().lstrip(".") or "file"
        files.append(
            GeneratedFile(
                path=safe_path,
                relative_path=relative.as_posix(),
                name=safe_path.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                file_type=file_type,
                download_allowed=stat.st_size <= download_limit_bytes,
            )
        )
    return files


def read_recent_lines(path: Path | str, *, max_lines: int) -> list[str]:
    """Read the last *max_lines* lines from a UTF-8 text file."""
    if max_lines < 1:
        return []
    log_path = Path(path)
    if not log_path.exists() or not log_path.is_file():
        return []
    return log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def find_latest_crawl_dir(crawl_base: Path | str) -> Path | None:
    """Return the newest crawler-created output directory under a crawl base."""
    base = Path(crawl_base)
    if not base.exists():
        return None
    candidates = [path for path in base.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def activity_log_path(crawl_dir: Path | str | None) -> Path | None:
    """Return the activity log path for a crawl output directory when present."""
    if crawl_dir is None:
        return None
    path = Path(crawl_dir) / _ACTIVITY_LOG_FILE
    return path if path.exists() else None


def cleanup_old_sessions(
    sessions_root: Path | str = _DEFAULT_SESSIONS_ROOT,
    *,
    active_session_ids: Iterable[str] = (),
    retention_days: int = _DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> list[Path]:
    """Delete inactive session folders older than the retention period."""
    root = Path(sessions_root)
    root.mkdir(parents=True, exist_ok=True)
    active_ids = {validate_safe_id(session_id) for session_id in active_session_ids}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not path.name.startswith(_SESSION_PREFIX):
            continue
        session_id = path.name.removeprefix(_SESSION_PREFIX)
        try:
            validate_safe_id(session_id)
        except ValueError:
            continue
        if session_id in active_ids:
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified_at >= cutoff:
            continue
        shutil.rmtree(path)
        removed.append(path)
    if removed:
        log_path = root / _CLEANUP_LOG_FILE
        timestamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        lines = [f"{timestamp} removed {path.name}" for path in removed]
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return removed


def cleanup_old_sessions_with_lock(
    sessions_root: Path | str = _DEFAULT_SESSIONS_ROOT,
    *,
    active_session_ids: Iterable[str] = (),
    retention_days: int = _DEFAULT_RETENTION_DAYS,
) -> list[Path]:
    """Run cleanup under a lightweight lock file."""
    root = Path(sessions_root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / _CLEANUP_LOCK_FILE
    if _lock_is_stale(lock_path):
        lock_path.unlink(missing_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return []
    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return cleanup_old_sessions(
            root,
            active_session_ids=active_session_ids,
            retention_days=retention_days,
        )
    finally:
        lock_path.unlink(missing_ok=True)


def start_crawl_job(
    *,
    session_id: str,
    crawl_id: str,
    crawler_config: CrawlerConfig,
    page_config: PageConfig,
    activity_log_size: int,
    sessions_root: Path | str = _DEFAULT_SESSIONS_ROOT,
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
                extractor=extractor,
                writer=writer,
                activity_log_size=activity_log_size,
                progress_callback=emit,
                should_cancel=cancel_event.is_set,
            )
            results = crawler.crawl()
            success_count = sum(1 for result in results if result.success)
            fail_count = len(results) - success_count
            state = "cancelled" if cancel_event.is_set() else _EVENT_COMPLETED
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
        return _PLAYWRIGHT_MISSING_BROWSER_MESSAGE
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
) -> Literal["idle", "running", "completed", "failed", "cancel_requested", "cancelled"]:
    """Map a worker event name to the user-facing job state."""
    if event_name == _EVENT_STARTED:
        return "running"
    if event_name == _EVENT_COMPLETED:
        return "completed"
    if event_name == _EVENT_FAILED:
        return "failed"
    if event_name == _EVENT_CANCEL_REQUESTED:
        return "cancel_requested"
    if event_name == "cancelled":
        return "cancelled"
    return "running"


def _lock_is_stale(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    modified_at = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - modified_at
    return age.total_seconds() > _LOCK_STALE_SECONDS
