# crawl4md (core library)

The core crawling library: it follows links, extracts the main content of each
page, and writes clean, sorted Markdown. It is synchronous (no `async`/`await`
needed) and usable from a notebook, a script, or any Python backend.

For installation and the full configuration/output reference, see the repo
docs: [INSTALLATION.md](../../docs/INSTALLATION.md), [CONFIGURATION.md](../../docs/CONFIGURATION.md),
and [ARCHITECTURE.md](../../docs/ARCHITECTURE.md).

## Quick start

```python
from crawl4md import SiteCrawler, CrawlerConfig, PageConfig

config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
crawler = SiteCrawler(config, PageConfig())
results = crawler.crawl()
crawler.print_summary(results)
```

Output is written to a UTC-timestamped folder; the primary result is
`final/sorted_success_content_*.md`.

## Module map

| Module | Responsibility |
|---|---|
| `__init__.py` | Public API exports |
| `config.py` | `CrawlerConfig`, `PageConfig` (Pydantic v2) |
| `crawler.py` | `SiteCrawler` — crawl loop, retries, WAF handling, progress/cancel hooks |
| `extractor.py` | `ContentExtractor` — HTML → Markdown (trafilatura / markdownify) |
| `sorter.py` | `ContentSorter` — order pages by URL path |
| `writer.py` | `FileWriter` — size-limited content files + URL lists |
| `naming.py` | Crawl folder/timestamp names (re-exports `artifact_store.naming`) |
| `progress.py` | `ProgressReporter` — Jupyter/terminal progress |
| `_internal/` | Implementation details (final output, PDF, URL filter, …) |

## Boundary

The core library must stay usable without the UI: it must not import `streamlit`
or `crawl4md_streamlit`, and must not reference app-specific paths. It depends on
`artifact_store` for naming and path safety. Boundary tests enforce this.
