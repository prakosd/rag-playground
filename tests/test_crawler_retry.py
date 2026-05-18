"""Tests for crawl4md.crawler — multi-round retry logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from tests.conftest import _make_mock_result


class TestRetryRounds:
    """Tests for the multi-round crawl with retries."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retries_blocked_pages(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages in round 1 are retried in round 2."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        ok_result = _make_mock_result("https://example.com/ok", "<p>good</p>", "good")
        blocked_result = _make_mock_result("https://example.com/blocked", blocked_html, "blocked")
        # Round 2: the previously-blocked page now succeeds
        retry_ok_result = _make_mock_result(
            "https://example.com/blocked", "<p>now ok</p>", "now ok"
        )

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if url == "https://example.com/ok":
                return ok_result
            # First call for /blocked returns block, second returns ok
            if url == "https://example.com/blocked":
                if call_count["n"] <= 2:
                    return blocked_result
                return retry_ok_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok", "https://example.com/blocked"],
            limit=10,
            max_retries=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert crawler.output_dir is not None
        # Round 1 files
        assert (crawler.output_dir / "round_1" / "success_urls.txt").exists()
        assert (crawler.output_dir / "round_1" / "fail_urls.txt").exists()
        # Round 2 files
        assert (crawler.output_dir / "round_2" / "success_urls.txt").exists()
        # Final files
        assert (crawler.output_dir / "final" / "success_urls.txt").exists()
        # All pages should succeed after retry
        success = [r for r in results if r.success]
        assert len(success) == 2

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_skips_retries_when_all_succeed(self, mock_crawler_cls, tmp_path: Path):
        """No retry rounds when everything succeeds in round 1."""
        ok_result = _make_mock_result("https://example.com/a", "<p>ok</p>", "ok")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a"],
            limit=10,
            max_retries=2,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        assert crawler.output_dir is not None
        # Round 1 exists
        assert (crawler.output_dir / "round_1" / "success_urls.txt").exists()
        # Round 2 should NOT exist (early exit)
        assert not (crawler.output_dir / "round_2" / "success_urls.txt").exists()
        assert not (crawler.output_dir / "round_2" / "fail_urls.txt").exists()
        # Final success
        assert (crawler.output_dir / "final" / "success_urls.txt").exists()
        assert not (crawler.output_dir / "final" / "fail_urls.txt").exists()

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_updates_result_url(self, mock_crawler_cls, tmp_path: Path):
        """CrawlResult.url should be the final URL after a redirect."""
        mock_result = _make_mock_result(
            "https://example.com/old",
            redirected_url="https://example.com/new",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/old"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com/new"
        assert results[0].redirected_url == "https://example.com/new"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_deduplicates_when_both_urls_are_seeds(self, mock_crawler_cls, tmp_path: Path):
        """Seeding both the original and redirect target should produce one result."""
        original = "https://example.com/old"
        target = "https://example.com/new"

        mock_result_redirect = _make_mock_result(original, redirected_url=target)
        mock_result_direct = _make_mock_result(target)

        mock_instance = AsyncMock()
        # First call: /old redirects to /new. Second call: /new (direct).
        mock_instance.arun = AsyncMock(side_effect=[mock_result_redirect, mock_result_direct])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[original, target], limit=10, max_concurrent=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Only one result — the second seed is skipped because /new is already visited
        assert len(results) == 1
        assert results[0].url == target
        # arun should be called only once (the second URL is skipped before crawling)
        assert mock_instance.arun.call_count == 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_deduplicates_when_both_seed_urls_prefetched(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """Concurrent seeds may both start, but redirect targets still collapse to one result."""
        original = "https://example.com/old"
        target = "https://example.com/new"

        mock_result_redirect = _make_mock_result(original, redirected_url=target)
        mock_result_direct = _make_mock_result(target)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[mock_result_redirect, mock_result_direct])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[original, target], limit=10, max_concurrent=2)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == target
        assert mock_instance.arun.call_count == 2

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_deduplicates_reverse_order(self, mock_crawler_cls, tmp_path: Path):
        """If the target is crawled first, the redirecting URL is still deduplicated."""
        original = "https://example.com/old"
        target = "https://example.com/new"

        mock_result_direct = _make_mock_result(target)
        mock_result_redirect = _make_mock_result(original, redirected_url=target)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[mock_result_direct, mock_result_redirect])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[target, original], limit=10)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Two arun calls happen (we can't know /old redirects until we crawl it),
        # but only one result is kept since /new is already visited
        assert len(results) == 1
        assert results[0].url == target

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_links_resolved_against_final_url(self, mock_crawler_cls, tmp_path: Path):
        """Links discovered on a redirected page should resolve against the final URL."""
        html = '<a href="sibling">Link</a>'
        mock_result = _make_mock_result(
            "https://example.com/old",
            html=html,
            redirected_url="https://example.com/section/new",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/old"], limit=1, max_depth=2)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        # The relative link "sibling" should resolve against /section/new
        urls_file = (crawler.output_dir / "final" / "success_urls.txt").read_text(encoding="utf-8")
        assert "https://example.com/section/new" in urls_file

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_to_disallowed_path_is_skipped(self, mock_crawler_cls, tmp_path: Path):
        """A redirect landing outside include_only_paths should be skipped."""
        mock_result = _make_mock_result(
            "https://example.com/blog/post",
            redirected_url="https://example.com/enterprise/page",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/blog/post"],
            include_only_paths=["/blog"],
            limit=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # The redirect target is outside /blog, so it should be skipped
        assert len(results) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_round1_no_delay_when_delay_is_zero(self, mock_crawler_cls, tmp_path: Path):
        """Round 1 does not apply per-page delay when delay=0 (default)."""
        ok_result = _make_mock_result("https://example.com", "<p>ok</p>", "ok")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com"],
            limit=1,
            delay=0,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            crawler.crawl()

        # asyncio.sleep should not have been called with a jitter value
        # (only the _ROUND_COOLDOWN sleep may appear, which is patched to 0)
        for call in mock_sleep.call_args_list:
            args = call[0]
            assert args[0] == 0 or args == (), (
                f"Unexpected sleep({args[0]}) in round 1 — delay should be skipped"
            )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_round1_applies_light_jitter(self, mock_crawler_cls, tmp_path: Path):
        """Round 1 applies a lighter jitter range when delay > 0."""
        ok_result = _make_mock_result("https://example.com", "<p>ok</p>", "ok")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        delay_value = 5.0
        config = CrawlerConfig(
            urls=["https://example.com"],
            limit=1,
            delay=delay_value,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            crawler.crawl()

        # At least one sleep should be in the round 1 jitter range
        jitter_calls = [
            call[0][0] for call in mock_sleep.call_args_list if call[0] and call[0][0] > 0
        ]
        assert any(delay_value * 0.1 <= v <= delay_value * 1.0 for v in jitter_calls), (
            f"Expected a jitter sleep in [{delay_value * 0.1}, {delay_value * 1.0}], got {jitter_calls}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_round_applies_delay(self, mock_crawler_cls, tmp_path: Path):
        """Retry rounds apply per-page delay with jitter."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        ok_result = _make_mock_result("https://example.com", "<p>good</p>", "good")
        blocked_result = _make_mock_result("https://example.com", blocked_html, "blocked")

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return blocked_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        delay_value = 2.0
        config = CrawlerConfig(
            urls=["https://example.com"],
            limit=1,
            delay=delay_value,
            max_retries=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            crawler.crawl()

        # At least one sleep call should be in the jitter range for the retry round
        jitter_calls = [
            call[0][0] for call in mock_sleep.call_args_list if call[0] and call[0][0] > 0
        ]
        assert any(delay_value * 0.3 <= v <= delay_value * 3.0 for v in jitter_calls), (
            f"Expected a jitter sleep in [{delay_value * 0.3}, {delay_value * 3.0}], got {jitter_calls}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_backoff_fires_on_block(self, mock_crawler_cls, tmp_path: Path):
        """WAF back-off sleep fires after a block is detected, even when delay=0."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        blocked_result = _make_mock_result("https://example.com", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com"],
            limit=1,
            delay=0,  # WAF back-off should still fire
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            crawler.crawl()

        # The WAF back-off floor (3.0s) should appear even with delay=0
        backoff_calls = [
            call[0][0] for call in mock_sleep.call_args_list if call[0] and call[0][0] >= 3.0
        ]
        assert len(backoff_calls) >= 1, (
            f"Expected WAF back-off sleep >= 3.0s, got calls: "
            f"{[c[0][0] for c in mock_sleep.call_args_list if c[0]]}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_backoff_escalates_on_consecutive_blocks(self, mock_crawler_cls, tmp_path: Path):
        """After 3+ consecutive WAF blocks, back-off escalates to the cap (15s)."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        # Create multiple URLs that all get blocked
        urls = [f"https://example.com/page{i}" for i in range(5)]

        async def mock_arun(url, config):
            return _make_mock_result(url, blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=urls,
            limit=5,
            delay=0,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            crawler.crawl()

        # After 3 consecutive blocks, back-off should escalate to 15s cap
        backoff_calls = [
            call[0][0] for call in mock_sleep.call_args_list if call[0] and call[0][0] > 0
        ]
        assert any(v == 15.0 for v in backoff_calls), (
            f"Expected escalated back-off of 15.0s after consecutive blocks, got {backoff_calls}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_round_cooldown_has_jitter(self, mock_crawler_cls, tmp_path: Path):
        """Round cooldown sleep uses jittered value (not exactly _ROUND_COOLDOWN)."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        ok_result = _make_mock_result("https://example.com", "<p>good</p>", "good")
        blocked_result = _make_mock_result("https://example.com", blocked_html, "blocked")

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return blocked_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com"],
            limit=1,
            max_retries=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        # Use a real _ROUND_COOLDOWN value (not the 0 from conftest) to test jitter
        with (
            patch("crawl4md.crawler._ROUND_COOLDOWN", 30),
            patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            crawler.crawl()

        # The cooldown should be in [30*0.8, 30*1.5] = [24, 45]
        cooldown_calls = [
            call[0][0] for call in mock_sleep.call_args_list if call[0] and call[0][0] >= 20
        ]
        assert len(cooldown_calls) >= 1, "Expected at least one round cooldown sleep"
        for v in cooldown_calls:
            assert 24.0 <= v <= 45.0, f"Round cooldown {v} outside jitter range [24, 45]"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_discovers_links_from_recovered_page(self, mock_crawler_cls, tmp_path: Path):
        """A page that fails in R1 and succeeds in R2 should have its links discovered."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        # /start fails in R1, succeeds in R2 with a link to /linked
        start_html_ok = (
            '<html><body><p>Real content here</p><a href="/linked">Link</a></body></html>'
        )
        linked_html = "<html><body><p>Linked page content</p></body></html>"

        blocked_result = _make_mock_result("https://example.com/start", blocked_html, "blocked")
        start_ok_result = _make_mock_result(
            "https://example.com/start", start_html_ok, "Real content here"
        )
        linked_result = _make_mock_result(
            "https://example.com/linked", linked_html, "Linked page content"
        )

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if url == "https://example.com/start":
                # First call blocked, subsequent calls succeed
                if call_count["n"] <= 1:
                    return blocked_result
                return start_ok_result
            if url == "https://example.com/linked":
                return linked_result
            return _make_mock_result(url)

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/start"],
            limit=10,
            max_retries=1,
            max_depth=2,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        result_urls = {r.url for r in results if r.success}
        assert "https://example.com/start" in result_urls
        assert "https://example.com/linked" in result_urls

        urls_file = (crawler.output_dir / "final" / "success_urls.txt").read_text(encoding="utf-8")
        assert "https://example.com/start" in urls_file
        assert "https://example.com/linked" in urls_file

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_discovery_respects_max_depth(self, mock_crawler_cls, tmp_path: Path):
        """Links discovered on retry are still subject to max_depth."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        # Seed at depth 1 with max_depth=1 means depth < max_depth is False → no discovery
        start_html_ok = '<html><body><p>Content</p><a href="/child">Link</a></body></html>'

        blocked_result = _make_mock_result("https://example.com/start", blocked_html, "blocked")
        start_ok_result = _make_mock_result("https://example.com/start", start_html_ok, "Content")

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if url == "https://example.com/start":
                if call_count["n"] <= 1:
                    return blocked_result
                return start_ok_result
            return _make_mock_result(url)

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/start"],
            limit=10,
            max_retries=1,
            max_depth=1,  # depth 1 = seeds only, no deeper
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        result_urls = {r.url for r in results}
        assert "https://example.com/start" in result_urls
        # /child should NOT be crawled — max_depth=1 prevents discovery
        assert "https://example.com/child" not in result_urls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_discovery_respects_limit(self, mock_crawler_cls, tmp_path: Path):
        """Retry discovery may overshoot once, then stops further discovery."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        start_html_ok = (
            "<html><body><p>Content</p>"
            '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
            "</body></html>"
        )

        blocked_result = _make_mock_result("https://example.com/start", blocked_html, "blocked")
        start_ok_result = _make_mock_result("https://example.com/start", start_html_ok, "Content")

        call_count = {"n": 0}

        async def mock_arun(url, config):
            call_count["n"] += 1
            if url == "https://example.com/start":
                if call_count["n"] <= 1:
                    return blocked_result
                return start_ok_result
            return _make_mock_result(url, "<p>page</p>", "page")

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/start"],
            limit=2,  # only 2 total pages allowed
            max_retries=1,
            max_depth=2,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Retry starts below limit, so one discovery burst can overshoot.
        # All already discovered pages are still processed.
        assert len(results) == 4

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_non_crawlable_links_do_not_consume_limit(self, mock_crawler_cls, tmp_path: Path):
        """Non-crawlable URLs (wrong domain, etc.) must not count toward limit."""
        # Seed discovers 3 same-domain + 5 other-domain links.
        # With limit=4, all 3 same-domain links should be crawled (seed + 3).
        seed_html = (
            "<html><body><p>Seed</p>"
            '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
            '<a href="https://other.com/1">O1</a>'
            '<a href="https://other.com/2">O2</a>'
            '<a href="https://other.com/3">O3</a>'
            '<a href="https://other.com/4">O4</a>'
            '<a href="https://other.com/5">O5</a>'
            "</body></html>"
        )

        async def mock_arun(url, config):
            if url == "https://example.com/start":
                return _make_mock_result(url, seed_html, "Seed")
            return _make_mock_result(url, "<p>page</p>", "page")

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/start"],
            limit=4,
            max_depth=2,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        succeeded = [r for r in results if r.success]
        crawled_urls = {r.url for r in results}
        # All 4 slots used: seed + /a + /b + /c
        assert len(succeeded) == 4
        assert "https://example.com/a" in crawled_urls
        assert "https://example.com/b" in crawled_urls
        assert "https://example.com/c" in crawled_urls
        # Other-domain links must not appear
        assert not any("other.com" in u for u in crawled_urls)


class TestRetryWaitUntilDowngrade:
    """Retry rounds should downgrade wait_until to domcontentloaded."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fallback_uses_domcontentloaded(self, mock_crawler_cls, tmp_path: Path):
        """Round 1 uses networkidle; retry rounds downgrade to domcontentloaded."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        ok_result = _make_mock_result("https://example.com/a", "<p>ok</p>", "ok")
        blocked_result = _make_mock_result("https://example.com/a", blocked_html, "blocked")

        configs_seen: list[object] = []
        call_count = {"n": 0}

        async def mock_arun(url, config):
            configs_seen.append(config)
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return blocked_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/a"], limit=10, max_retries=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        assert len(configs_seen) >= 2
        # Round 1 uses the default (networkidle)
        assert configs_seen[0].wait_until == "networkidle"
        # Retry round uses the fallback (domcontentloaded)
        assert configs_seen[1].wait_until == "domcontentloaded"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_user_override_respected_round1_overridden_retry(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """User's custom wait_until is used in round 1 but overridden on retry."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        ok_result = _make_mock_result("https://example.com/b", "<p>ok</p>", "ok")
        blocked_result = _make_mock_result("https://example.com/b", blocked_html, "blocked")

        configs_seen: list[object] = []
        call_count = {"n": 0}

        async def mock_arun(url, config):
            configs_seen.append(config)
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return blocked_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/b"], limit=10, max_retries=1)
        page_config = PageConfig(wait_until="load")
        crawler = SiteCrawler(config, page_config, output_base=tmp_path)
        crawler.crawl()

        assert len(configs_seen) >= 2
        # Round 1 respects the user's override
        assert configs_seen[0].wait_until == "load"
        # Retry round still uses the fallback
        assert configs_seen[1].wait_until == "domcontentloaded"
