# Copilot Instructions — crawl4md

## Project Overview

crawl4md is a Python library for crawling websites and extracting content as Markdown-formatted text files. It wraps Crawl4AI with a synchronous API designed for non-technical Jupyter Notebook users.

## Architecture

- **src layout**: All library code under `src/crawl4md/`.
- **Config models**: Pydantic v2 models in `config.py` — all user-facing parameters are validated here.
- **SiteCrawler**: Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter compatibility.
- **ContentExtractor**: Converts crawled HTML to Markdown text using trafilatura (main content) or markdownify (full HTML). Optionally inserts `---` separators between repeated structural items via BeautifulSoup pre-processing (`separate_items`/`item_selector`). Each page is validated per-page with mdformat (GFM extensions) after all post-processing to ensure structurally correct Markdown. A content-preservation guard compares tokens before/after formatting and falls back to the original text if any content was lost.
- **FileWriter**: Combines extracted pages into size-limited output files (`.txt` or `.md`, configurable via `PageConfig.output_extension`). Never splits a single page across files.
- **ProgressReporter**: Real-time progress display for Jupyter and terminal.

## Coding Conventions

- Python 3.10+, type hints on all public APIs.
- Pydantic v2 for data models (use `model_validator`, `field_validator`).
- Linting via ruff (config in `pyproject.toml`).
- Tests use pytest with mocked HTTP calls — never make real network requests in tests.
- Keep the notebook UX simple: plain language, no jargon, no code explanations.

## Key Dependencies

| Package | Purpose |
|---|---|
| crawl4ai | Web crawling engine with JS rendering |
| trafilatura | Main content extraction (strip boilerplate) |
| markdownify | Full HTML → Markdown conversion |
| pydantic | Config validation |
| nest-asyncio | Allows asyncio.run() inside Jupyter's event loop |
| beautifulsoup4 | HTML DOM parsing for item separation |
| mdformat | Markdown validation & auto-formatting (with mdformat-gfm for tables/strikethrough) |

## File Layout

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic config models
├── crawler.py        # SiteCrawler class
├── extractor.py      # ContentExtractor class
├── writer.py         # FileWriter class
└── progress.py       # ProgressReporter class
```

## Testing

- Tests use pytest with mocked HTTP calls — never make real network requests in tests.
- `_ROUND_COOLDOWN` (the 30 s sleep between retry rounds) is globally patched to 0 via an autouse fixture in `conftest.py`. No per-test patching is needed.
- When running tests in a terminal, **always wait for the command to finish and return its full output** before re-running, retrying, or drawing any conclusions. Do not start a new test run while one is still in progress.
