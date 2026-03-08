# crawl4md

A Python library for crawling websites and extracting their content as Markdown-formatted text files. Wraps [Crawl4AI](https://github.com/unclecode/crawl4ai) with a synchronous API designed for non-technical Jupyter Notebook users.

## Features

- **Synchronous API** — no `async`/`await` needed; works seamlessly in Jupyter Notebooks
- **Smart content extraction** — trafilatura for main content, markdownify for full HTML
- **WAF / bot-detection handling** — automatic retry rounds for blocked pages
- **Size-limited output files** — pages are never split across files
- **Real-time progress** — progress bar with ETA in both Jupyter and terminal
- **Configurable filtering** — include/exclude URL paths and HTML tags via regex
- **Structured item grouping** — auto-detects repeated elements (product cards, plan blocks) and inserts separators between them
- **Markdown validation** — every extracted page is auto-fixed via mdformat (with GFM support) to ensure structurally correct, renderable Markdown; a content-preservation guard prevents any words, numbers, or punctuation from being lost

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
```

`SiteCrawler` handles crawling, extraction, and file writing automatically. Output is saved to a timestamped folder in the current directory.

For step-by-step control, use the components individually:

```python
from crawl4md import ContentExtractor, FileWriter

extractor = ContentExtractor(page_config)
pages = extractor.extract(results)

writer = FileWriter()
writer.write(pages, crawler.output_dir, page_config.max_file_size_mb)
```

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
| `stealth` | `bool` | `False` | Enable bot-detection avoidance |
| `max_retries` | `int` | `2` | Retry rounds for WAF-blocked pages |
| `flush_interval` | `int` | `10` | Save progress to disk every N pages |

### PageConfig

| Parameter | Type | Default | Description |
|---|---|---|---|
| `extract_main_content` | `bool` | `True` | `True` = trafilatura (main content only), `False` = markdownify (full HTML) |
| `exclude_tags` | `list[str]` | `["nav", "script", "form", "style"]` | HTML tags to remove before extraction |
| `include_only_tags` | `list[str]` | `[]` | Keep only these HTML tags (mutually exclusive with `exclude_tags`) |
| `wait_for` | `float \| None` | `None` | Seconds to wait after page load (for JS-heavy sites) |
| `timeout` | `int` | `30000` | Page load timeout in milliseconds |
| `max_file_size_mb` | `float` | `15.0` | Max size per output file in MB |
| `output_extension` | `".txt" \| ".md"` | `".txt"` | Output file format |
| `separate_items` | `bool` | `False` | Insert `---` separators between repeated items (e.g. product cards) |
| `item_selector` | `str` | `""` | CSS selector for items; empty = auto-detect |

## Output Structure

Each crawl creates a timestamped folder with:

```
2026-03-07_14-01-02/
├── content_001.md          # Merged output (all successful pages)
├── content_002.md          # Additional file if size limit exceeded
├── urls_success.txt        # All successfully crawled URLs
├── urls_fail.txt           # URLs that failed after all retries
├── round_1_content_001.md  # Per-round content
├── round_1_urls_success.txt
├── round_1_urls_fail.txt
└── round_1_fail_content_001.md  # Error details for failed pages
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
├── writer.py         # FileWriter — size-limited output files (batch & incremental modes)
└── progress.py       # ProgressReporter — real-time progress with ETA
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## License

MIT
