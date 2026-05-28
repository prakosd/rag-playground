"""Progress event helpers for crawler integrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from crawl4md.config import CrawlResult

__all__ = [
    "emit_page_progress",
    "emit_progress",
]

_PROGRESS_EVENT_COMPLETED = "crawl_completed"
_PROGRESS_EVENT_DISCOVERED = "urls_discovered"
_PROGRESS_EVENT_INTERRUPTED = "crawl_interrupted"
_PROGRESS_EVENT_PAGE = "page_processed"
_PROGRESS_EVENT_STARTED = "crawl_started"
_PROGRESS_EVENT_STATUS = "crawl_status"


def emit_progress(
    callback: Callable[[Mapping[str, object]], None] | None,
    event: Mapping[str, object],
) -> None:
    """Send a progress event to an optional UI integration."""
    if callback is None:
        return
    callback(event)


def emit_page_progress(
    callback: Callable[[Mapping[str, object]], None] | None,
    results: list[CrawlResult],
    *,
    generated: set[str],
    prior_success: int,
    prior_fail: int,
    current_url: str,
    output_dir: Path | None,
    limit: int,
    next_url: str = "",
    eta_remaining_seconds: float | None = None,
    active_urls: list[str] | None = None,
    active_url_count: int | None = None,
    next_urls: list[str] | None = None,
    next_url_count: int | None = None,
    max_concurrent: int | None = None,
) -> dict[str, object]:
    """Emit a compact page-progress event."""
    success_count = sum(1 for result in results if result.success)
    fail_count = len(results) - success_count
    event: dict[str, object] = {
        "event": _PROGRESS_EVENT_PAGE,
        "processed_pages": prior_success + prior_fail + len(results),
        "successful_pages": prior_success + success_count,
        "failed_pages": prior_fail + fail_count,
        "queued_discovered_urls": len(generated),
        "current_url": current_url,
        "next_url": next_url,
        "eta_remaining_seconds": eta_remaining_seconds,
        "output_dir": str(output_dir) if output_dir else "",
        "limit": limit,
    }
    if active_urls is not None:
        event["active_urls"] = active_urls
    if active_url_count is not None:
        event["active_url_count"] = active_url_count
    if next_urls is not None:
        event["next_urls"] = next_urls
    if next_url_count is not None:
        event["next_url_count"] = next_url_count
    if max_concurrent is not None:
        event["max_concurrent"] = max_concurrent
    emit_progress(
        callback,
        event,
    )
    return event
