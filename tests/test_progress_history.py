"""Tests for persisted crawl progress history JSONL output."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md._internal.progress_history import ProgressHistoryRecorder
from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import _PROGRESS_HISTORY_FILE, SiteCrawler
from tests.conftest import _make_mock_result


def _read_history(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@patch("crawl4md.crawler.AsyncWebCrawler")
def test_progress_history_records_started_page_and_completed(
    mock_crawler_cls, tmp_path: Path
) -> None:
    mock_instance = AsyncMock()
    mock_instance.arun = AsyncMock(
        return_value=_make_mock_result("https://example.com", "<p>ok</p>", "ok")
    )
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_crawler_cls.return_value = mock_instance

    crawler = SiteCrawler(
        CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0, flush_interval=1),
        PageConfig(extract_main_content=False),
        output_base=tmp_path,
    )
    crawler.crawl()

    assert crawler.output_dir is not None
    history_path = crawler.output_dir / _PROGRESS_HISTORY_FILE
    assert history_path.exists()

    rows = _read_history(history_path)
    event_names = [str(row["event"]) for row in rows]
    assert "crawl_started" in event_names
    assert "page_processed" in event_names
    assert "crawl_completed" in event_names

    page_row = next(row for row in rows if row["event"] == "page_processed")
    assert page_row["page_limit"] == 1
    assert page_row["discovered_pages"] >= 1
    assert page_row["successful_pages"] == 1
    assert page_row["failed_pages"] == 0
    assert page_row["processed_pages"] == 1


def test_progress_history_recorder_carries_previous_counters_for_sparse_events(
    tmp_path: Path,
) -> None:
    recorder = ProgressHistoryRecorder(output_dir=tmp_path, session_id="session_123")

    recorder.record({"event": "crawl_started", "limit": 9})
    recorder.record(
        {
            "event": "page_processed",
            "limit": 9,
            "queued_discovered_urls": 4,
            "successful_pages": 3,
            "failed_pages": 1,
            "processed_pages": 4,
        }
    )
    recorder.record(
        {
            "event": "urls_discovered",
            "limit": 9,
            "queued_discovered_urls": 7,
        }
    )

    rows = _read_history(recorder.path)
    assert len(rows) == 3
    last = rows[-1]
    assert last["event"] == "urls_discovered"
    assert last["discovered_pages"] == 7
    assert last["successful_pages"] == 3
    assert last["failed_pages"] == 1
    assert last["processed_pages"] == 4


@patch("crawl4md.crawler.AsyncWebCrawler")
def test_progress_history_rows_include_retry_round_values(mock_crawler_cls, tmp_path: Path) -> None:
    ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok")
    blocked_result = _make_mock_result(
        "https://example.com/retry",
        "<html><body>Request unsuccessful. Incapsula incident ID: 99</body></html>",
        "blocked",
    )
    retried_result = _make_mock_result("https://example.com/retry", "<p>retry ok</p>", "retry ok")

    call_count = {"retry": 0}

    async def _mock_arun(url, config):
        _ = config
        if url == "https://example.com/ok":
            return ok_result
        call_count["retry"] += 1
        if call_count["retry"] == 1:
            return blocked_result
        return retried_result

    mock_instance = AsyncMock()
    mock_instance.arun = _mock_arun
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_crawler_cls.return_value = mock_instance

    crawler = SiteCrawler(
        CrawlerConfig(
            urls=["https://example.com/ok", "https://example.com/retry"],
            limit=10,
            max_retries=1,
            flush_interval=1,
        ),
        PageConfig(extract_main_content=False),
        output_base=tmp_path,
    )
    crawler.crawl()

    assert crawler.output_dir is not None
    rows = _read_history(crawler.output_dir / _PROGRESS_HISTORY_FILE)
    assert any(int(row["round"]) == 2 for row in rows)


@patch("crawl4md.crawler.AsyncWebCrawler")
def test_progress_history_records_interrupt_event(mock_crawler_cls, tmp_path: Path) -> None:
    first = _make_mock_result("https://example.com/a", "<p>a</p>", "a")

    call_count = {"n": 0}

    async def _mock_arun(url, config):
        _ = (url, config)
        call_count["n"] += 1
        if call_count["n"] == 1:
            return first
        raise asyncio.CancelledError()

    mock_instance = AsyncMock()
    mock_instance.arun = _mock_arun
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_crawler_cls.return_value = mock_instance

    crawler = SiteCrawler(
        CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=5,
            max_retries=0,
            flush_interval=1,
        ),
        PageConfig(extract_main_content=False),
        output_base=tmp_path,
    )
    crawler.crawl()

    assert crawler.output_dir is not None
    rows = _read_history(crawler.output_dir / _PROGRESS_HISTORY_FILE)
    assert any(str(row["event"]) == "crawl_interrupted" for row in rows)
