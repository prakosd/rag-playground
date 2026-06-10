# Building Another UI

← Back to [README](../README.md)

The bundled Streamlit app is a reference adapter over the `crawl4md` library, not a
required runtime. Another UI stack (such as React) can reproduce the same crawl
behavior and generated files by calling `crawl4md` from a Python backend or worker
and letting the library keep ownership of crawling, extraction, file writing, final
output generation, and YAML front matter.

To match the bundled app's behavior, build `CrawlerConfig` and `PageConfig`, create
a `ContentExtractor` and `FileWriter` from that page config, then run `SiteCrawler`
with the same optional integration hooks the Streamlit adapter uses: `output_base`,
`session_id`, `progress_callback`, and `should_cancel`. Your UI can render progress
from the emitted events and serve the generated files afterward, but it should not
reimplement the crawl pipeline or output writer if you want the same result structure.

`SiteCrawler` also writes `progress_history.jsonl` in each crawl root as a
chart-ready cumulative timeline (page limit, discovered pages, successful pages,
failed pages, processed pages, elapsed seconds). UIs can read this file to restore
chart history after page reloads.

## Example adapter setup

```python
from crawl4md import CrawlerConfig, PageConfig, SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter

crawler_config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
page_config = PageConfig(output_extension=".md")

extractor = ContentExtractor(page_config)
writer = FileWriter(
    max_file_size_mb=page_config.max_file_size_mb,
    file_extension=page_config.output_extension,
)

crawler = SiteCrawler(
    crawler_config,
    page_config,
    output_base="outputs/my_ui/session_123/crawl_001",
    session_id="session_123",
    extractor=extractor,
    writer=writer,
    progress_callback=lambda event: print(event),
    should_cancel=lambda: False,
)

results = crawler.crawl()
```

`crawl4md` is a Python library, so a browser-only frontend cannot run it directly.
A different frontend stack needs a Python service, worker, or desktop shell to call
the library.

## Adding vector indexing to your UI

The same pattern applies to Step 2: call the `vector_indexer` library from your
backend. Build an `IndexingConfig`, then run `VectorIndexer.run(config, inputs,
output_base, progress_callback=..., should_cancel=...)`. It returns a structured
`IndexingResult` and writes a ChromaDB index plus a `manifest.json`. The embedding
provider and vector store sit behind interfaces, so you can swap either without
changing your UI. See [src/vector_indexer/README.md](../src/vector_indexer/README.md).
