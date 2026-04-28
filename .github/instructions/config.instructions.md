---
description: "Use when editing Pydantic config models in src/crawl4md/config.py or its tests. Covers CrawlerConfig, PageConfig, CrawlResult, ExtractedPage field rules and validators."
applyTo: "src/crawl4md/config.py, tests/test_config.py"
---

# Config Models

Pydantic v2 models — all user-facing parameters validated here. Use `model_validator` / `field_validator` (v2 style only).

## Models

- **CrawlerConfig** — `urls`, `exclude_paths`, `include_only_paths`, `limit`, `max_depth`, `flush_interval`, `delay`, `stealth`, `headers`, `max_retries`. Accepts CSV strings for list fields; validates regex patterns.
- **PageConfig** — `exclude_tags`, `include_only_tags`, `wait_until`, `wait_for`, `timeout`, `max_file_size_mb`, `extract_main_content`, `output_extension`, `separate_items`, `item_selector`, `js_code`, `scan_full_page`, `scroll_delay`, `ocr_languages`, `flatten_shadow_dom`. Cannot set both `exclude_tags` and `include_only_tags`.
- **CrawlResult** — `url`, `html`, `markdown`, `success`, `error`, `redirected_url`, `is_pdf`.
- **ExtractedPage** — `url`, `title`, `markdown`.

## Constraints

- `headers` is a free-form `dict[str, str]` forwarded to Crawl4AI's `BrowserConfig`.
- Type hints required on all public fields and validators.
- Pydantic field defaults are exempt from the "no inline magic values" rule.
