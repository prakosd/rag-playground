# crawl4md

A Python library for crawling websites and extracting their content as Markdown-formatted text files. Wraps [Crawl4AI](https://github.com/unclecode/crawl4ai) with a synchronous API designed for non-technical Jupyter Notebook users.

## Features

- **Synchronous API** — no `async`/`await` needed; works seamlessly in Jupyter Notebooks
- **Smart content extraction** — trafilatura for main content (with automatic fallback to markdownify when coverage is below 15%), plus supplementary section recovery for FAQs, accordions, and product metadata
- **WAF / bot-detection handling** — two-stage detection (HTML block signatures + post-extraction content-length check) with automatic retry rounds and cooldown between rounds
- **Size-limited output files** — pages are never split across files; oversized pages get their own file
- **Real-time progress** — animated HTML progress bar in Jupyter, plain-text ETA in terminal
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
2. **Retry** — failed/blocked pages are retried in subsequent rounds (up to `max_retries`), with a 30-second cooldown between rounds.
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
| `delay` | `float` | `0` | Seconds between page crawls (uses jitter 0.3x–3.0x) |
| `stealth` | `bool` | `True` | Enable bot-detection avoidance (random UA, stealth flags, full-page scan) |
| `headers` | `dict[str, str]` | `{}` | Custom HTTP headers passed to the browser |
| `max_retries` | `int` | `2` | Retry rounds for WAF-blocked pages |
| `flush_interval` | `int` | `10` | Save progress to disk every N pages |

### PageConfig

| Parameter | Type | Default | Description |
|---|---|---|---|
| `extract_main_content` | `bool` | `True` | `True` = trafilatura (main content only), `False` = markdownify (full HTML) |
| `exclude_tags` | `list[str]` | `["nav", "script", "form", "style"]` | HTML tags to remove before extraction |
| `include_only_tags` | `list[str]` | `[]` | Keep only these HTML tags (mutually exclusive with `exclude_tags`) |
| `wait_for` | `float \| None` | `None` | Seconds to wait after page load (for JS-heavy sites) |
| `timeout` | `float` | `30` | Page load timeout in seconds |
| `max_file_size_mb` | `float` | `15.0` | Max size per output file in MB |
| `output_extension` | `".txt" \| ".md"` | `".txt"` | Output file format |
| `separate_items` | `bool` | `False` | Insert `---` separators between repeated items (e.g. product cards) |
| `item_selector` | `str` | `""` | CSS selector for items; empty = auto-detect |
| `js_code` | `list[str]` | `[]` | JavaScript snippets to execute before extraction (e.g. expand collapsibles) |
| `scan_full_page` | `bool` | `True` | Scroll through the full page before extraction (helps bypass lazy-load WAFs) |
| `scroll_delay` | `float` | `0.4` | Seconds to pause between scroll steps (used when `scan_full_page` is on) |

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

See `notebooks/crawl4md.ipynb` for a guided, step-by-step notebook.

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

Test files: `test_config.py`, `test_crawler.py`, `test_extractor.py`, `test_sorter.py`, `test_writer.py`.

Tests use mocked HTTP calls — no real network requests are made.

## License

MIT
