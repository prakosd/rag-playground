---
description: "Use when editing ContentExtractor in src/crawl4md/extractor.py or its tests (extractor, items, links, product, supplementary). Covers trafilatura/markdownify modes, pre-processing rules, and mdformat validation."
applyTo: "src/crawl4md/extractor.py, tests/test_extractor.py, tests/test_extractor_items.py, tests/test_extractor_links.py, tests/test_extractor_product.py, tests/test_extractor_supplementary.py"
---

# ContentExtractor

Converts HTML to Markdown. Modes: trafilatura (default, `extract_main_content=True`) with markdownify fallback; markdownify-only; binary-document mode (`is_pdf=True` / `is_docx=True` → shared `_extract_document_page`, which skips HTML preprocessing since the Markdown was already produced by the matching downloader).

## Constraints

- Pre-processing always runs (tag filtering, strikethrough preservation, heading spacing, empty link population, item separation, table fixing).
- `_populate_empty_links()` has no config flag.
- `_insert_item_separators()` uses `_ITEM_SENTINEL` that must survive trafilatura extraction.
- Supplementary section and product metadata recovery in trafilatura mode only.
- mdformat validation falls back to original if any content is lost.
