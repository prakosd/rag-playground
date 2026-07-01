"""Tests for crawl4md.crawler — output files, URL lists, and print_summary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md.config import CrawlerConfig, CrawlResult, ExtractedPage, PageConfig
from crawl4md.crawler import _PROGRESS_EVENT_PAGE, SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter, PageSidecar
from tests.conftest import _make_mock_result

_SITE_GRAPH_FILE = "site_graph.jsonl"
_LOGS_DIR = "logs"


def _read_pages_registry(output_dir: Path) -> list[dict[str, object]]:
    path = output_dir / _SITE_GRAPH_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _records_by_url(output_dir: Path) -> dict[str, dict[str, object]]:
    return {str(record["url"]): record for record in _read_pages_registry(output_dir / _LOGS_DIR)}


class TestFailContentFiles:
    """Tests for fail content file generation (symmetrical with success content)."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_progress_event_counts_empty_extraction_as_failure(
        self, mock_crawler_cls, tmp_path: Path
    ):
        class EmptyExtractor:
            def _extract_page(self, crawl_result: CrawlResult) -> ExtractedPage:
                return ExtractedPage(url=crawl_result.url, title="Empty", markdown="")

        events: list[dict[str, object]] = []
        mock_result = _make_mock_result(
            "https://example.com/empty",
            "<main><p>Visible page text with enough length to avoid PDF fallback.</p></main>",
            "Visible page text with enough length to avoid PDF fallback. " * 2,
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/empty"], limit=1, max_retries=0, flush_interval=1
        )
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config,
            PageConfig(extract_main_content=False),
            output_base=tmp_path,
            extractor=EmptyExtractor(),
            writer=writer,
            progress_callback=events.append,
        )

        results = crawler.crawl()

        page_events = [event for event in events if event.get("event") == _PROGRESS_EVENT_PAGE]
        assert results[0].success is False
        assert page_events[0]["successful_pages"] == 0
        assert page_events[0]["failed_pages"] == 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_storm_failures_have_sidecar_backed_final_content(
        self, mock_crawler_cls, tmp_path: Path
    ):
        events: list[dict[str, object]] = []
        target_url = "https://example.com/target"
        redirect_urls = [
            "https://example.com/redirect-1",
            "https://example.com/redirect-2",
            "https://example.com/redirect-3",
        ]
        target_result = _make_mock_result(
            target_url,
            "<main><p>Target page content long enough for extraction.</p></main>",
            "Target page content long enough for extraction. " * 2,
        )
        redirect_results = [
            _make_mock_result(redirect_url, redirected_url=target_url)
            for redirect_url in redirect_urls
        ]

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[target_result, *redirect_results])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target_url, *redirect_urls],
            limit=4,
            max_depth=1,
            max_retries=0,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            extractor=extractor,
            writer=writer,
            progress_callback=events.append,
        )
        results = crawler.crawl()

        assert crawler.output_dir is not None
        assert [result.url for result in results if not result.success] == redirect_urls

        final_dir = crawler.output_dir / "final"
        assert (final_dir / "fail_urls.txt").read_text(
            encoding="utf-8"
        ).splitlines() == redirect_urls
        final_fail_content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(final_dir.glob("sorted_fail_content_*.txt"))
        )
        for redirect_url in redirect_urls:
            assert redirect_url in final_fail_content

        page_events = [event for event in events if event.get("event") == _PROGRESS_EVENT_PAGE]
        redirect_page_events = [
            event for event in page_events if event.get("current_url") in redirect_urls
        ]
        assert [event["current_url"] for event in redirect_page_events[:3]] == redirect_urls
        assert [event["failed_pages"] for event in redirect_page_events[:3]] == [1, 2, 3]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_file_created_for_blocked_page(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages produce a fail content file with error and raw response."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        blocked_result = _make_mock_result(
            "https://example.com/blocked", blocked_html, "blocked page text"
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/blocked"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("initial/fail_content_*.txt"))
        assert len(fail_files) >= 1
        content = fail_files[0].read_text(encoding="utf-8")
        assert "https://example.com/blocked" in content
        assert "Blocked by WAF" in content
        assert "blocked page text" in content  # raw response preserved

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_includes_error_and_raw_markdown(self, mock_crawler_cls, tmp_path: Path):
        """Fail content contains both the error reason and the raw markdown response."""
        blocked_html = "<html><body>Access Denied</title></body></html>"
        blocked_result = _make_mock_result(
            "https://example.com/denied", blocked_html, "access denied markdown"
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/denied"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("initial/fail_content_*.txt"))
        assert len(fail_files) >= 1
        content = fail_files[0].read_text(encoding="utf-8")
        assert "**Error:** Blocked by WAF" in content
        assert "**Raw response:**" in content
        assert "access denied markdown" in content

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_no_fail_content_when_all_succeed(self, mock_crawler_cls, tmp_path: Path):
        """No fail content files are created when all pages succeed."""
        ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("**/fail_content*"))
        assert len(fail_files) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_not_created_without_writer(self, mock_crawler_cls, tmp_path: Path):
        """No fail content files when no writer is provided."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        blocked_result = _make_mock_result("https://example.com/x", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/x"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("**/fail_content*"))
        assert len(fail_files) == 0


class TestOutputFrontMatter:
    """Tests for YAML front matter metadata on generated content files."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_all_generated_content_files_include_front_matter(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """Every generated success/fail content file starts with required metadata."""
        ok_url = "https://example.com/ok"
        blocked_url = "https://example.com/blocked"

        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"

        async def _mock_arun(*, url, config):
            if url == blocked_url:
                return _make_mock_result(url, blocked_html, "blocked page text")
            return _make_mock_result(url, "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=_mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[ok_url, blocked_url],
            limit=2,
            max_retries=0,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        content_files = sorted(crawler.output_dir.glob("**/*content_*.txt"))
        assert content_files

        for file_path in content_files:
            content = file_path.read_text(encoding="utf-8")
            assert content.startswith("---\n")
            assert "crawl_start_datetime:" in content
            assert f'session_id: "{crawler.output_dir.name}"' in content
            assert f"stored_directory: {json.dumps(str(file_path.parent))}" in content
            assert "crawl_parameters:" in content
            if "fail_content_" in file_path.name:
                assert 'status: "failed"' in content
            else:
                assert 'status: "success"' in content

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_session_id_defaults_to_output_dir_name_even_under_app_like_path(
        self, mock_crawler_cls, tmp_path: Path
    ):
        output_base = (
            tmp_path
            / "outputs"
            / "streamlit_sessions"
            / "session_n25mbzlcfcpn"
            / "crawl_20260512_132924_iqlz0jd1_ukv"
        )

        mock_result = _make_mock_result("https://example.com/page", "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/page"],
            limit=1,
            max_retries=0,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config,
            page_config,
            output_base=output_base,
            extractor=extractor,
            writer=writer,
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        content_files = sorted(crawler.output_dir.glob("initial/success_content_*.txt"))
        assert content_files

        content = content_files[0].read_text(encoding="utf-8")
        assert f'session_id: "{crawler.output_dir.name}"' in content

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_session_id_can_be_set_explicitly(self, mock_crawler_cls, tmp_path: Path):
        explicit_session_id = "ui_session_abc123"
        mock_result = _make_mock_result("https://example.com/page", "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/page"],
            limit=1,
            max_retries=0,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            session_id=explicit_session_id,
            extractor=extractor,
            writer=writer,
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        content_files = sorted(crawler.output_dir.glob("initial/success_content_*.txt"))
        assert content_files

        content = content_files[0].read_text(encoding="utf-8")
        assert f'session_id: "{explicit_session_id}"' in content


class TestPagesRegistry:
    """Tests for the root-level deduped site_graph.jsonl graph source."""

    @staticmethod
    def _crawler_config(urls: list[str], **overrides: object) -> CrawlerConfig:
        values = {
            "urls": urls,
            "limit": 10,
            "max_depth": 2,
            "flush_interval": 1,
            "delay": 0,
        }
        values.update(overrides)
        return CrawlerConfig(**values)

    @staticmethod
    def _crawler(tmp_path: Path, config: CrawlerConfig, **kwargs: object) -> SiteCrawler:
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        return SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            extractor=extractor,
            writer=writer,
            **kwargs,
        )

    def test_async_flush_site_graph_writes_registry(self, tmp_path: Path) -> None:
        crawler = SiteCrawler(self._crawler_config(["https://example.com"]), output_base=tmp_path)
        crawler.output_dir = tmp_path
        crawler._site_graph_path = tmp_path / _SITE_GRAPH_FILE
        crawler._upsert_page_record(
            normalized_url="https://example.com/a",
            url="https://example.com/a",
            discovered_from="https://example.com",
            status="success",
            page_size_kb=1.25,
            graph_depth=1,
            round_num=1,
        )

        asyncio.run(crawler._flush_site_graph_async())

        assert _read_pages_registry(tmp_path) == [
            {
                "url": "https://example.com/a",
                "discovered_from": "https://example.com",
                "page_size_kb": 1.25,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            }
        ]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_records_successful_discovery(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        seed_url = "https://example.com"
        page_a = "https://example.com/a"
        page_b = "https://example.com/b"
        seed_html = (
            "<main><p>seed content with enough visible text for the crawler.</p>"
            '<a href="/a">A</a><a href="/b">B</a></main>'
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result(seed_url, seed_html, "seed markdown content" * 4),
                _make_mock_result(page_a, "<p>alpha content long enough</p>", "alpha" * 20),
                _make_mock_result(page_b, "<p>beta content long enough</p>", "beta" * 20),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(tmp_path, self._crawler_config([seed_url], limit=3))
        crawler.crawl()

        assert crawler.output_dir is not None
        records = _records_by_url(crawler.output_dir)

        assert set(records) == {seed_url, page_a, page_b}
        assert {record["status"] for record in records.values()} == {"success"}
        assert records[seed_url]["discovered_from"] is None
        assert records[seed_url]["depth"] == 0
        assert records[page_a]["discovered_from"] == seed_url
        assert records[page_a]["depth"] == 1
        assert records[page_a]["page_size_kb"] is not None
        assert not (crawler.output_dir / "final" / _SITE_GRAPH_FILE).exists()

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_preserves_parent_for_retry_failure(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        seed_url = "https://example.com"
        fail_url = "https://example.com/fail"
        seed_html = '<main><p>seed</p><a href="/fail">Fail</a></main>'
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result(seed_url, seed_html, "seed markdown content" * 4),
                _make_mock_result(fail_url, blocked_html, "blocked"),
                _make_mock_result(fail_url, blocked_html, "blocked"),
                _make_mock_result(fail_url, blocked_html, "blocked"),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(tmp_path, self._crawler_config([seed_url], max_retries=2))
        crawler.crawl()

        assert crawler.output_dir is not None
        record = _records_by_url(crawler.output_dir)[fail_url]

        assert record["status"] == "fail"
        assert record["page_size_kb"] is None
        assert record["discovered_from"] == seed_url
        assert record["depth"] == 1
        assert record["round_num"] == 3

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_records_skipped_links(self, mock_crawler_cls, tmp_path: Path) -> None:
        seed_url = "https://example.com"
        external_url = "https://external.example/about"
        excluded_url = "https://example.com/admin"
        seed_html = (
            "<main><p>seed content with enough visible text for links.</p>"
            '<a href="https://external.example/about">External</a>'
            '<a href="/admin">Admin</a>'
            '<a href="/style.css">Style</a></main>'
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result(seed_url, seed_html, "seed markdown content" * 4)
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = self._crawler_config([seed_url], exclude_paths=[r"/admin"])
        crawler = self._crawler(tmp_path, config)
        results = crawler.crawl()

        assert crawler.output_dir is not None
        records = _records_by_url(crawler.output_dir)

        assert len(results) == 1
        assert mock_instance.arun.await_count == 1
        assert external_url not in records
        assert records[excluded_url]["status"] == "skipped"
        assert records[excluded_url]["discovered_from"] == seed_url
        assert records[excluded_url]["depth"] == 1
        assert records[excluded_url]["page_size_kb"] is None
        assert all("style.css" not in url for url in records)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_flushes_discovered_page_on_cancel(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        seed_url = "https://example.com"
        child_url = "https://example.com/child"
        seed_html = '<main><p>seed</p><a href="/child">Child</a></main>'
        cancel_checks = 0

        def should_cancel() -> bool:
            nonlocal cancel_checks
            cancel_checks += 1
            return cancel_checks > 1

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result(seed_url, seed_html, "seed markdown content" * 4)
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(
            tmp_path,
            self._crawler_config([seed_url]),
            should_cancel=should_cancel,
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        records = _records_by_url(crawler.output_dir)

        assert records[seed_url]["status"] == "success"
        assert records[child_url]["status"] == "discovered"
        assert records[child_url]["page_size_kb"] is None
        assert records[child_url]["round_num"] is None
        assert not (crawler.output_dir / "final" / _SITE_GRAPH_FILE).exists()

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_keeps_first_parent_for_duplicate_links(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        seed_url = "https://example.com"
        parent_a = "https://example.com/a"
        parent_b = "https://example.com/b"
        child_url = "https://example.com/child"
        seed_html = '<main><a href="/a">A</a><a href="/b">B</a></main>'
        parent_html = '<main><p>parent</p><a href="/child">Child</a></main>'

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result(seed_url, seed_html, "seed markdown content" * 4),
                _make_mock_result(parent_a, parent_html, "parent a markdown" * 4),
                _make_mock_result(parent_b, parent_html, "parent b markdown" * 4),
                _make_mock_result(child_url, "<p>child</p>", "child markdown" * 4),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(tmp_path, self._crawler_config([seed_url], max_depth=3))
        crawler.crawl()

        assert crawler.output_dir is not None
        records = _records_by_url(crawler.output_dir)

        assert len(records) == 4
        assert records[child_url]["discovered_from"] == parent_a

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_moves_record_for_redirect(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        source_url = "https://example.com/a"
        redirected_url = "https://example.com/a/"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result(
                source_url,
                "<p>redirected content</p>",
                "redirected markdown" * 4,
                redirected_url=redirected_url,
            )
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(tmp_path, self._crawler_config([source_url], limit=1))
        crawler.crawl()

        assert crawler.output_dir is not None
        records = _records_by_url(crawler.output_dir)

        assert set(records) == {redirected_url}
        assert records[redirected_url]["status"] == "success"
        assert records[redirected_url]["discovered_from"] is None
        assert records[redirected_url]["depth"] == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_pages_registry_removes_redirect_outside_filter(
        self, mock_crawler_cls, tmp_path: Path
    ) -> None:
        source_url = "https://example.com/start"
        redirected_url = "https://external.example/out"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result(
                source_url,
                "<p>external redirect</p>",
                "external redirect markdown" * 4,
                redirected_url=redirected_url,
            )
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        crawler = self._crawler(tmp_path, self._crawler_config([source_url], limit=1))
        results = crawler.crawl()

        assert crawler.output_dir is not None
        assert results == []
        assert _read_pages_registry(crawler.output_dir / _LOGS_DIR) == []


class TestPrintSummary:
    """Tests for SiteCrawler.print_summary()."""

    def test_prints_success_and_fail_counts(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=True),
            CrawlResult(url="https://example.com/b", success=False, error="fail"),
        ]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "1 succeeded" in out
        assert "1 failed" in out
        assert str(tmp_path) in out

    def test_prints_round_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        # Create dummy round files in round_1/ subdir
        round_1_dir = tmp_path / "round_1"
        round_1_dir.mkdir()
        (round_1_dir / "success_content_001.md").write_text("x" * 100, encoding="utf-8")
        (round_1_dir / "success_urls.txt").write_text("https://example.com/a", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "--- round_1 ---" in out
        assert "success_content_001.md" in out

    def test_prints_sorted_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        final_dir = tmp_path / "final"
        final_dir.mkdir()
        (final_dir / "sorted_success_content_001.md").write_text("data", encoding="utf-8")
        (final_dir / "sorted_success_urls.txt").write_text("url", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "Sorted by URL path" in out
        assert "sorted_success_content_001.md" in out

    def test_prints_fail_hint(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=False, error="blocked"),
            CrawlResult(url="https://example.com/b", success=False, error="blocked"),
        ]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "2 URL(s) that could not be crawled" in out

    def test_no_output_dir_shows_message(self, capsys):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)
        crawler.output_dir = None

        crawler.print_summary([])
        out = capsys.readouterr().out
        assert "No output folder found" in out

    def test_prints_final_unsorted_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        final_dir = tmp_path / "final"
        final_dir.mkdir()
        (final_dir / "success_content_001.md").write_text("data", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "Final (unsorted" in out
        assert "success_content_001.md" in out

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_merged_across_rounds(self, mock_crawler_cls, tmp_path: Path):
        """Fail content from multiple rounds is merged into final fail_content files."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        blocked_result = _make_mock_result(
            "https://example.com/stuck", blocked_html, "still blocked"
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/stuck"], limit=1, max_retries=1, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        # Per-round fail content files from both rounds
        round1_fail = list(crawler.output_dir.glob("initial/fail_content_*.txt"))
        round2_fail = list(crawler.output_dir.glob("round_1/fail_content_*.txt"))
        assert len(round1_fail) >= 1
        assert len(round2_fail) >= 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_skips_already_succeeded_url(self, mock_crawler_cls, tmp_path: Path):
        """A retry round should not re-crawl a URL that already succeeded."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")

        # Round 2: B is retried, but redirects to A (already succeeded)
        result_b_redirect = _make_mock_result(url_b, redirected_url=url_a)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_redirect])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # A should appear only once in the success results
        success_urls = [r.url for r in results if r.success]
        assert success_urls.count(url_a) == 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_sorted_files_no_duplicates(self, mock_crawler_cls, tmp_path: Path):
        """Sorted final URL files should contain no duplicate URLs."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")

        # Round 2: B succeeds
        result_b_ok = _make_mock_result(url_b)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_ok])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None

        # Check sorted final success URLs have no duplicates
        sorted_urls_path = crawler.output_dir / "final" / "sorted_success_urls.txt"
        if sorted_urls_path.exists():
            urls = sorted_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), (
                f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"
            )

        # Check final success URLs have no duplicates
        final_urls_path = crawler.output_dir / "final" / "success_urls.txt"
        if final_urls_path.exists():
            urls = final_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), (
                f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"
            )

        # Check final fail URLs have no duplicates (if any)
        final_fail_path = crawler.output_dir / "final" / "fail_urls.txt"
        if final_fail_path.exists():
            urls = final_fail_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), (
                f"Duplicate fail URLs found: {[u for u in urls if urls.count(u) > 1]}"
            )


