# Copilot Instructions — crawl4md

## Project Overview

crawl4md is a Python library for crawling websites and extracting content as Markdown-formatted text files. It wraps Crawl4AI with a synchronous API designed for non-technical Jupyter Notebook users.

## Data Flow

```
SiteCrawler.crawl()
  ├─ Crawl4AI (async) → CrawlResult (raw HTML per page)
  ├─ ContentExtractor  → ExtractedPage (clean Markdown per page)
  ├─ FileWriter         → size-limited content files + URL lists
  └─ ContentSorter      → sorted final files grouped by URL path
```

Each crawl creates a timestamped output directory. Results pass through multiple rounds (initial + retries), then merged, deduplicated, and sorted.

## File Layout

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic config models
├── crawler.py        # SiteCrawler class
├── extractor.py      # ContentExtractor class
├── sorter.py         # ContentSorter class
├── writer.py         # FileWriter class
└── progress.py       # ProgressReporter class
```

## Architecture

### Config models (`config.py`)

Pydantic v2 models — all user-facing parameters validated here.

- **CrawlerConfig** — `urls`, `exclude_paths`, `include_only_paths`, `limit`, `max_depth`, `flush_interval`, `delay`, `stealth`, `headers`, `max_retries`. Accepts CSV strings for list fields; validates regex patterns.
- **PageConfig** — `exclude_tags`, `include_only_tags`, `wait_until`, `wait_for`, `timeout`, `max_file_size_mb`, `extract_main_content`, `output_extension`, `separate_items`, `item_selector`, `js_code`, `scan_full_page`, `scroll_delay`, `ocr_languages`, `flatten_shadow_dom`. Cannot set both `exclude_tags` and `include_only_tags`.
- **CrawlResult** — `url`, `html`, `markdown`, `success`, `error`, `redirected_url`, `is_pdf`.
- **ExtractedPage** — `url`, `title`, `markdown`.
- `headers` is a free-form `dict[str, str]` forwarded to Crawl4AI's `BrowserConfig`.

### SiteCrawler (`crawler.py`)

Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter; Windows uses `ProactorEventLoop` in a `ThreadPoolExecutor`.

**Constraints:**

- URL filtering: same-domain only (`www.` stripped), skips static asset extensions (except `.pdf`), applies path regex filters, skips template placeholders (`{{`, `{%`).
- PDF: URL extension fast path + Content-Type HEAD fallback. Fetched via httpx, converted via pymupdf4llm. `CrawlResult.is_pdf` routes to `_extract_pdf_page()` (skips HTML preprocessing). OCR via `PageConfig.ocr_languages` (default `["eng", "msa"]`); empty list disables. Tesseract errors caught once with warning.
- WAF detection: HTML signature check + post-extraction content-length check.
- Retry rounds downgrade `wait_until` to `domcontentloaded` via `_FALLBACK_WAIT_UNTIL`.
- `_ROUND_COOLDOWN` is patched to 0 in tests via autouse fixture in `conftest.py`.
- `resume()` is a classmethod. Restores content/extraction settings from saved session; only behavioral settings can be overridden via kwargs: `limit`, `max_depth`, `max_retries`, `delay`, `stealth`, `headers`, `flush_interval`, `wait_until`, `wait_for`, `timeout`, `max_file_size_mb`.

### ContentExtractor (`extractor.py`)

Converts HTML to Markdown. Modes: trafilatura (default, `extract_main_content=True`) with markdownify fallback; markdownify-only; PDF mode (`is_pdf=True`).

**Constraints:**

- Pre-processing always runs (tag filtering, strikethrough preservation, heading spacing, empty link population, item separation, table fixing).
- `_populate_empty_links()` has no config flag.
- `_insert_item_separators()` uses `_ITEM_SENTINEL` that must survive trafilatura extraction.
- Supplementary section and product metadata recovery in trafilatura mode only.
- mdformat validation falls back to original if any content is lost.

### FileWriter (`writer.py`)

**Constraints:** Both batch (`write()`) and incremental (`add()`/`flush()`/`reset()`) modes must be maintained. Oversized pages get their own file with `UserWarning`. Symmetric `_fail_writer` for failed pages. Extension via `PageConfig.output_extension`.

### ProgressReporter (`progress.py`)

Auto-detects Jupyter vs terminal. Jupyter widget uses `_repr_html_()` — all CSS classes prefixed `c4md-`. Colors in `_LIGHT_COLORS`/`_DARK_COLORS` with dark-mode media queries.

**Colab:** `_repr_html_colab()` uses inline `style="..."` only — no `<style>` blocks, `@keyframes`, `position: absolute`, `filter`, or `animation` (stripped by Colab's sanitizer).

## Output File Naming

Timestamped folder (`YYYY-MM-DD_HH-MM-SS`):

```
round_{N}_{success|fail}_content_{NNN}.ext   # Per-round
round_{N}_{success|fail}_urls.txt
final_{success|fail}_content_{NNN}.ext       # Merged
final_{success|fail}_urls.txt
sorted_final_{success|fail}_content_{NNN}_of_{TTT}.ext  # Sorted
sorted_final_{success|fail}_urls.txt
```

`{N}` = round (1-based), `{NNN}` = file index (001…), `ext` = `PageConfig.output_extension`.

## Coding Conventions

- Python 3.10+, type hints on all public APIs. Pydantic v2 (`model_validator`, `field_validator`). Linting via ruff (`pyproject.toml`).
- Tests use mocked HTTP — never real network requests. Keep notebook UX simple: plain language, no jargon.
- **No inline magic values:** Thresholds, tag lists, regex patterns, repeated string literals → `_UPPER_SNAKE_CASE` constants (grouped after imports). Regex `re.compile()`d at module level. **Exempt:** Pydantic field defaults, standard Python idioms, spec-defined keys used once, trivial markdown strings (`"- "`, `"### "`).

## Dev Environment

Defined in `.devcontainer/devcontainer.json` (Python 3.12 + Chromium via Playwright + Tesseract OCR).

- `--shm-size=2g` is required — Chromium crashes with Docker's default 64 MB `/dev/shm`.
- Tesseract `eng` + `msa` are pre-installed to match `PageConfig.ocr_languages` defaults.
- The yarn apt source is removed before `apt-get update` (expired GPG key in the base image).
- Setup order: `pip install -e '.[dev]'` → `playwright install --with-deps chromium` → `crawl4ai-setup`.

## Dependencies

crawl4ai, trafilatura, markdownify, pydantic, nest-asyncio, beautifulsoup4, mdformat + mdformat-gfm, pymupdf4llm, httpx. Full list in `pyproject.toml`.

## Testing

- Every code change needs unit tests (happy path + key edge cases; bug fixes need a reproducing test).
- Start with a TODO list before implementing. Task is complete only when tests AND linting are both clean.
- Tests: `python -m pytest tests/ -q`. Lint: `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- **Delegate test/lint runs to the `test-runner` agent** (two-pass: quiet first, then verbose re-run of failures only).
- Wait for full test output before re-running or drawing conclusions.

## Maintaining This File

Target: under 250 lines. **Keep:** constraints not discoverable from source — conventions, gotchas, cross-module rules, testing policy, output naming. **Omit:** implementation details readable from source. Update only when a constraint or convention changes. Update README.md for user-facing behavior changes. When adding/removing Python dependencies or system packages, also review `.devcontainer/devcontainer.json`.
