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
        assert "https://example.com/doc.pdf" not in links
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
        assert fallback.wait_until == primary.wait_until

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
