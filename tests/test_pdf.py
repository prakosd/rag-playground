"""Tests for PDF crawling and extraction support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor

# ------------------------------------------------------------------
# CrawlResult.is_pdf field
# ------------------------------------------------------------------


class TestCrawlResultIsPdf:
    def test_is_pdf_default_false(self):
        r = CrawlResult(url="https://example.com")
        assert r.is_pdf is False

    def test_is_pdf_explicit_true(self):
        r = CrawlResult(url="https://example.com/doc.pdf", is_pdf=True)
        assert r.is_pdf is True

    def test_is_pdf_explicit_false(self):
        r = CrawlResult(url="https://example.com/doc.pdf", is_pdf=False)
        assert r.is_pdf is False


# ------------------------------------------------------------------
# SiteCrawler._is_pdf_url
# ------------------------------------------------------------------


class TestIsPdfUrl:
    def test_plain_pdf_url(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf") is True

    def test_pdf_with_query_params(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf?token=abc") is True

    def test_pdf_with_fragment(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf#page=3") is True

    def test_case_insensitive(self):
        assert SiteCrawler._is_pdf_url("https://example.com/DOC.PDF") is True
        assert SiteCrawler._is_pdf_url("https://example.com/doc.Pdf") is True

    def test_non_pdf_url(self):
        assert SiteCrawler._is_pdf_url("https://example.com/page.html") is False

    def test_no_extension(self):
        assert SiteCrawler._is_pdf_url("https://example.com/download") is False

    def test_pdf_in_path_but_not_extension(self):
        assert SiteCrawler._is_pdf_url("https://example.com/pdf/report") is False

    def test_deep_path_pdf(self):
        url = "https://phl.hasil.gov.my/pdf/pdfam/Lampiran_A_Panduan.pdf"
        assert SiteCrawler._is_pdf_url(url) is True


# ------------------------------------------------------------------
# SiteCrawler._is_pdf_response
# ------------------------------------------------------------------


class TestIsPdfResponse:
    @pytest.mark.asyncio
    async def test_pdf_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/download?id=1")
        assert result is True

    @pytest.mark.asyncio
    async def test_html_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/page")
        assert result is False

    @pytest.mark.asyncio
    async def test_pdf_content_type_with_params(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf; charset=binary"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/report")
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_error_returns_false(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/report")
        assert result is False

    @pytest.mark.asyncio
    async def test_forwards_headers(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await SiteCrawler._is_pdf_response(
                "https://example.com/report", {"Authorization": "Bearer x"}
            )
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["headers"] == {"Authorization": "Bearer x"}


# ------------------------------------------------------------------
# SiteCrawler._download_pdf
# ------------------------------------------------------------------


class TestDownloadPdf:
    @pytest.mark.asyncio
    async def test_successful_download(self):
        config = MagicMock()
        config.headers = {"User-Agent": "test"}

        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.config = config

        mock_response = MagicMock()
        mock_response.content = b"fake-pdf-bytes"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_doc = MagicMock()

        with (
            patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client),
            patch("crawl4md.crawler.pymupdf.open", return_value=mock_doc) as mock_open,
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# PDF Title\n\nContent"
            ),
        ):
            result = await crawler._download_pdf("https://example.com/doc.pdf")

        assert result.success is True
        assert result.is_pdf is True
        assert result.markdown == "# PDF Title\n\nContent"
        assert result.url == "https://example.com/doc.pdf"
        mock_open.assert_called_once_with(stream=b"fake-pdf-bytes", filetype="pdf")
        mock_doc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_failure(self):
        import httpx

        config = MagicMock()
        config.headers = {}

        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.config = config

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await crawler._download_pdf("https://example.com/missing.pdf")

        assert result.success is False
        assert result.is_pdf is True
        assert "PDF download failed" in result.error


# ------------------------------------------------------------------
# Link discovery: .pdf no longer filtered
# ------------------------------------------------------------------


class TestPdfLinkDiscovery:
    def test_extract_links_includes_pdf(self):
        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a><a href="/doc.pdf">PDF</a><a href="/report.PDF">PDF2</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://example.com/doc.pdf" in links
        assert "https://example.com/report.PDF" in links


# ------------------------------------------------------------------
# ContentExtractor._extract_pdf_page
# ------------------------------------------------------------------


class TestExtractPdfPage:
    def test_basic_extraction(self):
        result = CrawlResult(
            url="https://example.com/reports/annual_report.pdf",
            markdown="# Annual Report\n\nRevenue increased by 15%.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)

        assert page.url == result.url
        assert "annual report" in page.title.lower()
        assert "Revenue increased" in page.markdown

    def test_title_from_url_with_hyphens(self):
        result = CrawlResult(
            url="https://example.com/my-great-report.pdf",
            markdown="Content here.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "my great report"

    def test_title_from_url_with_underscores(self):
        result = CrawlResult(
            url="https://example.com/pdf/Lampiran_A_Panduan.pdf",
            markdown="Content here.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "Lampiran A Panduan"

    def test_title_url_encoded(self):
        result = CrawlResult(
            url="https://example.com/my%20report.pdf",
            markdown="Content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "my report"

    def test_title_fallback_to_url(self):
        result = CrawlResult(
            url="https://example.com/.pdf",
            markdown="Content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        # After stripping .pdf and separators, name is empty → falls back to URL
        assert page.title == result.url

    def test_routing_via_extract_page(self):
        result = CrawlResult(
            url="https://example.com/doc.pdf",
            markdown="# PDF Content\n\nSome text.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_page(result)
        assert "PDF Content" in page.markdown
        assert page.url == result.url

    def test_skips_html_preprocessing(self):
        """Ensure _extract_pdf_page does not run HTML-based preprocessing."""
        result = CrawlResult(
            url="https://example.com/report.pdf",
            html="<nav>should not matter</nav><p>text</p>",
            markdown="# Report\n\nImportant findings.",
            success=True,
            is_pdf=True,
        )
        # Use tag filters that would normally strip content from HTML
        config = PageConfig(exclude_tags=["nav", "p"], include_only_tags=[])
        extractor = ContentExtractor(config)
        page = extractor._extract_page(result)
        # The markdown should be based on the CrawlResult.markdown, not the HTML
        assert "Important findings" in page.markdown

    def test_non_pdf_extension_in_url(self):
        """PDF from dynamic URL uses the full filename for title."""
        result = CrawlResult(
            url="https://example.com/download?id=123",
            markdown="Dynamic PDF content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.url == result.url
        assert "Dynamic PDF content" in page.markdown
