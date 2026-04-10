# crawl4md

A Python library for crawling websites and extracting their content as Markdown-formatted text files. Wraps [Crawl4AI](https://github.com/unclecode/crawl4ai) with a synchronous API designed for non-technical Jupyter Notebook users.

## Features

- **Synchronous API** — no `async`/`await` needed; works seamlessly in Jupyter Notebooks
- **PDF support** — automatically detects and extracts content from PDF URLs (via URL extension or Content-Type fallback), converting them to Markdown using pymupdf4llm. Scanned/image-only PDFs are handled via OCR (requires [Tesseract](https://github.com/tesseract-ocr/tesseract) installed on the system).
- **Smart content extraction** — trafilatura for main content (with automatic fallback to markdownify when coverage is below 15%), plus supplementary section recovery for FAQs, accordions, and product metadata
- **WAF / bot-detection handling** — two-stage detection (HTML block signatures + post-extraction content-length check) with automatic retry rounds and cooldown between rounds
- **Size-limited output files** — pages are never split across files; oversized pages get their own file
- **Real-time progress** — animated spider progress widget in Jupyter (with live activity tracking and duration log), plain-text ETA in terminal
- **Configurable filtering** — include/exclude URL paths and HTML tags via regex
- **Structured item grouping** — auto-detects repeated elements (product cards, plan blocks) via DOM analysis and inserts `---` separators; supports custom CSS selectors
- **Markdown validation** — every extracted page is auto-fixed via mdformat (with GFM support) to ensure structurally correct, renderable Markdown; a content-preservation guard prevents any words, numbers, or punctuation from being lost
- **Sorted output** — final files are sorted by URL path for natural reading order

## Installation

```bash
pip install -e ".[dev]"
crawl4ai-setup                         # one-time browser setup
playwright install --with-deps chromium # install Chromium for JS rendering
```

Requires Python 3.10+.

## Quick Start

```python
from crawl4md import SiteCrawler, CrawlerConfig, PageConfig

config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
page_config = PageConfig()

crawler = SiteCrawler(config, page_config)
results = crawler.crawl()

# Print a summary of results and output file locations
crawler.print_summary(results)
```

`SiteCrawler` handles crawling, extraction, and file writing automatically. Output is saved to a timestamped folder (e.g. `2026-03-07_14-01-02/`) in the current directory.

For step-by-step control, use the components individually:

```python
from crawl4md import ContentExtractor, ContentSorter, FileWriter

extractor = ContentExtractor(page_config)
pages = extractor.extract(results)

sorter = ContentSorter()
pages = sorter.sort(pages)

writer = FileWriter()
writer.write(pages, crawler.output_dir, page_config.max_file_size_mb)
```

## How It Works

```
SiteCrawler.crawl()
  ├─ Crawl4AI (async)   → CrawlResult (raw HTML per page)
  ├─ ContentExtractor    → ExtractedPage (clean Markdown per page)
  ├─ FileWriter          → size-limited content files + URL lists
  └─ ContentSorter       → sorted final files grouped by URL path
```

1. **Crawl** — seed URLs are crawled with link discovery up to `max_depth`. Discovered links are queued up to `limit`.
2. **Retry** — failed/blocked pages are retried in subsequent rounds (up to `max_retries`), with a 30-second cooldown between rounds. Retry rounds automatically downgrade `wait_until` to `domcontentloaded` to avoid repeated timeouts. Link discovery continues in retry rounds — pages that recover on retry have their links discovered and crawled (respecting `max_depth` and `limit`).
3. **Extract** — HTML is converted to Markdown via trafilatura or markdownify, then cleaned through a 7-step post-processing pipeline.
4. **Write** — pages are written to numbered, size-limited files. Per-round files are produced during crawl; final merged and sorted files are written after all rounds complete.

## Configuration

### CrawlerConfig

| Parameter | Type | Default | Description |
|---|---|---|---|
| `urls` | `list[str]` | *(required)* | Seed URLs to crawl (comma-separated string also accepted) |
| `limit` | `int` | `1` | Maximum pages to crawl |
| `max_depth` | `int` | `1` | How many clicks deep to follow links |
| `exclude_paths` | `list[str]` | `[]` | Regex patterns for URLs to skip |
| `include_only_paths` | `list[str]` | `[]` | Regex patterns for URLs to keep (skip everything else) |
| `delay` | `float` | `0` | Seconds to wait between page crawls — paces your crawl to avoid triggering bot detection (round 1: jitter 0.1x–1.0x; retries: jitter 0.3x–3.0x). WAF back-off (3–15 s) always applies on block detection. |
| `stealth` | `bool` | `True` | Enable bot-detection avoidance (random UA, stealth flags, full-page scan) |
| `headers` | `dict[str, str]` | `{}` | Custom HTTP headers passed to the browser |
| `max_retries` | `int` | `2` | Retry rounds for WAF-blocked pages (minimum 2) |
| `flush_interval` | `int` | `10` | Save progress to disk every N pages |

### PageConfig

| Parameter | Type | Default | Description |
|---|---|---|---|
| `extract_main_content` | `bool` | `True` | `True` = trafilatura (main content only), `False` = markdownify (full HTML) |
| `exclude_tags` | `list[str]` | `["nav", "script", "form", "style"]` | HTML tags to remove before extraction |
| `include_only_tags` | `list[str]` | `[]` | Keep only these HTML tags (mutually exclusive with `exclude_tags`) |
| `wait_until` | `str` | `"networkidle"` | When to consider a page loaded. `"networkidle"` waits until network traffic stops (thorough, good for JS-heavy sites). `"domcontentloaded"` returns as soon as the HTML is parsed (faster, good for simple/static sites). Capped by `timeout`. Retry rounds automatically downgrade to `"domcontentloaded"` to avoid repeated timeouts. |
| `wait_for` | `float \| None` | `None` | Extra delay (seconds) **after** `wait_until` completes, before extracting content — gives slow JavaScript time to finish rendering. Runs on top of `wait_until`, not instead of it. |
| `timeout` | `float` | `30` | Hard limit (seconds) for the page load phase — if `wait_until` hasn't resolved within this time, the page is treated as loaded anyway. Does not include `wait_for`. |
| `max_file_size_mb` | `float` | `15.0` | Max size per output file in MB |
| `output_extension` | `".txt" \| ".md"` | `".txt"` | Output file format |
| `separate_items` | `bool` | `True` | Insert `---` separators between repeated items (e.g. product cards) |
| `item_selector` | `str` | `""` | CSS selector for items; empty = auto-detect |
| `js_code` | `list[str]` | `[]` | JavaScript snippets to execute before extraction (e.g. expand collapsibles) |
| `scan_full_page` | `bool` | `True` | Scroll through the full page before extraction (helps bypass lazy-load WAFs) |
| `scroll_delay` | `float` | `0.4` | Seconds to pause between scroll steps (used when `scan_full_page` is on) |
| `ocr_languages` | `list[str]` | `["eng", "msa"]` | Tesseract language codes for PDF OCR (e.g. `["eng", "fra"]`). Empty list disables OCR. Requires Tesseract installed. |

### Page Timing

The timing parameters control different phases of each page crawl:

```
For each page:
  delay          wait_until               wait_for          extract
  ─────── → ──────────────────── → ────────────────── → ────────────
  pause     page load condition     extra JS pause       content
  between   ("networkidle" or       (runs after load     extraction
  pages     "domcontentloaded")     condition is met)
            └─ timeout caps this ─┘
```

- **`delay`** (CrawlerConfig) — pause *between* pages. Controls crawl speed to avoid bot detection. Applied before starting the next page.
- **`wait_until`** (PageConfig) — determines *when* a page is considered loaded. `"networkidle"` waits until all network requests finish (~500 ms of silence), which is thorough but can hang on analytics-heavy sites. `"domcontentloaded"` returns as soon as the HTML is parsed, which is faster but may miss JS-rendered content. On retry rounds, `wait_until` is automatically downgraded to `"domcontentloaded"` to avoid repeated timeouts.
- **`wait_for`** (PageConfig) — extra pause *after* `wait_until` completes. Use this when content appears slightly after the page load event (e.g., delayed AJAX calls). Runs on top of `wait_until`, not instead of it.
- **`timeout`** (PageConfig) — hard limit on the `wait_until` phase. If the load condition hasn't been met within this time, the page is treated as loaded anyway and extraction proceeds.

## Output Structure

Each crawl creates a timestamped folder with three tiers of output:

```
2026-03-08_17-39-59/
│
│  # Per-round files (written during crawl)
├── round_1_success_content_001.md
├── round_1_success_urls.txt
├── round_1_fail_content_001.md        # Error details + raw HTML for blocked pages
├── round_1_fail_urls.txt
├── round_2_success_content_001.md     # Retry round (if needed)
├── round_2_fail_urls.txt
│
│  # Final merged files (after all rounds, unsorted)
├── final_success_content_001.md       # All successful pages merged
├── final_success_content_002.md       # Additional file if size limit exceeded
├── final_fail_content_001.md          # All failed pages merged
├── final_success_urls.txt             # All successful URLs (deduplicated)
├── final_fail_urls.txt                # URLs that never succeeded
│
│  # Sorted final files (grouped by URL path)
├── sorted_final_success_content_001.md
├── sorted_final_fail_content_001.md
├── sorted_final_success_urls.txt
└── sorted_final_fail_urls.txt
```

## Notebook Usage

See `notebooks/crawl4md.ipynb` for a guided, step-by-step notebook. You can also run it directly in Google Colab:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/prakosd/crawl4md/blob/master/notebooks/crawl4md.ipynb)

## Architecture

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic v2 config models (CrawlerConfig, PageConfig, CrawlResult, ExtractedPage)
├── crawler.py        # SiteCrawler — synchronous wrapper around Crawl4AI
├── extractor.py      # ContentExtractor — HTML → Markdown via trafilatura or markdownify, validated with mdformat
├── sorter.py         # ContentSorter — sorts pages by URL path for natural display order
├── writer.py         # FileWriter — size-limited output files (batch & incremental modes)
└── progress.py       # ProgressReporter — real-time progress with ETA (Jupyter & terminal)
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

Test files: `test_config.py`, `test_crawler.py`, `test_crawler_output.py`, `test_crawler_retry.py`, `test_extractor.py`, `test_extractor_items.py`, `test_extractor_links.py`, `test_extractor_product.py`, `test_extractor_supplementary.py`, `test_sorter.py`, `test_writer.py`, `test_progress.py`.

Tests use mocked HTTP calls — no real network requests are made.

## License

MIT
