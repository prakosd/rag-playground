# crawl4md

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/prakosd/rag-playground)

A Python library for crawling websites and extracting their content as Markdown-formatted text files, plus a browser-based Streamlit app. It wraps [Crawl4AI](https://github.com/unclecode/crawl4ai) with a synchronous Python API and a Jupyter Notebook for technical users.

This repository is evolving into a practical RAG playground: **Step 1** crawls websites into clean Markdown and **Step 2** builds a searchable vector index from those outputs. Steps 3–5 (semantic search, RAG Q&A, conversational RAG) are placeholder workspaces for now.

**Repo rename note:** the public GitHub repository is moving to `prakosd/rag-playground`. The Python package, imports, notebook name, and Streamlit helper package remain `crawl4md` / `crawl4md_streamlit` in this phase.

## What's inside

| Package | Role |
|---|---|
| [`crawl4md`](src/crawl4md/README.md) | Core crawling library — crawl, extract, sort, write Markdown |
| [`artifact_store`](src/artifact_store/README.md) | Shared foundation — naming, path safety, archives, crawl-result discovery (pure stdlib) |
| [`vector_indexer`](src/vector_indexer/README.md) | UI-independent chunking + embedding + vector store (ChromaDB behind an interface) |
| [`apps/streamlit`](apps/streamlit/README.md) | Browser UI adapter for non-technical users (Steps 1–2 implemented) |

The libraries are UI-independent and enforced separate by boundary tests; the Streamlit app is a reference adapter over them.

## Features

- **Synchronous API** — no `async`/`await`; works seamlessly in Jupyter Notebooks
- **PDF support** — detects and extracts PDF URLs via pymupdf4llm; scanned PDFs via OCR (requires [Tesseract](https://github.com/tesseract-ocr/tesseract))
- **Smart content extraction** — trafilatura with markdownify fallback, plus supplementary recovery for FAQs, accordions, and product metadata
- **WAF / bot-detection handling** — two-stage detection with automatic retry rounds and cooldown
- **Size-limited, sorted output** — pages are never split across files; final files are sorted by URL path
- **Real-time progress** — browser charts in Streamlit, spider widget in Jupyter, plain-text ETA in terminal
- **Stop-safe output** — stopping a crawl still writes final output for completed pages
- **Vector indexing (Step 2)** — index `.md` / `.txt` / `.zip` outputs into a ChromaDB vector store with configurable chunking and embedding providers (Amazon Titan, OpenAI, or an offline default)

## Quick start (library)

```python
from crawl4md import SiteCrawler, CrawlerConfig, PageConfig

config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
crawler = SiteCrawler(config, PageConfig())
results = crawler.crawl()
crawler.print_summary(results)  # output in a timestamped folder; primary: final/sorted_success_content_*.md
```

For step-by-step control, use `ContentExtractor`, `ContentSorter`, and `FileWriter` individually (see [src/crawl4md/README.md](src/crawl4md/README.md)).

## Run it

- **No-install (Codespaces / Dev Container):** click the badge above or reopen in the dev container — Streamlit auto-starts at `http://localhost:8501`. See [docs/INSTALLATION.md](docs/INSTALLATION.md).
- **Streamlit app locally:**
  ```bash
  pip install -e ".[vector,bedrock]" -e "apps/streamlit"
  cd apps/streamlit && streamlit run
  ```
  Then open `http://localhost:8501`. Step 1 crawls a site; Step 2 turns the results into a vector index. Outputs are saved under `outputs/streamlit_sessions/`.
- **Notebook:** open `notebooks/crawl4md.ipynb`.

## Documentation

| Topic | Doc |
|---|---|
| Install & environments | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| Configuration & output reference | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Architecture & data flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Development (tests, lint, conventions) | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Building another UI over the libraries | [docs/BUILDING_ANOTHER_UI.md](docs/BUILDING_ANOTHER_UI.md) |
| Core crawler | [src/crawl4md/README.md](src/crawl4md/README.md) |
| Shared foundation | [src/artifact_store/README.md](src/artifact_store/README.md) |
| Vector indexer | [src/vector_indexer/README.md](src/vector_indexer/README.md) |
| Streamlit app | [apps/streamlit/README.md](apps/streamlit/README.md) |

## License

MIT
