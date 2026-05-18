"""Tests for crawler progress event helpers."""

from __future__ import annotations

from pathlib import Path

from crawl4md._internal.crawler_progress import emit_page_progress, emit_progress
from crawl4md.config import CrawlResult


def test_emit_progress_noops_without_callback() -> None:
    emit_progress(None, {"event": "anything"})


def test_emit_progress_sends_event_to_callback() -> None:
    events: list[object] = []
    event = {"event": "crawl_started", "limit": 2}

    emit_progress(events.append, event)

    assert events == [event]


def test_emit_page_progress_counts_results_and_metadata(tmp_path: Path) -> None:
    events: list[object] = []
    results = [
        CrawlResult(url="https://example.com/a", success=True),
        CrawlResult(url="https://example.com/b", success=False),
    ]

    emit_page_progress(
        events.append,
        results,
        generated={"a", "b", "c"},
        prior_success=1,
        prior_fail=2,
        current_url="https://example.com/b",
        output_dir=tmp_path,
        limit=10,
        next_url="https://example.com/c",
        eta_remaining_seconds=12.5,
    )

    assert events == [
        {
            "event": "page_processed",
            "processed_pages": 5,
            "successful_pages": 2,
            "failed_pages": 3,
            "queued_discovered_urls": 3,
            "current_url": "https://example.com/b",
            "next_url": "https://example.com/c",
            "eta_remaining_seconds": 12.5,
            "output_dir": str(tmp_path),
            "limit": 10,
        }
    ]


def test_emit_page_progress_includes_optional_concurrency_metadata(tmp_path: Path) -> None:
    events: list[object] = []
    results = [CrawlResult(url="https://example.com/a", success=True)]

    emit_page_progress(
        events.append,
        results,
        generated={"a", "b"},
        prior_success=0,
        prior_fail=0,
        current_url="https://example.com/a",
        output_dir=tmp_path,
        limit=10,
        next_url="https://example.com/b",
        eta_remaining_seconds=3.5,
        active_urls=["https://example.com/a"],
        active_url_count=4,
        next_urls=["https://example.com/b"],
        next_url_count=6,
        max_concurrent=20,
    )

    event = events[0]
    assert isinstance(event, dict)
    assert event["active_urls"] == ["https://example.com/a"]
    assert event["active_url_count"] == 4
    assert event["next_urls"] == ["https://example.com/b"]
    assert event["next_url_count"] == 6
    assert event["max_concurrent"] == 20