class TestSaveUrlLists:
    """Tests for per-round URL list splitting."""

    def test_splits_success_and_fail(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        success = [CrawlResult(url="https://example.com/a", success=True)]
        fail = [CrawlResult(url="https://example.com/b", success=False, error="Blocked")]
        round_1_dir = tmp_path / "round_1"
        round_1_dir.mkdir()
        crawler._save_url_lists(success, fail, round_1_dir)

        assert (round_1_dir / "success_urls.txt").read_text(
            encoding="utf-8"
        ) == "https://example.com/a"
        assert (round_1_dir / "fail_urls.txt").read_text(
            encoding="utf-8"
        ) == "https://example.com/b"

    def test_no_fail_file_when_all_succeed(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        success = [CrawlResult(url="https://example.com/a", success=True)]
        round_1_dir = tmp_path / "round_1"
        round_1_dir.mkdir()
        crawler._save_url_lists(success, [], round_1_dir)

        assert (round_1_dir / "success_urls.txt").exists()
        assert not (round_1_dir / "fail_urls.txt").exists()


@patch("crawl4md._internal.final_output._CLEANUP_INTERMEDIATE_FILES", False)
class TestFinalUnsortedContentFiles:
    """Tests for unsorted final_success_content / final_fail_content file generation.

    These tests run with _CLEANUP_INTERMEDIATE_FILES=False so unsorted files
    are kept on disk, allowing direct assertion against them.
    """

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_unsorted_content_created(self, mock_crawler_cls, tmp_path: Path):
        """final_success_content files are created when extractor/writer are provided."""
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_result = _make_mock_result("https://example.com", html, "Hello world")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        final_files = list(crawler.output_dir.glob("final/success_content_*.txt"))
        assert len(final_files) >= 1
        content = final_files[0].read_text(encoding="utf-8")
        assert "https://example.com" in content

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_no_final_fail_content_when_all_succeed(self, mock_crawler_cls, tmp_path: Path):
        """No final_fail_content files when all pages succeed."""
        ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("final/fail_content*"))
        assert len(fail_files) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_fail_content_created_for_blocked_page(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages produce final_fail_content files."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        blocked_result = _make_mock_result(
            "https://example.com/blocked", blocked_html, "blocked page text"
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/blocked"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("final/fail_content_*.txt"))
        assert len(fail_files) >= 1
        content = fail_files[0].read_text(encoding="utf-8")
        assert "https://example.com/blocked" in content
        assert "Blocked by WAF" in content

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_unsorted_no_duplicates(self, mock_crawler_cls, tmp_path: Path):
        """Multi-round crawl produces final content with no duplicate pages."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")

        # Round 2: B succeeds
        result_b_ok = _make_mock_result(url_b)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_ok])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        final_files = list(crawler.output_dir.glob("final/success_content_*.txt"))
        assert len(final_files) >= 1
        content = final_files[0].read_text(encoding="utf-8")
        # Both source blocks should appear exactly once
        assert content.count(f"*Source: {url_a}*") == 1
        assert content.count(f"*Source: {url_b}*") == 1


class TestRoundSuccessSnapshots:
    """Tests for cumulative per-round success URL/content snapshots."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_round_success_files_are_cumulative(self, mock_crawler_cls, tmp_path: Path):
        """round_2_success files include successes from round 1 and round 2."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")
        # Round 2: B succeeds
        result_b_ok = _make_mock_result(url_b)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_ok])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None

        round_1_success_urls = (crawler.output_dir / "initial" / "success_urls.txt").read_text(
            encoding="utf-8"
        )
        assert round_1_success_urls == url_a

        round_2_success_urls = (crawler.output_dir / "round_1" / "success_urls.txt").read_text(
            encoding="utf-8"
        )
        assert round_2_success_urls.splitlines() == [url_a, url_b]

        round_2_files = list(crawler.output_dir.glob("round_1/success_content_*.txt"))
        assert len(round_2_files) >= 1
        round_2_content = round_2_files[0].read_text(encoding="utf-8")
        assert round_2_content.count(f"*Source: {url_a}*") == 1
        assert round_2_content.count(f"*Source: {url_b}*") == 1


@patch("crawl4md._internal.final_output._ENABLE_SORTED_ROUND_FILES", True)
@patch("crawl4md.crawler._ENABLE_SORTED_ROUND_FILES", True)
class TestSortedRoundFiles:
    """Tests for per-round sorted content and URL file generation.

    These tests run with _ENABLE_SORTED_ROUND_FILES=True (i.e. cleanup disabled)
    so per-round sorted files are written and can be asserted against.
    """

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_round_success_files_created(self, mock_crawler_cls, tmp_path: Path):
        """A single-round crawl produces sorted_round_1_success_content and URL files."""
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_result = _make_mock_result("https://example.com/page", html, "Hello world")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/page"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        sorted_files = list(crawler.output_dir.glob("initial/sorted_success_content_*.txt"))
        assert len(sorted_files) >= 1
        content = sorted_files[0].read_text(encoding="utf-8")
        assert "https://example.com/page" in content

        sorted_urls = crawler.output_dir / "initial" / "sorted_success_urls.txt"
        assert sorted_urls.exists()
        assert "https://example.com/page" in sorted_urls.read_text(encoding="utf-8")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_round_fail_files_created(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages produce sorted_round_1_fail_content and URL files."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        blocked_result = _make_mock_result(
            "https://example.com/blocked", blocked_html, "blocked page text"
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/blocked"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        sorted_fail_files = list(crawler.output_dir.glob("initial/sorted_fail_content_*.txt"))
        assert len(sorted_fail_files) >= 1
        content = sorted_fail_files[0].read_text(encoding="utf-8")
        assert "https://example.com/blocked" in content
        assert "Blocked by WAF" in content

        sorted_fail_urls = crawler.output_dir / "initial" / "sorted_fail_urls.txt"
        assert sorted_fail_urls.exists()
        assert "https://example.com/blocked" in sorted_fail_urls.read_text(encoding="utf-8")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_round_no_files_without_writer(self, mock_crawler_cls, tmp_path: Path):
        """No sorted round files are created when no writer is provided."""
        mock_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok"], limit=1, max_retries=0, flush_interval=1
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        assert crawler.output_dir is not None
        sorted_files = list(crawler.output_dir.glob("round_*/sorted_*"))
        assert len(sorted_files) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_round_files_cumulative_across_rounds(self, mock_crawler_cls, tmp_path: Path):
        """sorted_round_2 success contains pages from both round 1 and round 2."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")
        # Round 2: B succeeds
        result_b_ok = _make_mock_result(url_b)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_ok])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None

        # Round 2 sorted success URLs should contain both A and B
        sorted_r2_urls = crawler.output_dir / "round_1" / "sorted_success_urls.txt"
        assert sorted_r2_urls.exists()
        urls = sorted_r2_urls.read_text(encoding="utf-8").strip().split("\n")
        assert set(urls) == {url_a, url_b}

        # Sorted content should contain both
        sorted_r2_files = list(crawler.output_dir.glob("round_1/sorted_success_content_*.txt"))
        assert len(sorted_r2_files) >= 1
        content = sorted_r2_files[0].read_text(encoding="utf-8")
        assert url_a in content
        assert url_b in content


