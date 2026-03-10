"""Tests for crawl4md.crawler — output files, URL lists, and print_summary."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter
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
        # Per-round fail content file
        fail_files = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
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
        fail_files = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
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
        fail_files = list(crawler.output_dir.glob("*fail_content*"))
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
        fail_files = list(crawler.output_dir.glob("*fail_content*"))
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

        # Create dummy round files
        (tmp_path / "round_1_success_content_001.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / "round_1_success_urls.txt").write_text(
            "https://example.com/a", encoding="utf-8"
        )

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "--- Round 1 ---" in out
        assert "round_1_success_content_001.md" in out

    def test_prints_sorted_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        (tmp_path / "sorted_final_success_content_001.md").write_text("data", encoding="utf-8")
        (tmp_path / "sorted_final_success_urls.txt").write_text("url", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "Sorted by URL path" in out
        assert "sorted_final_success_content_001.md" in out

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

        (tmp_path / "final_success_content_001.md").write_text("data", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "Final (unsorted" in out
        assert "final_success_content_001.md" in out

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
        round1_fail = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
        round2_fail = list(crawler.output_dir.glob("round_2_fail_content_*.txt"))
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
        sorted_urls_path = crawler.output_dir / "sorted_final_success_urls.txt"
        if sorted_urls_path.exists():
            urls = sorted_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), (
                f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"
            )

        # Check final success URLs have no duplicates
        final_urls_path = crawler.output_dir / "final_success_urls.txt"
        if final_urls_path.exists():
            urls = final_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), (
                f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"
            )

        # Check final fail URLs have no duplicates (if any)
        final_fail_path = crawler.output_dir / "final_fail_urls.txt"
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
        crawler._save_url_lists(success, fail, "round_1_")

        assert (tmp_path / "round_1_success_urls.txt").read_text(
            encoding="utf-8"
        ) == "https://example.com/a"
        assert (tmp_path / "round_1_fail_urls.txt").read_text(
            encoding="utf-8"
        ) == "https://example.com/b"

    def test_no_fail_file_when_all_succeed(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        success = [CrawlResult(url="https://example.com/a", success=True)]
        crawler._save_url_lists(success, [], "round_1_")

        assert (tmp_path / "round_1_success_urls.txt").exists()
        assert not (tmp_path / "round_1_fail_urls.txt").exists()


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
        final_files = list(crawler.output_dir.glob("final_success_content_*.txt"))
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
        fail_files = list(crawler.output_dir.glob("final_fail_content*"))
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
        fail_files = list(crawler.output_dir.glob("final_fail_content_*.txt"))
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
        final_files = list(crawler.output_dir.glob("final_success_content_*.txt"))
        assert len(final_files) >= 1
        content = final_files[0].read_text(encoding="utf-8")
        # Both URLs should appear exactly once
        assert content.count(url_a) == 1
        assert content.count(url_b) == 1
