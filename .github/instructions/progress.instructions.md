---
description: "Use when editing ProgressReporter in src/crawl4md/progress.py or its tests. Covers Jupyter widget rules and Colab sanitizer constraints."
applyTo: "src/crawl4md/progress.py, tests/test_progress.py"
---

# ProgressReporter

Auto-detects Jupyter vs terminal. Jupyter widget uses `_repr_html_()` — all CSS classes prefixed `c4md-`. Colors live in `_LIGHT_COLORS` / `_DARK_COLORS` with dark-mode media queries.

## Colab constraints

`_repr_html_colab()` uses inline `style="..."` only — no `<style>` blocks, no `@keyframes`, no `position: absolute`, no `filter`, no `animation`. All of these are stripped by Colab's sanitizer.