class TestPrintSummarySortedRound:
    """Tests for print_summary display of sorted round files."""

    def test_prints_sorted_round_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        # Unsorted round files (needed for round detection)
        round_1_dir = tmp_path / "round_1"
        round_1_dir.mkdir()
        (round_1_dir / "success_content_001.md").write_text("x", encoding="utf-8")
        # Sorted round files
        (round_1_dir / "sorted_success_content_001.md").write_text("x", encoding="utf-8")
        (round_1_dir / "sorted_success_urls.txt").write_text("url", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "round_1 (sorted)" in out
        assert "sorted_success_content_001.md" in out


class TestInterruptHandling:
    """Tests for graceful handling of KeyboardInterrupt during crawl."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_interrupt_produces_final_files(self, mock_crawler_cls, tmp_path: Path):
        """Interrupt mid-crawl still writes final and sorted files from completed data."""
        url_a = "https://example.com/a"
        result_a = _make_mock_result(url_a)

        call_count = {"n": 0}

        async def mock_arun(url, config=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return result_a
            raise asyncio.CancelledError()

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[url_a, "https://example.com/b"], limit=10, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        # Final files should exist (from whatever completed before interrupt)
        final_urls = crawler.output_dir / "final" / "success_urls.txt"
        if final_urls.exists():
            assert url_a in final_urls.read_text(encoding="utf-8")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_interrupt_writes_final_files_without_session_artifacts(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """Stopping a crawl keeps completed pages without saved-session state."""
        url_a = "https://example.com/a"
        result_a = _make_mock_result(url_a)
        call_count = {"count": 0}

        async def mock_arun(url, config=None):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return result_a
            raise asyncio.CancelledError()

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[url_a, "https://example.com/b"], limit=10, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        crawler = SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            extractor=ContentExtractor(page_config),
            writer=FileWriter(max_file_size_mb=15.0),
        )

        results = crawler.crawl()

        assert crawler.output_dir is not None
        final_urls = crawler.output_dir / "final" / "success_urls.txt"
        assert url_a in final_urls.read_text(encoding="utf-8")
        assert [result.url for result in results if result.success] == [url_a]
        assert not (crawler.output_dir / "session.jsonl").exists()
        assert not (crawler.output_dir / "session_checkpoint.json").exists()

    def test_final_files_are_rebuilt_without_stale_content(self, tmp_path: Path):
        """Regenerating final files replaces old content and stale URL lists."""
        url_a = "https://example.com/a"
        session_dir = tmp_path / "2026-05-06_12-00-00"
        round_dir = session_dir / "round_1"
        final_dir = session_dir / "final"
        round_dir.mkdir(parents=True)
        final_dir.mkdir()
        PageSidecar.append(
            ExtractedPage(url=url_a, title="A", markdown="fresh content"),
            round_dir / "success_pages.jsonl",
        )
        (final_dir / "success_content_001.md").write_text("stale content", encoding="utf-8")
        (final_dir / "success_content_002.md").write_text("stale extra", encoding="utf-8")
        (final_dir / "fail_content_001.md").write_text("stale fail", encoding="utf-8")
        (final_dir / "sorted_success_content_001_of_999.md").write_text(
            "stale sorted", encoding="utf-8"
        )
        (final_dir / "sorted_fail_content_001_of_999.md").write_text(
            "stale sorted fail", encoding="utf-8"
        )
        (final_dir / "fail_urls.txt").write_text("https://example.com/old", encoding="utf-8")

        page_config = PageConfig(output_extension=".md")
        crawler = SiteCrawler(
            CrawlerConfig(urls=[url_a]),
            page_config,
            output_base=tmp_path,
            writer=FileWriter(max_file_size_mb=15.0, file_extension=".md"),
        )
        crawler.output_dir = session_dir
        crawler._write_final_files([CrawlResult(url=url_a, success=True)], [])
        crawler._write_sorted_files([CrawlResult(url=url_a, success=True)], [])

        # With _CLEANUP_INTERMEDIATE_FILES=True (default), unsorted content files
        # are removed after sorted files are written.
        sorted_success_files = sorted(final_dir.glob("sorted_success_content_*.md"))
        assert [path.name for path in sorted_success_files] == [
            "sorted_success_content_001_of_001.md"
        ]
        assert "stale" not in sorted_success_files[0].read_text(encoding="utf-8")
        assert "fresh content" in sorted_success_files[0].read_text(encoding="utf-8")
        assert not list(final_dir.glob("success_content_*.md"))  # cleaned up
        assert not (final_dir / "fail_urls.txt").exists()
        assert not (final_dir / "sorted_fail_urls.txt").exists()
        assert not list(final_dir.glob("fail_content_*.md"))
        assert not list(final_dir.glob("sorted_fail_content_*.md"))

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_interrupt_returns_partial_results(self, mock_crawler_cls, tmp_path: Path):
        """crawl() returns completed round results on interrupt, not an error."""
        url_a = "https://example.com/a"
        result_a = _make_mock_result(url_a)

        call_count = {"n": 0}

        async def mock_arun(url, config=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return result_a
            raise asyncio.CancelledError()

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[url_a, "https://example.com/b"], limit=10, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        results = crawler.crawl()

        # Should not raise, should return a list (possibly empty or partial)
        assert isinstance(results, list)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_interrupt_prints_interrupted_message(self, mock_crawler_cls, tmp_path: Path, capsys):
        """Interrupt produces 'Interrupted!' message instead of a traceback."""

        async def mock_arun(url, config=None):
            raise asyncio.CancelledError()

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a"], limit=1, max_retries=0, flush_interval=1
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        out = capsys.readouterr().out
        assert "Interrupted" in out


class TestSidecarFiles:
    """Tests for JSONL sidecar files and memory-efficient field stripping."""

    @patch("crawl4md._internal.final_output._CLEANUP_INTERMEDIATE_FILES", False)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sidecar_files_created(self, mock_crawler_cls, tmp_path: Path):
        """Crawl creates success and fail JSONL sidecar files (cleanup disabled)."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        ok_result = _make_mock_result(
            "https://example.com/ok",
            "<html><body><p>Good content here is long enough to pass</p></body></html>",
            "Good content here is long enough to pass",
        )
        blocked_result = _make_mock_result("https://example.com/blocked", blocked_html, "short")

        call_count = 0

        async def mock_arun(url, config=None):
            nonlocal call_count
            call_count += 1
            if "blocked" in url:
                return blocked_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok", "https://example.com/blocked"],
            limit=2,
            max_retries=0,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        # Success sidecar exists with at least 1 page
        success_sidecars = list(crawler.output_dir.glob("initial/success_pages.jsonl"))
        assert len(success_sidecars) >= 1
        success_pages = list(PageSidecar.read_pages(success_sidecars[0]))
        assert len(success_pages) >= 1
        assert any(p.url == "https://example.com/ok" for p in success_pages)

        # Fail sidecar exists
        fail_sidecars = list(crawler.output_dir.glob("initial/fail_pages.jsonl"))
        assert len(fail_sidecars) >= 1
        fail_pages = list(PageSidecar.read_pages(fail_sidecars[0]))
        assert len(fail_pages) >= 1
        assert any(p.url == "https://example.com/blocked" for p in fail_pages)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sidecar_files_deleted_after_crawl(self, mock_crawler_cls, tmp_path: Path):
        """With _CLEANUP_INTERMEDIATE_FILES=True (default), sidecars are gone after crawl."""
        ok_result = _make_mock_result(
            "https://example.com/page",
            "<html><body><p>Good content here is long enough</p></body></html>",
            "Good content here is long enough",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/page"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        # Sidecars should be gone — final sorted output was built from them then they were removed
        assert not list(crawler.output_dir.glob("round_*/success_pages.jsonl"))
        assert not list(crawler.output_dir.glob("round_*/fail_pages.jsonl"))
        # Final sorted output should exist, proving the sidecars were used before deletion
        final_dir = crawler.output_dir / "final"
        assert list(final_dir.glob("sorted_success_content_*"))

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_crawl_results_have_stripped_fields(self, mock_crawler_cls, tmp_path: Path):
        """Returned CrawlResult objects have empty html and markdown after crawl."""
        ok_result = _make_mock_result(
            "https://example.com/page",
            "<html><body><p>Real content</p></body></html>",
            "Real content",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/page"], limit=1, max_retries=0, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        results = crawler.crawl()

        assert len(results) == 1
        # Heavy fields are stripped after content is persisted to disk
        assert results[0].html == ""
        assert results[0].markdown == ""
        # Lightweight metadata is preserved
        assert results[0].url == "https://example.com/page"
        assert results[0].success is True

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_files_built_from_sidecars(self, mock_crawler_cls, tmp_path: Path):
        """Final sorted content files contain correct content from sidecars."""
        pages_data = [
            ("https://example.com/b/page", "Page B content is real text"),
            ("https://example.com/a/page", "Page A content is real text"),
        ]
        results_iter = iter(
            [
                _make_mock_result(
                    url,
                    f"<html><body><p>{md}</p></body></html>",
                    md,
                )
                for url, md in pages_data
            ]
        )

        async def mock_arun(url, config=None):
            return next(results_iter)

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/b/page", "https://example.com/a/page"],
            limit=2,
            max_retries=0,
            flush_interval=10,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        # Sorted final files should exist and contain both URLs
        sorted_files = list(crawler.output_dir.glob("final/sorted_success_content_*"))
        assert len(sorted_files) >= 1
        content = sorted_files[0].read_text(encoding="utf-8")
        assert "https://example.com/a/page" in content
        assert "https://example.com/b/page" in content

        # In sorted output, /a/ should come before /b/
        pos_a = content.index("*Source: https://example.com/a/page*")
        pos_b = content.index("*Source: https://example.com/b/page*")
        assert pos_a < pos_b

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_final_files_have_of_total_suffix(self, mock_crawler_cls, tmp_path: Path):
        """Sorted final content files are renamed to include _of_NNN suffix."""
        pages_data = [
            ("https://example.com/a", "Page A"),
            ("https://example.com/b", "Page B"),
        ]
        results_iter = iter(
            [
                _make_mock_result(
                    url,
                    f"<html><body><p>{md}</p></body></html>",
                    md,
                )
                for url, md in pages_data
            ]
        )

        async def mock_arun(url, config=None):
            return next(results_iter)

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=2,
            max_retries=0,
            flush_interval=10,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        sorted_files = sorted(crawler.output_dir.glob("final/sorted_success_content_*"))
        assert len(sorted_files) >= 1
        # Every sorted final file should contain the _of_ suffix
        for f in sorted_files:
            assert "_of_" in f.stem
