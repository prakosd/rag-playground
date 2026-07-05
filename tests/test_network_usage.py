"""Tests for proxy/fallback-API usage logging (network_usage.csv)."""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from crawl4md._internal.network_usage import NETWORK_USAGE_FILE, NetworkUsageRecorder
from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from tests.conftest import _make_mock_result


class _FakeProxyConfig:
    """Minimal stand-in for crawl4ai.ProxyConfig used to avoid a real dependency."""

    DIRECT = object()

    def __init__(self, server: str) -> None:
        self.server = server

    @classmethod
    def from_string(cls, value: str) -> _FakeProxyConfig:
        return cls(value)


def _read_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


# --- NetworkUsageRecorder unit tests ----------------------------------------


def test_recorder_is_noop_without_reset() -> None:
    # No path configured yet — record must not raise or write anything.
    NetworkUsageRecorder().record(
        method="proxy", round_num=2, url="https://e.com", status="success", size_kb=1.0
    )


def test_recorder_writes_header_and_rows(tmp_path: Path) -> None:
    recorder = NetworkUsageRecorder()
    recorder.reset(tmp_path)
    recorder.record(
        method="proxy", round_num=2, url="https://e.com/a", status="success", size_kb=1.5
    )
    recorder.record(method="api", round_num=3, url="https://e.com/b", status="fail", size_kb=None)

    path = tmp_path / NETWORK_USAGE_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp,round,method,url,status,size_kb"

    rows = _read_rows(path)
    assert [row["method"] for row in rows] == ["proxy", "api"]
    assert rows[0]["round"] == "2"
    assert rows[0]["url"] == "https://e.com/a"
    assert rows[0]["status"] == "success"
    assert rows[0]["size_kb"] == "1.50"
    assert rows[1]["status"] == "fail"
    assert rows[1]["size_kb"] == ""


def test_recorder_appends_without_duplicate_header(tmp_path: Path) -> None:
    recorder = NetworkUsageRecorder()
    recorder.reset(tmp_path)
    recorder.record(method="proxy", round_num=2, url="u1", status="success", size_kb=None)
    recorder.record(method="proxy", round_num=2, url="u2", status="success", size_kb=None)

    lines = (tmp_path / NETWORK_USAGE_FILE).read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("timestamp,")
    assert len(_read_rows(tmp_path / NETWORK_USAGE_FILE)) == 2


# --- Crawler integration tests ----------------------------------------------


def _run_crawler(tmp_path: Path, config: CrawlerConfig, results: list[object]) -> SiteCrawler:
    mock_instance = AsyncMock()
    mock_instance.arun = AsyncMock(side_effect=results)
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("crawl4md.crawler.AsyncWebCrawler", return_value=mock_instance),
        patch("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig),
    ):
        crawler = SiteCrawler(config, PageConfig(extract_main_content=False), output_base=tmp_path)
        crawler.crawl()
    return crawler


def test_crawl_logs_proxy_usage_on_first_retry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fail = _make_mock_result("https://example.com", "<p>x</p>", "")
    fail.success = False
    fail.error = ""
    fail.markdown = ""
    fail.html = ""
    ok = _make_mock_result(
        "https://example.com", "<main><p>retry content</p></main>", "retry content " * 10
    )

    config = CrawlerConfig(
        urls=["https://example.com"],
        limit=1,
        max_retries=2,
        proxies=["http://user:pass@proxy:8080"],
    )
    with caplog.at_level(logging.INFO, logger="crawl4md"):
        crawler = _run_crawler(tmp_path, config, [fail, ok])

    assert crawler.output_dir is not None
    usage_path = crawler.output_dir / "logs" / NETWORK_USAGE_FILE
    rows = _read_rows(usage_path)
    # Round 2 (first retry) is the proxy round; the initial round is not logged.
    assert [row["round"] for row in rows] == ["2"]
    assert rows[0]["method"] == "proxy"
    assert rows[0]["url"] == "https://example.com"
    assert rows[0]["status"] == "success"
    # Proxy credentials must never leak into the usage log.
    assert "user:pass" not in usage_path.read_text(encoding="utf-8")
    # The same usage is surfaced in the terminal log (no credentials).
    proxy_logs = [r.getMessage() for r in caplog.records if "Fetched via proxy" in r.getMessage()]
    assert proxy_logs
    assert "https://example.com" in proxy_logs[0]
    assert "user:pass" not in proxy_logs[0]


def test_crawl_without_paid_resources_writes_no_usage_log(tmp_path: Path) -> None:
    fail = _make_mock_result("https://example.com", "<p>x</p>", "")
    fail.success = False
    fail.error = ""
    fail.markdown = ""
    fail.html = ""
    ok = _make_mock_result(
        "https://example.com", "<main><p>retry content</p></main>", "retry content " * 10
    )

    config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=2)
    crawler = _run_crawler(tmp_path, config, [fail, ok])

    assert crawler.output_dir is not None
    assert not (crawler.output_dir / "logs" / NETWORK_USAGE_FILE).exists()
