"""Tests for crawl4md.crawler — core SiteCrawler and WAF detection."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter
from tests.conftest import _make_mock_result


class TestSiteCrawler:
    def test_creates_timestamped_output_dir(self, tmp_path: Path):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        output_dir = crawler._create_output_dir()

        assert output_dir.exists()
        assert output_dir.parent == tmp_path
        # Matches YYYY-MM-DD_HH-MM-SS
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", output_dir.name)

    def test_url_allowed_no_filters(self):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/any") is True

    def test_url_allowed_rejects_external_domain(self):
        config = CrawlerConfig(urls=["https://www.starhub.com/personal/support.html"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://www.starhub.com/personal/page") is True
        assert crawler._url_allowed("https://starhub.com/other") is True
        assert crawler._url_allowed("https://sub.starhub.com/page") is True
        assert crawler._url_allowed("https://otherdomain.com/page") is False

    def test_url_allowed_exclude(self):
        config = CrawlerConfig(urls=["https://example.com"], exclude_paths=[r"/admin"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/admin/settings") is False
        assert crawler._url_allowed("https://example.com/blog") is True

    def test_url_allowed_include_only(self):
        config = CrawlerConfig(urls=["https://example.com"], include_only_paths=[r"/blog"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/blog/post1") is True
        assert crawler._url_allowed("https://example.com/about") is False

    def test_extract_links(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html='<a href="/page1">P1</a> <a href="https://other.com">O</a> <a href="#frag">F</a>',
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://other.com" in links
        # Fragment-only links are resolved to the base URL
        assert all(not link.endswith("#frag") for link in links)

    def test_extract_links_skips_static_assets(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a>'
                '<a href="/style.css">CSS</a>'
                '<a href="/favicon.ico">ICO</a>'
                '<a href="/app.js">JS</a>'
                '<a href="/image.png">PNG</a>'
                '<a href="/font.woff2">WOFF2</a>'
                '<a href="/doc.pdf">PDF</a>'
                '<a href="/DependencyHandler.axd?s=abc&amp;t=Css">AXD</a>'
                '<a href="/Service.asmx">ASMX</a>'
                '<a href="/Handler.ashx?id=1">ASHX</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://example.com/style.css" not in links
        assert "https://example.com/favicon.ico" not in links
        assert "https://example.com/app.js" not in links
        assert "https://example.com/image.png" not in links
        assert "https://example.com/font.woff2" not in links
        # PDF links are now allowed through for PDF crawling support
        assert "https://example.com/doc.pdf" in links
        assert not any("DependencyHandler.axd" in link for link in links)
        assert "https://example.com/Service.asmx" not in links
        assert not any("Handler.ashx" in link for link in links)

    def test_extract_links_skips_template_placeholders(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a>'
                '<a href="https://example.com/${offer_url}">Offer</a>'
                '<a href="https://example.com/${msa_link}">MSA</a>'
                '<a href="https://example.com/{{slug}}">Slug</a>'
                '<a href="https://example.com/{%url%}">Django</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert len(links) == 1  # Only the real link survives

    def test_save_url_list(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=True),
            CrawlResult(url="https://example.com/b", success=True),
        ]
        crawler._save_url_list(results)

        urls_file = tmp_path / "urls.txt"
        assert urls_file.exists()
        lines = urls_file.read_text(encoding="utf-8").splitlines()
        assert lines == ["https://example.com/a", "https://example.com/b"]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_crawl_single_page(self, mock_crawler_cls, tmp_path: Path):
        """Test that crawl() returns results and creates output."""
        mock_result = _make_mock_result("https://example.com", "<p>hi</p>", "hi")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].success is True
        assert crawler.output_dir is not None
        assert (crawler.output_dir / "final_success_urls.txt").exists()

    def test_stealth_enables_browser_and_run_flags(self):
        """Stealth mode sets enable_stealth, simulate_user, override_navigator, magic, scan_full_page."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"], stealth=True)
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.simulate_user is True
        assert run_cfg.override_navigator is True
        assert run_cfg.magic is True
        assert run_cfg.scan_full_page is True
        assert run_cfg.scroll_delay == 0.4

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_random_ua_when_stealth(self, mock_crawler_cls, tmp_path: Path):
        """When stealth=True, BrowserConfig gets random user agent mode."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=_make_mock_result("https://example.com"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, stealth=True)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        browser_cfg = (
            mock_crawler_cls.call_args[1].get("config") or mock_crawler_cls.call_args[0][0]
        )
        assert browser_cfg.user_agent_mode == "random"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_headers_passed_to_browser_config(self, mock_crawler_cls, tmp_path: Path):
        """Custom headers are forwarded to BrowserConfig."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=_make_mock_result("https://example.com"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com"], limit=1, headers={"Accept-Language": "en"}
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        browser_cfg = (
            mock_crawler_cls.call_args[1].get("config") or mock_crawler_cls.call_args[0][0]
        )
        assert browser_cfg.headers.get("Accept-Language") == "en"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_single_crawler_instance_across_rounds(self, mock_crawler_cls, tmp_path: Path):
        """Only one AsyncWebCrawler instance is created even with retries."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        blocked_result = _make_mock_result("https://example.com/a", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=2)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        # AsyncWebCrawler should be instantiated exactly once
        assert mock_crawler_cls.call_count == 1

    def test_js_code_passed_to_run_config(self):
        """js_code from PageConfig is forwarded to CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        page_config = PageConfig(js_code="document.querySelector('.faq').click()")
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.js_code == ["document.querySelector('.faq').click()"]

    def test_timeout_converted_to_milliseconds(self):
        """timeout (seconds) is converted to page_timeout (milliseconds) in CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        page_config = PageConfig(timeout=15)
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.page_timeout == 15000

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_crawl_with_extractor_and_writer(self, mock_crawler_cls, tmp_path: Path):
        """Content files are written incrementally when extractor/writer are provided."""
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_result = _make_mock_result("https://example.com", html, "Hello world")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com"], limit=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            extractor=extractor,
            writer=writer,
        )
        results = crawler.crawl()

        assert len(results) == 1
        assert len(crawler.content_files) >= 1


class TestIsBlocked:
    """Tests for WAF/bot-protection block detection."""

    def test_detects_incapsula(self):
        html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_incapsula_case_insensitive(self):
        html = "<html><body>request unsuccessful. incapsula incident id: 456</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_access_denied(self):
        html = "<html><head><title>Access Denied</title></head><body>blocked</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_ignores_normal_html(self):
        html = "<html><body><p>Normal content</p></body></html>"
        assert SiteCrawler._is_blocked(html) is False

    def test_empty_html_not_blocked(self):
        assert SiteCrawler._is_blocked("") is False

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_real_content_not_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page that contains a WAF signature but also substantial markdown is not flagged."""
        html = (
            "<html><head><title>Plans</title></head>"
            "<body><noscript>Please turn JavaScript on and reload the page</noscript>"
            "<p>" + "Real content. " * 100 + "</p></body></html>"
        )
        long_markdown = "Real content. " * 100
        mock_result = _make_mock_result("https://example.com", html, long_markdown)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is True
        assert results[0].error is None

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_short_content_is_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page that contains a WAF signature and only short markdown is flagged as blocked."""
        html = (
            "<html><head><title>Access Denied</title></head>"
            "<body>Please turn JavaScript on and reload the page</body></html>"
        )
        mock_result = _make_mock_result("https://example.com", html, "Access Denied")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert results[0].error == "Blocked by WAF"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_nav_chrome_still_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page with WAF signature whose raw markdown exceeds 500 chars due to
        nav chrome should still be flagged when the *real* content is empty."""
        # Simulate a JS-required page with navigation boilerplate
        nav_text = " ".join(["Nav link"] * 100)  # >500 chars of nav chrome
        html = (
            "<html><head><title>Product PLP/PDP</title></head><body>"
            f"<nav>{nav_text}</nav>"
            "<main><noscript>JavaScript is required</noscript></main>"
            "</body></html>"
        )
        # Crawl4AI raw markdown includes the nav text
        long_nav_markdown = nav_text + "\nJavaScript is required"
        mock_result = _make_mock_result("https://example.com/product", html, long_nav_markdown)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/product"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert "Blocked" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_real_main_content_not_blocked(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """A page with a WAF signature but substantial <main> content stays successful."""
        real_content = "Galaxy S26 Ultra specs and pricing. " * 30  # >500 chars of real content
        html = (
            "<html><head><title>Galaxy S26 Ultra</title></head><body>"
            "<nav>Menu Home About</nav>"
            "<noscript>JavaScript is required</noscript>"
            f"<main><p>{real_content}</p></main>"
            "</body></html>"
        )
        mock_result = _make_mock_result("https://example.com/product", html, real_content)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/product"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is True
        assert results[0].error is None

    def test_content_length_without_chrome_strips_nav(self):
        """_content_length_without_chrome ignores nav, header, footer, script, style, form."""
        html = (
            "<html><body>"
            "<nav>Menu Home About Contact Support</nav>"
            "<header>Site Header</header>"
            "<main><p>Real content here</p></main>"
            "<footer>Footer links</footer>"
            "</body></html>"
        )
        length = SiteCrawler._content_length_without_chrome(html)
        assert "Real content here" in html
        # Should only count the <main> content, not nav/header/footer
        assert length < 50
        assert length > 0

    def test_content_length_without_chrome_empty_html(self):
        assert SiteCrawler._content_length_without_chrome("") == 0

    def test_fallback_run_config_disables_scan_and_stealth(self):
        """Fallback config omits scan_full_page and stealth run-flags."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"], stealth=True)
        page_config = PageConfig(scan_full_page=True, timeout=20, js_code="alert(1)")
        crawler = SiteCrawler(config, page_config)

        fallback = crawler._build_fallback_run_config(CrawlerRunConfig)
        assert fallback.scan_full_page is False
        assert fallback.magic is False
        assert fallback.simulate_user is False
        assert fallback.override_navigator is False
        # Non-stealth settings are preserved
        assert fallback.page_timeout == 20000
        assert fallback.js_code == ["alert(1)"]

    def test_fallback_run_config_uses_domcontentloaded(self):
        """Fallback config downgrades wait_until to domcontentloaded."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(wait_until="networkidle")
        crawler = SiteCrawler(config, page_config)

        fallback = crawler._build_fallback_run_config(CrawlerRunConfig)
        assert fallback.wait_until == "domcontentloaded"

    def test_run_config_passes_wait_until(self):
        """wait_until is forwarded to CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(wait_until="networkidle")
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.wait_until == "networkidle"

    def test_run_config_default_wait_until(self):
        """Default wait_until is networkidle."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.wait_until == "networkidle"

    def test_fallback_preserves_same_base_settings_as_primary(self):
        """Fallback config carries the same excluded_tags, timeout, js_code, wait_for, wait_until."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(
            exclude_tags="nav, form",
            wait_until="networkidle",
            wait_for=5,
            timeout=30,
            js_code="window.scrollTo(0,0)",
        )
        crawler = SiteCrawler(config, page_config)

        primary = crawler._build_run_config(CrawlerRunConfig)
        fallback = crawler._build_fallback_run_config(CrawlerRunConfig)

        assert fallback.excluded_tags == primary.excluded_tags
        assert fallback.page_timeout == primary.page_timeout
        assert fallback.js_code == primary.js_code
        assert fallback.delay_before_return_html == primary.delay_before_return_html
        assert fallback.wait_until == "domcontentloaded"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_rounds_use_fallback_run_config(self, mock_crawler_cls, tmp_path: Path):
        """Retry rounds pass the fallback (reduced) run config, not the primary."""
        # Round 1: page fails; Retry round 2: page succeeds
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = ""
        fail_result.markdown = ""
        fail_result.html = ""

        ok_result = _make_mock_result("https://example.com")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[fail_result, ok_result])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=1)
        page_config = PageConfig(scan_full_page=True)
        crawler = SiteCrawler(config, page_config, output_base=tmp_path)
        crawler.crawl()

        # arun called twice: once in round 1, once in retry
        assert mock_instance.arun.call_count == 2

        # Round 1 config should have scan_full_page=True
        round1_cfg = mock_instance.arun.call_args_list[0][1].get("config")
        assert round1_cfg.scan_full_page is True

        # Retry config should have scan_full_page=False (fallback)
        retry_cfg = mock_instance.arun.call_args_list[1][1].get("config")
        assert retry_cfg.scan_full_page is False
        assert retry_cfg.magic is False
        assert retry_cfg.wait_until == "domcontentloaded"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_error_includes_status_code(self, mock_crawler_cls, tmp_path: Path):
        """When a page fails, the error message includes the HTTP status code."""
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = ""
        fail_result.status_code = 403
        fail_result.markdown = ""
        fail_result.html = ""

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=fail_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert "HTTP 403" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_error_includes_exception_type(self, mock_crawler_cls, tmp_path: Path):
        """When arun raises, the error includes the exception class name."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=RuntimeError("Execution context was destroyed"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert "RuntimeError" in (results[0].error or "")
        assert "Execution context was destroyed" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_failed_result_with_empty_error_shows_unknown(self, mock_crawler_cls, tmp_path: Path):
        """A failed result with no error attribute shows 'Unknown error'."""
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = None
        fail_result.error_message = None
        fail_result.status_code = 0
        fail_result.markdown = ""
        fail_result.html = ""

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=fail_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert "Unknown error" in (results[0].error or "")
        assert "HTTP 0" in (results[0].error or "")


class TestNormalizeUrl:
    """Tests for _normalize_url — URL normalization to reduce duplicate crawling."""

    def test_http_to_https(self):
        assert SiteCrawler._normalize_url("http://example.com/page") == "https://example.com/page"

    def test_strips_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page") == "https://example.com/page"
        )

    def test_http_and_www_combined(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page") == "https://example.com/page"
        )

    def test_lowercases_host(self):
        assert SiteCrawler._normalize_url("https://Example.COM/Page") == "https://example.com/Page"

    def test_preserves_path_and_query(self):
        url = "https://example.com/a/b?q=1&r=2"
        assert SiteCrawler._normalize_url(url) == url

    def test_strips_fragment(self):
        assert (
            SiteCrawler._normalize_url("https://example.com/page#section")
            == "https://example.com/page"
        )

    def test_idempotent(self):
        url = "https://example.com/page"
        assert SiteCrawler._normalize_url(SiteCrawler._normalize_url(url)) == url

    # -- strip_www=True (explicit) --

    def test_strip_www_true_removes_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page", strip_www=True)
            == "https://example.com/page"
        )

    def test_strip_www_true_http_and_www(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page", strip_www=True)
            == "https://example.com/page"
        )

    # -- strip_www=False --

    def test_strip_www_false_preserves_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page", strip_www=False)
            == "https://www.example.com/page"
        )

    def test_strip_www_false_http_and_www(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page", strip_www=False)
            == "https://www.example.com/page"
        )

    def test_strip_www_false_no_www_unchanged(self):
        assert (
            SiteCrawler._normalize_url("https://example.com/page", strip_www=False)
            == "https://example.com/page"
        )


class TestExtractBaseDomains:
    """Tests for _extract_base_domains with strip_www flag."""

    def test_strip_www_true_removes_www(self):
        domains = SiteCrawler._extract_base_domains(
            ["https://www.example.com/page"], strip_www=True
        )
        assert domains == {"example.com"}

    def test_strip_www_false_preserves_www(self):
        domains = SiteCrawler._extract_base_domains(
            ["https://www.example.com/page"], strip_www=False
        )
        assert domains == {"www.example.com"}

    def test_strip_www_true_no_www_unchanged(self):
        domains = SiteCrawler._extract_base_domains(["https://example.com/page"], strip_www=True)
        assert domains == {"example.com"}


class TestExtractLinksNormalization:
    """Tests that _extract_links normalizes discovered URLs."""

    def test_extract_links_normalizes_http_and_www(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        # Both should normalize to the same URL
        assert links.count("https://example.com/page1") == 1

    def test_extract_links_strip_www_true_deduplicates(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com", strip_www=True)
        assert links == ["https://example.com/page1"]

    def test_extract_links_strip_www_false_keeps_both(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com", strip_www=False)
        assert len(links) == 2
        assert "https://www.example.com/page1" in links
        assert "https://example.com/page1" in links


class TestRedirectDedup:
    """Tests that redirect dedup is logged and does not silently discard."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_to_visited_is_logged(self, mock_crawler_cls, tmp_path: Path):
        """When a redirect targets an already-visited URL, it should be logged."""
        # Page A succeeds normally, Page B redirects to A's normalized URL
        result_a = _make_mock_result("https://example.com/a", "<p>content A</p>", "content A")
        result_a.redirected_url = None

        result_b = _make_mock_result("http://www.example.com/b", "<p>content B</p>", "content B")
        result_b.redirected_url = "https://example.com/a"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a", "http://www.example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Only page A should be in results — page B's redirect target was already visited
        assert len(results) == 1
        assert results[0].url == "https://example.com/a"

        # Activity log should contain a "Skipped" entry for the redirect
        log_txt = crawler.output_dir / "activity_log.txt"
        if log_txt.exists():
            log_content = log_txt.read_text(encoding="utf-8")
            assert "Skipped" in log_content or "skip" in log_content.lower()


