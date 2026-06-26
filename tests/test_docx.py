"""Tests for DOCX crawling and extraction support (SiteCrawler integration)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crawl4md.config import CrawlerConfig, CrawlResult, PageConfig
from crawl4md.crawler import (
    _JITTER_RETRY_MAX,
    _JITTER_RETRY_MIN,
    SiteCrawler,
)
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.writer import FileWriter


class TestCrawlResultIsDocx:
    def test_is_docx_default_false(self):
        assert CrawlResult(url="https://example.com").is_docx is False

    def test_is_docx_explicit_true(self):
        assert CrawlResult(url="https://example.com/d.docx", is_docx=True).is_docx is True


class TestIsDocxUrl:
    def test_plain_docx_url(self):
        assert SiteCrawler._is_docx_url("https://example.com/report.docx") is True

    def test_docx_with_query_and_fragment(self):
        assert SiteCrawler._is_docx_url("https://example.com/r.docx?token=a#x") is True

    def test_case_insensitive(self):
        assert SiteCrawler._is_docx_url("https://example.com/R.DOCX") is True

    def test_legacy_doc_is_not_docx(self):
        assert SiteCrawler._is_docx_url("https://example.com/old.doc") is False

    def test_non_docx_url(self):
        assert SiteCrawler._is_docx_url("https://example.com/page.html") is False


def test_is_document_url_true_for_both_pdf_and_docx():
    assert SiteCrawler._is_document_url("https://example.com/a.pdf") is True
    assert SiteCrawler._is_document_url("https://example.com/a.docx") is True
    assert SiteCrawler._is_document_url("https://example.com/a.html") is False


class TestIsDocxResponse:
    @pytest.mark.asyncio
    async def test_docx_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {
            "content-type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        }
        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_docx_response("https://example.com/download?id=1")
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
            result = await SiteCrawler._is_docx_response("https://example.com/page")
        assert result is False


@pytest.mark.asyncio
async def test_download_docx_wires_mammoth_and_markdownify():
    config = MagicMock()
    config.headers = {"User-Agent": "test"}
    crawler = SiteCrawler.__new__(SiteCrawler)
    crawler.config = config
    crawler.page_config = PageConfig()

    response = MagicMock()
    response.content = b"docx-bytes"
    response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    crawler._pdf_client = mock_client

    mammoth_result = MagicMock()
    mammoth_result.value = "<h1>Report</h1>"

    mock_mammoth = MagicMock()
    mock_mammoth.convert_to_html = MagicMock(return_value=mammoth_result)
    mock_markdownify = MagicMock()
    mock_markdownify.markdownify = MagicMock(return_value="# Report")
    with (
        patch("crawl4md.crawler.mammoth", mock_mammoth),
        patch("crawl4md.crawler.markdownify", mock_markdownify),
    ):
        result = await crawler._download_docx("https://example.com/report.docx")

    assert result.success is True
    assert result.is_docx is True
    assert result.markdown == "# Report"
    mock_client.get.assert_awaited_once_with("https://example.com/report.docx")
    mock_markdownify.markdownify.assert_called_once()


@patch("crawl4md.crawler.AsyncWebCrawler")
def test_direct_docx_url_writes_markdown(mock_crawler_cls, tmp_path):
    docx_url = "https://example.com/report.docx"
    mock_browser = AsyncMock()
    mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
    mock_browser.__aexit__ = AsyncMock(return_value=False)
    mock_crawler_cls.return_value = mock_browser

    response = MagicMock()
    response.content = b"docx-bytes"
    response.raise_for_status = MagicMock()
    mock_doc_client = AsyncMock()
    mock_doc_client.get = AsyncMock(return_value=response)
    mock_doc_client.__aenter__ = AsyncMock(return_value=mock_doc_client)
    mock_doc_client.__aexit__ = AsyncMock(return_value=False)

    mammoth_result = MagicMock()
    mammoth_result.value = "<h1>Report</h1><p>Body text here.</p>"

    page_config = PageConfig(extract_main_content=False, ocr_languages=[])
    crawler = SiteCrawler(
        CrawlerConfig(urls=[docx_url], limit=1, max_retries=0, flush_interval=1),
        page_config,
        output_base=tmp_path,
        extractor=ContentExtractor(page_config),
        writer=FileWriter(max_file_size_mb=15.0),
    )

    mock_mammoth = MagicMock()
    mock_mammoth.convert_to_html = MagicMock(return_value=mammoth_result)
    mock_markdownify = MagicMock()
    mock_markdownify.markdownify = MagicMock(return_value="# Report\n\nBody text here.")
    with (
        patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_doc_client),
        patch("crawl4md.crawler.mammoth", mock_mammoth),
        patch("crawl4md.crawler.markdownify", mock_markdownify),
    ):
        results = crawler.crawl()

    assert results[0].success is True
    assert results[0].is_docx is True
    mock_mammoth.convert_to_html.assert_called_once()
    all_text = "".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in tmp_path.rglob("*")
        if path.is_file() and path.suffix in {".txt", ".md"}
    )
    assert "Body text here." in all_text


def test_direct_docx_retry_delay_uses_retry_jitter(tmp_path):
    docx_url = "https://example.com/retry.docx"
    crawler = SiteCrawler(
        CrawlerConfig(urls=[docx_url], delay=5, max_retries=0), output_base=tmp_path
    )
    crawler.output_dir = tmp_path
    crawler._download_docx = AsyncMock(
        return_value=CrawlResult(url=docx_url, markdown="# Doc", success=True, is_docx=True)
    )
    progress = ProgressReporter(1, log_dir=tmp_path)
    results: list[CrawlResult] = []

    async def run_direct_docx_retry() -> None:
        await crawler._handle_direct_docx_url(
            url=docx_url,
            results=results,
            generated={docx_url},
            prior_success=0,
            prior_fail=0,
            queue=[],
            progress=progress,
            round_num=2,
            crawl_depth=1,
            round_dir=None,
            is_retry=True,
        )

    with (
        patch("crawl4md.crawler.random.uniform", return_value=2.0) as mock_uniform,
        patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        asyncio.run(run_direct_docx_retry())

    progress.close()
    mock_uniform.assert_called_once_with(_JITTER_RETRY_MIN, _JITTER_RETRY_MAX)
    mock_sleep.assert_awaited_once_with(10.0)
    assert [result.url for result in results] == [docx_url]


@pytest.mark.asyncio
async def test_handle_docx_fallback_redownloads_when_content_type_is_docx(tmp_path):
    docx_url = "https://example.com/download?id=1"
    crawler = SiteCrawler(CrawlerConfig(urls=[docx_url], max_retries=0), output_base=tmp_path)
    crawler._pdf_client = None
    crawler._is_docx_response = AsyncMock(return_value=True)
    crawler._download_docx = AsyncMock(
        return_value=CrawlResult(url=docx_url, markdown="# Doc", success=True, is_docx=True)
    )
    thin = CrawlResult(url=docx_url, html="<html></html>", markdown="x", success=True)
    results = [thin]
    progress = ProgressReporter(1, log_dir=tmp_path)

    crawl_result, _ = await crawler._handle_docx_fallback(
        url=docx_url,
        crawl_result=thin,
        results=results,
        terminal_page=None,
        progress=progress,
    )

    progress.close()
    assert crawl_result.is_docx is True
    assert results[-1].is_docx is True
    crawler._download_docx.assert_awaited_once_with(docx_url)
