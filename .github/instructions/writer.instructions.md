---
description: "Use when editing FileWriter in src/crawl4md/writer.py or its tests. Covers batch vs incremental modes, oversized-page handling, and output file naming."
applyTo: "src/crawl4md/writer.py, src/crawl4md/sorter.py, tests/test_writer.py, tests/test_sorter.py"
---

# FileWriter & ContentSorter

## FileWriter constraints

- Both batch (`write()`) and incremental (`add()` / `flush()` / `reset()`) modes must be maintained.
- Oversized pages get their own file with `UserWarning`.
- Symmetric `_fail_writer` for failed pages.
- Extension comes from `PageConfig.output_extension`.
- **Page source markers.** `_format_page` wraps each page's human-readable header (the `# title` heading and `*Source: <url>*` line) in render-invisible HTML-comment markers `_PAGE_HEADER_START_MARKER` (`<!-- crawl4md:source -->`) and `_PAGE_HEADER_END_MARKER` (`<!-- /crawl4md:source -->`). They let `vector_indexer` recover a page's source and drop the header from indexed chunks while humans still see the heading. The two marker strings are duplicated in `vector_indexer.page_source` with a "keep in sync" comment — do not change one without the other, and do not add a cross-library import. `test_writer.py` asserts the markers bracket each page header and that the leading front matter is still written once.

## Output file naming

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