class TestRedirectStorm:
    """Tests for anti-bot redirect storm detection."""

    @staticmethod
    def _make_redirect_side_effects(
        target: str,
        source_urls: list[str],
    ) -> list:
        """Create mock arun results where every source redirects to *target*."""
        effects = []
        for src in source_urls:
            r = _make_mock_result(src, "<p>redirect page</p>", "redirect page")
            r.redirected_url = target
            effects.append(r)
        return effects

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_below_threshold_flushed_as_unresolved(self, mock_crawler_cls, tmp_path: Path):
        """Below-threshold redirects appear as unresolved failures at end-of-loop."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # First page succeeds (populates visited with target)
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        # Two more pages redirect to /home (below threshold of 3)
        redirects = self._make_redirect_side_effects(
            target, ["https://example.com/a", "https://example.com/b"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, "https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert successes[0].url == target
        # The two redirects are flushed as unresolved failures at end-of-loop
        assert len(failures) == 2
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {
            "https://example.com/a",
            "https://example.com/b",
        }

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_at_threshold_becomes_failure(self, mock_crawler_cls, tmp_path: Path):
        """After reaching the threshold, all redirect pages become failures.

        p0 and p1 are retroactively converted when p2 triggers the storm;
        p2 and p3 are direct storm failures.
        """
        from crawl4md.crawler import _REDIRECT_STORM_ERROR

        target = "https://example.com/home"
        sources = [f"https://example.com/p{i}" for i in range(4)]

        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redirects = self._make_redirect_side_effects(target, sources)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, *sources],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert successes[0].url == target
        # All 4 redirects become failures (p0/p1 retroactive, p2/p3 direct)
        assert len(failures) == 4
        assert all(r.error == _REDIRECT_STORM_ERROR for r in failures)
        # Failures carry the original URL, not the redirect target
        failure_urls = {r.url for r in failures}
        assert failure_urls == {f"https://example.com/p{i}" for i in range(4)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_counter_resets_on_successful_crawl(self, mock_crawler_cls, tmp_path: Path):
        """A non-redirect result resets the counter and flushes skipped URLs."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # Sequence: home, redirect×2, normal_page, redirect×2
        # The normal page resets the counter; both batches of 2 are
        # flushed as unresolved failures (batch 1 on reset, batch 2
        # at end-of-loop).
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redir_a = self._make_redirect_side_effects(
            target, ["https://example.com/r1", "https://example.com/r2"]
        )
        result_normal = _make_mock_result("https://example.com/good", "<p>good</p>", "good")
        redir_b = self._make_redirect_side_effects(
            target, ["https://example.com/r3", "https://example.com/r4"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redir_a, result_normal, *redir_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target,
                "https://example.com/r1",
                "https://example.com/r2",
                "https://example.com/good",
                "https://example.com/r3",
                "https://example.com/r4",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert {r.url for r in successes} == {target, "https://example.com/good"}
        # All 4 redirects flushed as unresolved failures
        assert len(failures) == 4
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {f"https://example.com/r{i}" for i in range(1, 5)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_different_targets_flush_on_switch(self, mock_crawler_cls, tmp_path: Path):
        """Redirects to different targets flush prior batch as unresolved."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target_a = "https://example.com/home-a"
        target_b = "https://example.com/home-b"

        result_a = _make_mock_result(target_a, "<p>a</p>", "a")
        result_b = _make_mock_result(target_b, "<p>b</p>", "b")
        # 2 redirects to target_a, then 2 to target_b — neither reaches 3
        redir_a = self._make_redirect_side_effects(
            target_a, ["https://example.com/r1", "https://example.com/r2"]
        )
        redir_b = self._make_redirect_side_effects(
            target_b, ["https://example.com/r3", "https://example.com/r4"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b, *redir_a, *redir_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target_a,
                target_b,
                "https://example.com/r1",
                "https://example.com/r2",
                "https://example.com/r3",
                "https://example.com/r4",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert {r.url for r in successes} == {target_a, target_b}
        # r1/r2 flushed on target switch; r3/r4 flushed at end-of-loop
        assert len(failures) == 4
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {f"https://example.com/r{i}" for i in range(1, 5)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_storm_retroactive_vs_direct_order(self, mock_crawler_cls, tmp_path: Path):
        """Retroactive failures appear before the storm-triggered failure in results."""
        from crawl4md.crawler import _REDIRECT_STORM_ERROR

        target = "https://example.com/home"
        # 3 redirects: p0 and p1 are below threshold, p2 triggers storm
        sources = [f"https://example.com/p{i}" for i in range(3)]
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redirects = self._make_redirect_side_effects(target, sources)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, *sources],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        failures = [r for r in results if not r.success]
        assert len(failures) == 3
        # Retroactive failures (p0, p1) appear before the direct one (p2)
        assert failures[0].url == "https://example.com/p0"
        assert failures[1].url == "https://example.com/p1"
        assert failures[2].url == "https://example.com/p2"
        assert all(r.error == _REDIRECT_STORM_ERROR for r in failures)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_mixed_storm_and_unresolved(self, mock_crawler_cls, tmp_path: Path):
        """Storm batch uses STORM error; post-reset batch uses UNRESOLVED error."""
        from crawl4md.crawler import _REDIRECT_STORM_ERROR, _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # Sequence: home, redirect×3 (storm), normal, redirect×2 (unresolved)
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        storm_batch = self._make_redirect_side_effects(
            target, [f"https://example.com/s{i}" for i in range(3)]
        )
        result_normal = _make_mock_result("https://example.com/good", "<p>good</p>", "good")
        tail_batch = self._make_redirect_side_effects(
            target, ["https://example.com/t0", "https://example.com/t1"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[result_home, *storm_batch, result_normal, *tail_batch]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target,
                "https://example.com/s0",
                "https://example.com/s1",
                "https://example.com/s2",
                "https://example.com/good",
                "https://example.com/t0",
                "https://example.com/t1",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2

        storm_failures = [r for r in failures if r.error == _REDIRECT_STORM_ERROR]
        unresolved_failures = [r for r in failures if r.error == _UNRESOLVED_REDIRECT_ERROR]
        # s0, s1, s2 are storm failures (retroactive + direct)
        assert {r.url for r in storm_failures} == {f"https://example.com/s{i}" for i in range(3)}
        # t0, t1 are unresolved (flushed at end-of-loop)
        assert {r.url for r in unresolved_failures} == {
            "https://example.com/t0",
            "https://example.com/t1",
        }


class TestEmptyExtraction:
    """Tests that empty extraction is treated as failure."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_empty_extraction_demoted_to_failure(self, mock_crawler_cls, tmp_path: Path):
        """When extraction produces empty markdown, the page becomes a failure."""
        # HTML that crawl4ai reports as success, but extraction produces nothing
        html = "<html><head></head><body></body></html>"
        mock_result = _make_mock_result("https://example.com/empty", html, "")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/empty"], limit=1, max_retries=0)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].success is False
        assert "No extractable content" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_empty_extraction_appears_in_fail_urls(self, mock_crawler_cls, tmp_path: Path):
        """Empty extraction pages should appear in fail_urls.txt."""
        html = "<html><head></head><body></body></html>"
        mock_result = _make_mock_result("https://example.com/empty", html, "")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/empty"], limit=1, max_retries=0)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        fail_urls = crawler.output_dir / "final_fail_urls.txt"
        assert fail_urls.exists()
        content = fail_urls.read_text(encoding="utf-8")
        assert "https://example.com/empty" in content
