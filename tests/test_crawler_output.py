"""Tests for crawl4md.crawler — output files, URL lists, and print_summary."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md.config import CrawlerConfig, CrawlResult, ExtractedPage, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter, PageSidecar
from tests.conftest import _make_mock_result


class TestFailContentFiles:
    """Tests for fail content file generation (symmetrical with success content)."""

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
        fail_files = list(crawler.output_dir.glob("round_1/fail_content_*.txt"))
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
        fail_files = list(crawler.output_dir.glob("round_1/fail_content_*.txt"))
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
        assert "--- Round 1 ---" in out
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
        round1_fail = list(crawler.output_dir.glob("round_1/fail_content_*.txt"))
        round2_fail = list(crawler.output_dir.glob("round_2/fail_content_*.txt"))
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


class TestFinalUnsortedContentFiles:
    """Tests for unsorted final_success_content / final_fail_content file generation."""

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
        # Both URLs should appear exactly once
        assert content.count(url_a) == 1
        assert content.count(url_b) == 1


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

        round_1_success_urls = (crawler.output_dir / "round_1" / "success_urls.txt").read_text(
            encoding="utf-8"
        )
        assert round_1_success_urls == url_a

        round_2_success_urls = (crawler.output_dir / "round_2" / "success_urls.txt").read_text(
            encoding="utf-8"
        )
        assert round_2_success_urls.splitlines() == [url_a, url_b]

        round_2_files = list(crawler.output_dir.glob("round_2/success_content_*.txt"))
        assert len(round_2_files) >= 1
        round_2_content = round_2_files[0].read_text(encoding="utf-8")
        assert round_2_content.count(url_a) == 1
        assert round_2_content.count(url_b) == 1


class TestSortedRoundFiles:
    """Tests for per-round sorted content and URL file generation."""

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
        sorted_files = list(crawler.output_dir.glob("round_1/sorted_success_content_*.txt"))
        assert len(sorted_files) >= 1
        content = sorted_files[0].read_text(encoding="utf-8")
        assert "https://example.com/page" in content

        sorted_urls = crawler.output_dir / "round_1" / "sorted_success_urls.txt"
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
        sorted_fail_files = list(crawler.output_dir.glob("round_1/sorted_fail_content_*.txt"))
        assert len(sorted_fail_files) >= 1
        content = sorted_fail_files[0].read_text(encoding="utf-8")
        assert "https://example.com/blocked" in content
        assert "Blocked by WAF" in content

        sorted_fail_urls = crawler.output_dir / "round_1" / "sorted_fail_urls.txt"
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

    @patch("crawl4md.crawler._ENABLE_SORTED_ROUND_FILES", False)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sorted_round_files_skipped_when_disabled(self, mock_crawler_cls, tmp_path: Path):
        """No sorted round files when _ENABLE_SORTED_ROUND_FILES is False."""
        html = "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
        mock_result = _make_mock_result("https://example.com/page", html, "Hello")

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
        sorted_r2_urls = crawler.output_dir / "round_2" / "sorted_success_urls.txt"
        assert sorted_r2_urls.exists()
        urls = sorted_r2_urls.read_text(encoding="utf-8").strip().split("\n")
        assert set(urls) == {url_a, url_b}

        # Sorted content should contain both
        sorted_r2_files = list(crawler.output_dir.glob("round_2/sorted_success_content_*.txt"))
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
        assert "Round 1 (sorted)" in out
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

        success_files = sorted(final_dir.glob("success_content_*.md"))
        sorted_success_files = sorted(final_dir.glob("sorted_success_content_*.md"))
        assert [path.name for path in success_files] == ["success_content_001.md"]
        assert [path.name for path in sorted_success_files] == [
            "sorted_success_content_001_of_001.md"
        ]
        assert "stale" not in success_files[0].read_text(encoding="utf-8")
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

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_sidecar_files_created(self, mock_crawler_cls, tmp_path: Path):
        """Crawl creates success and fail JSONL sidecar files."""
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
        success_sidecars = list(crawler.output_dir.glob("round_*/success_pages.jsonl"))
        assert len(success_sidecars) >= 1
        success_pages = list(PageSidecar.read_pages(success_sidecars[0]))
        assert len(success_pages) >= 1
        assert any(p.url == "https://example.com/ok" for p in success_pages)

        # Fail sidecar exists
        fail_sidecars = list(crawler.output_dir.glob("round_*/fail_pages.jsonl"))
        assert len(fail_sidecars) >= 1
        fail_pages = list(PageSidecar.read_pages(fail_sidecars[0]))
        assert len(fail_pages) >= 1
        assert any(p.url == "https://example.com/blocked" for p in fail_pages)

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
        pos_a = content.index("example.com/a/page")
        pos_b = content.index("example.com/b/page")
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
