---
description: "Use when editing Pydantic config models in src/crawl4md/config.py or its tests. Covers CrawlerConfig, PageConfig, CrawlResult, ExtractedPage field rules and validators."
applyTo: "src/crawl4md/config.py, tests/test_config.py"
---

# Config Models

Pydantic v2 models — all user-facing parameters validated here. Use `model_validator` / `field_validator` (v2 style only).

## Models

- **CrawlerConfig** — `urls`, `exclude_paths`, `include_only_paths`, `limit`, `max_depth`, `max_concurrent`, `flush_interval`, `delay`, `stealth`, `headers`, `max_retries`, `proxies`. Accepts CSV strings for list fields (including `proxies`); validates regex patterns. `proxies` is `repr=False` (never logged — may carry credentials) and feeds Crawl4AI's per-request `proxy_config` (direct-first escalation). Undetected-browser escalation is automatic on retry rounds (no config field).
- **PageConfig** — `exclude_tags`, `include_only_tags`, `wait_until`, `wait_for`, `timeout`, `max_file_size_mb`, `extract_main_content`, `output_extension`, `separate_items`, `item_selector`, `js_code`, `scan_full_page`, `scroll_delay`, `ocr_languages`, `flatten_shadow_dom`. Cannot set both `exclude_tags` and `include_only_tags`.
- **CrawlResult** — `url`, `html`, `markdown`, `success`, `error`, `error_code`, `redirected_url`, `is_pdf`, `is_docx`. `error` is free-text human detail; `error_code` is an optional stable code from `crawl4md.messages` (e.g. `crawl.blocked`, `crawl.empty_content`) so a UI can localize without parsing `error`. `is_pdf`/`is_docx` flag a binary document whose Markdown was produced by the matching `_internal` downloader (the extractor routes these straight to its document path, skipping HTML preprocessing).
- **ExtractedPage** — `url`, `title`, `markdown`.

## Constraints

- `headers` is a free-form `dict[str, str]` forwarded to Crawl4AI's `BrowserConfig`.
- Type hints required on all public fields and validators.
- Pydantic field defaults are exempt from the "no inline magic values" rule.
