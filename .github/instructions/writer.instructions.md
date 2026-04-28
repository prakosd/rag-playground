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
