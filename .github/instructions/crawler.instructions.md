---
description: "Use when editing SiteCrawler in src/crawl4md/crawler.py or its tests (crawler, retry, output, session, pdf). Covers URL filtering, PDF handling, WAF detection, retry/cooldown, and resume()."
applyTo: "src/crawl4md/crawler.py, tests/test_crawler.py, tests/test_crawler_retry.py, tests/test_crawler_output.py, tests/test_session.py, tests/test_pdf.py"
---

# SiteCrawler

Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter; Windows uses `ProactorEventLoop` in a `ThreadPoolExecutor`.

## Constraints

- **URL filtering:** same-domain only (`www.` stripped), skips static asset extensions (except `.pdf`), applies path regex filters, skips template placeholders (`{{`, `{%`).
- **PDF:** URL extension fast path + Content-Type HEAD fallback. Fetched via httpx, converted via pymupdf4llm. `CrawlResult.is_pdf` routes to `_extract_pdf_page()` (skips HTML preprocessing). OCR via `PageConfig.ocr_languages` (default `["eng", "msa"]`); empty list disables. Tesseract errors caught once with warning.
- **WAF detection:** HTML signature check + post-extraction content-length check.
- **Retry rounds** downgrade `wait_until` to `domcontentloaded` via `_FALLBACK_WAIT_UNTIL`.
- `_ROUND_COOLDOWN` is patched to 0 in tests via autouse fixture in `conftest.py`.
- `resume()` is a classmethod. Restores content/extraction settings from saved session; only behavioral settings can be overridden via kwargs: `limit`, `max_depth`, `max_retries`, `delay`, `stealth`, `headers`, `flush_interval`, `wait_until`, `wait_for`, `timeout`, `max_file_size_mb`.
