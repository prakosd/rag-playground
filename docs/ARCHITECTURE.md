# Architecture

← Back to [README](../README.md)

The repository is organized in layers. A shared foundation (`artifact_store`) sits
under two independent libraries (`crawl4md` for crawling, `vector_indexer` for
indexing). The Streamlit app is a UI adapter over those libraries and owns only
rendering, session/browser state, background jobs, and downloads.

```mermaid
flowchart TD
  ArtifactStore["artifact_store<br/>naming · paths · archives · crawl-result discovery"]
  Crawl4md["crawl4md<br/>crawl → extract → write → sort"]
  VectorIndexer["vector_indexer<br/>load → chunk → embed → vector store"]
  App["apps/streamlit<br/>UI shell, pages, background jobs"]
  ArtifactStore --> Crawl4md
  ArtifactStore --> VectorIndexer
  Crawl4md --> App
  VectorIndexer --> App
```

## Step 1 — how crawling works

```mermaid
flowchart TD
  Seeds["Seed URLs"] --> SiteCrawler["SiteCrawler.crawl()<br/>sync entry point"]
  SiteCrawler --> Crawl4AI["Crawl4AI<br/>browser crawl"]
  Crawl4AI --> CrawlResult["CrawlResult<br/>raw HTML"]
  CrawlResult --> Extractor["ContentExtractor"]
  Extractor --> ExtractedPage["ExtractedPage<br/>clean Markdown"]
  ExtractedPage --> RoundWriter["FileWriter<br/>round snapshots"]
  RoundWriter --> RoundFiles["round_N/<br/>content + URL lists"]
  ExtractedPage --> Sorter["ContentSorter<br/>URL-path order"]
  Sorter --> FinalWriter["FileWriter<br/>merged final output"]
  FinalWriter --> FinalFiles["final/<br/>sorted content + URLs"]
```

1. **Crawl** — seed URLs are crawled with link discovery up to `max_depth`. Discovered links are queued up to `limit`.
2. **Retry** — failed/blocked pages are retried in subsequent rounds (up to `max_retries`), with a 30-second cooldown between rounds. Retry rounds automatically downgrade `wait_until` to `domcontentloaded`. Link discovery continues in retry rounds.
3. **Extract** — HTML is converted to Markdown via trafilatura or markdownify, then cleaned through a 7-step post-processing pipeline.
4. **Write** — pages are written to numbered, size-limited files. Per-round files are produced during the crawl; final merged and sorted files are written after all rounds complete.

```mermaid
flowchart TD
  Initial["Initial crawl round"] --> Failed{"Failed or blocked pages?"}
  Failed -->|No| Merge["Merge rounds and write final output"]
  Failed -->|Yes, retry budget remains| Cooldown["Cooldown before retry round"]
  Cooldown --> Downgrade["Retry round uses domcontentloaded"]
  Downgrade --> Retry["Retry failed or blocked URLs"]
  Retry --> Discover["Recovered pages may discover more links"]
  Discover --> Failed
  Failed -->|Retry limit reached| FinalFailures["Keep unresolved URLs in final fail files"]
  FinalFailures --> Merge
```

## Step 2 — how indexing works

Step 2 builds on the final `.md` / `.txt` outputs (or uploaded files) without
changing the crawl pipeline.

```mermaid
flowchart TD
  Inputs["selected crawl results + uploads<br/>.md / .txt / .zip"] --> Loader["document_loader<br/>(.zip → .md/.txt members)"]
  Loader --> Chunker["chunking<br/>overlapping chunks"]
  Chunker --> Embed["EmbeddingProvider<br/>Titan / OpenAI / offline"]
  Embed --> Store["VectorStore (ChromaDB)<br/>vector_<id>/<timestamp>/chroma"]
  Store --> Result["IndexingResult + manifest.json"]
```

The embedding provider and vector store are both behind interfaces, so a provider
or database can change without touching the application layer. See
[src/vector_indexer/README.md](../src/vector_indexer/README.md).

## Library layers

**Core library (crawl4md):**

```mermaid
flowchart TD
  PublicAPI["__init__.py<br/>public API"] --> Config["config.py<br/>models"]
  Config --> Crawler["crawler.py<br/>SiteCrawler"]
  Crawler --> Pipeline["extractor.py<br/>writer.py<br/>sorter.py"]
  Crawler --> Progress["progress.py<br/>ProgressReporter"]
```

**Streamlit adapter:**

```mermaid
flowchart TD
  App["streamlit_app.py<br/>UI shell"] --> Inputs["controls.py<br/>form_ui.py · vector_form_ui.py"]
  App --> Pages["pages.py<br/>navigation metadata"]
  Inputs --> Jobs["crawl_jobs.py · vector_index_jobs.py<br/>background jobs"]
  Jobs --> Outputs["generated_files.py<br/>session_manager.py"]
  Support["support.py<br/>compat exports"] --> Jobs
  Support --> Outputs
```

**Adapter boundary:** the app builds configs and runs the libraries, then renders
their emitted events and generated files. It does not reimplement crawling or
indexing.

The crawl adapter passes optional integration hooks into `SiteCrawler`
(`output_base`, `session_id`, `progress_callback`, `should_cancel`) and reads
`progress_history.jsonl` from each crawl root to restore chart history after page
reloads.
