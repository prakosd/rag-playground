---
description: "Use when editing SiteCrawler in src/crawl4md/crawler.py or its tests (crawler, retry, output, pdf). Covers URL filtering, PDF handling, WAF detection, progress/cancel hooks, retry/cooldown, and stop-safe final output."
applyTo: "src/crawl4md/crawler.py, tests/test_crawler.py, tests/test_crawler_retry.py, tests/test_crawler_output.py, tests/test_pdf.py"
---

# SiteCrawler

Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter; Windows uses `ProactorEventLoop` in a `ThreadPoolExecutor`.

## Constraints

- **URL filtering:** same-domain only (`www.` stripped), skips static asset extensions (except `.pdf`), applies path regex filters, skips template placeholders (`{{`, `{%`).
- **PDF:** URL extension fast path + Content-Type HEAD fallback. Fetched via httpx, converted via pymupdf4llm. `CrawlResult.is_pdf` routes to `_extract_pdf_page()` (skips HTML preprocessing). OCR via `PageConfig.ocr_languages` (default `["eng", "msa"]`); empty list disables. Tesseract errors caught once with warning.
- **WAF detection:** HTML signature check + post-extraction content-length check.
- **Progress/cancel hooks:** `progress_callback` receives event mappings for UI consumers such as Streamlit, and `should_cancel` allows cooperative cancellation. Both must remain optional and must not introduce a Streamlit dependency into `crawler.py`.
- **Retry rounds** downgrade `wait_until` to `domcontentloaded` via `_FALLBACK_WAIT_UNTIL`.
- `_sleep_with_cancel()` should use chunked polling only when `should_cancel` is provided; without a cancel hook, keep the existing plain sleep behavior so retry timing tests remain stable.
- `_ROUND_COOLDOWN` is patched to 0 in tests via autouse fixture in `conftest.py`.
- Cancellation should preserve sidecar-based final and sorted-final output for completed pages. Do not reintroduce saved-session checkpoint or resume APIs.
