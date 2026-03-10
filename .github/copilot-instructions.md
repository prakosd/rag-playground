# Copilot Instructions — crawl4md

## Project Overview

crawl4md is a Python library for crawling websites and extracting content as Markdown-formatted text files. It wraps Crawl4AI with a synchronous API designed for non-technical Jupyter Notebook users.

## Data Flow

```
SiteCrawler.crawl()
  ├─ Crawl4AI (async) → CrawlResult (raw HTML per page)
  ├─ ContentExtractor  → ExtractedPage (clean Markdown per page)
  ├─ FileWriter         → size-limited content files + URL lists
  └─ ContentSorter      → sorted final files grouped by URL path
```

Each crawl creates a timestamped output directory. Results pass through multiple rounds (initial + retries), then are merged, deduplicated, and sorted.

## Architecture

### Config models (`config.py`)

Pydantic v2 models — all user-facing parameters are validated here.

- **CrawlerConfig** — `urls`, `exclude_paths`, `include_only_paths`, `limit`, `max_depth`, `flush_interval`, `delay`, `stealth`, `headers`, `max_retries`. Accepts CSV strings for list fields; validates regex patterns. `stealth` defaults to `True` (enables random UA, navigator override, full-page scroll). `headers` is a free-form `dict[str, str]` forwarded to `BrowserConfig`.
- **PageConfig** — `exclude_tags`, `include_only_tags`, `wait_for`, `timeout`, `max_file_size_mb`, `extract_main_content`, `output_extension`, `separate_items`, `item_selector`, `js_code`, `scan_full_page`, `scroll_delay`. Cannot set both `exclude_tags` and `include_only_tags`. `separate_items` defaults to `True` (auto-detects and separates repeated items). `scan_full_page` (default `True`) scrolls through the page before extraction; `scroll_delay` (default `0.4`) controls pause between scroll steps.
- **CrawlResult** — per-page output: `url`, `html`, `markdown`, `success`, `error`, `redirected_url`.
- **ExtractedPage** — post-extraction output: `url`, `title`, `markdown`.

### SiteCrawler (`crawler.py`)

Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter compatibility; on Windows uses `ProactorEventLoop` in a `ThreadPoolExecutor`.

Constructor accepts an optional keyword argument `activity_log_size` (default `10`) that controls how many recent activities are shown in the Jupyter progress widget's activity log.

**Multi-round strategy:**

1. **Round 1** — crawl seed URLs with link discovery (respects `max_depth`). Discovered links are added to the queue up to `config.limit`. When `delay > 0`, a light per-page jitter (`delay × 0.1–1.0`) is applied; when `delay` is 0 (default) no per-page delay is used.
2. **Rounds 2+** — retry failed URLs with link discovery enabled. Pages that now succeed have their links discovered and crawled within the same round (respecting `max_depth` and `limit`). A `_ROUND_COOLDOWN` (30 s, jittered ×0.8–1.5) pause between rounds lets WAFs cool down. Per-page `delay` (with jitter 0.3x–3.0x) is applied during these retry rounds.
3. **WAF back-off** — when a WAF block is detected, an immediate back-off sleep fires (`max(_WAF_BACKOFF_FLOOR, delay × 2.0–5.0)`). After `_WAF_CONSECUTIVE_THRESHOLD` (3) consecutive blocks the delay escalates to `_WAF_BACKOFF_CAP` (15 s). This applies even when `delay=0`.
4. **Cross-round state** — `all_generated` (set of all URLs ever queued) and `url_depths` (URL → depth map) are shared across rounds for correct dedup, limit enforcement, and depth tracking.
5. **Early exit** — skip remaining retries if all pages succeed.
6. **Session persistence** — a single `AsyncWebCrawler` instance is shared across all rounds so cookies (including WAF challenge tokens) persist through retries.

**WAF detection (two-stage):**

- `_is_blocked(html)` — checks raw HTML against `_BLOCK_SIGNATURES` (Incapsula, Cloudflare, "access denied", "javascript is required", etc.).
- Post-extraction check — if block signature is present AND extracted markdown < `_BLOCK_MAX_CONTENT_LENGTH` (500 chars), the page is demoted to failed and queued for retry.
- `_content_length_without_chrome()` strips boilerplate tags (nav, script, style, form, header, footer, noscript) before measuring text length.

**URL filtering:**

- Must match seed domain(s) (with `www.` stripping).
- Skips `_BOILERPLATE_DOMAINS` (`browsehappy.com`, `google.com`).
- Skips `_STATIC_ASSET_EXTENSIONS` (CSS, JS, images, media, archives).
- Applies `include_only_paths` / `exclude_paths` regex filters.
- Template placeholders (`{{`, `{%`) in hrefs are skipped.

**Redirect handling:** Uses Crawl4AI's `redirected_url`; deduplicates against already-visited URLs; stores final URL in `CrawlResult.redirected_url`.

### ContentExtractor (`extractor.py`)

Converts crawled HTML to Markdown. Two extraction modes controlled by `PageConfig.extract_main_content`:

- **`True` (default)** — trafilatura (strips boilerplate). Falls back to markdownify if trafilatura coverage < `_COVERAGE_THRESHOLD` (15% of visible text).
- **`False`** — markdownify on full HTML.

**Pre-processing (before extraction):**

- `_filter_tags()` — apply `exclude_tags` / `include_only_tags` via HTMLParser.
- `_preserve_strikethrough()` — convert `<del>/<s>/<strike>` → `~~text~~` so strikethrough survives extraction.
- `_space_heading_children()` — insert whitespace between adjacent inline Tag children in `<h1>`–`<h6>` elements to prevent text concatenation (e.g. `<span>Broadband</span><span>For seamless</span>` → `Broadband For seamless`).
- `_populate_empty_links()` — find `<a>` tags with `href` but no text content and populate them with visible link text derived from: `title` attr → `aria-label` attr → URL path slug → `"Link"`. Skips `href="#"`, `javascript:`, and empty strings. Always-on, no config flag. **Overlay relocation:** when the populated anchor has no child elements and its parent's other children have ≥ 30 chars of combined text, the anchor is moved to the *end* of its parent so card content appears before the reference link.
- `_insert_item_separators()` — if `separate_items` is enabled (default `True`), insert sentinel markers (`_ITEM_SENTINEL`) between repeated structural elements. Auto-detection via `_find_repeated_items()` returns **all** qualifying groups (≥ 3 same-signature siblings with ≥ 20 chars each), deduplicated by item overlap and sorted by descending score. Each group is expanded via `_include_interstitial_siblings()`. When `item_selector` CSS is provided, only that single group is used.
- `_fix_markdown_tables()` — normalize colspan/rowspan, fix missing separator rows, equalize column counts.

**Supplementary section recovery (trafilatura mode only):**

Trafilatura strips non-main-content sections. The extractor recovers them via `_extract_supplementary_sections()`:

1. JSON-LD `FAQPage` schema.
2. HTML5 `<details>`/`<summary>` groups (≥ 3 siblings).
3. CSS class/ID matching ("faq", "accordion", "q-and-a", etc.).
4. `<h2>`–`<h4>` headings containing "FAQ" / "Frequently Asked".

**Product metadata extraction** (`_extract_product_header()`):

Checked in order: JSON-LD `@type: Product` → Open Graph `product:price:amount` → DOM fallback (strikethrough price detection). Returns `{name, brand, price, high_price}` or `None`.

**Post-processing pipeline** (`_clean_markdown()`, applied in order):

1. `_strip_template_variables()` — remove leaked SPA/OutSystems vars (`Var_*`, `In_*`, `isOutOfStock`, etc.).
2. `_collapse_blank_lines()` — reduce 3+ consecutive blank lines to 1.
3. `_dedup_paragraphs()` — remove consecutive duplicate paragraphs.
4. `_reformat_separated_items()` — convert `---`-delimited product sections to structured bullet lists (≥ 3 separators).
5. `_compact_product_listings()` — auto-detect 3+ consecutive product-name/price pairs and reformat as bullet lists with badges.
6. `_promote_section_labels()` — short standalone lines before content become `###` headings.
7. `_compact_short_paragraphs()` — runs of 3+ short single-line paragraphs become bullet lists.

**Markdown validation:** Each page is formatted with mdformat (GFM extensions). A content-preservation guard compares tokens before/after; falls back to original text if any content was lost.

**Title extraction** (5-source fallback): `<title>` → `og:title` → `<h1>` → URL slug → generic fallback. Generic titles ("Home", "Product PLP", etc.) are filtered out.

### ContentSorter (`sorter.py`)

Groups extracted pages by URL path for natural display order. Sorts lexicographically by path segments; stable sort preserves crawl order for pages with identical paths.

### FileWriter (`writer.py`)

Combines extracted pages into size-limited output files (`.txt` or `.md`, configurable via `PageConfig.output_extension`). Never splits a single page across files. Oversized pages get their own file with a `UserWarning`.

- **Batch mode:** `write(pages, output_dir, max_file_size_mb)` — all at once.
- **Incremental mode:** `add(page)` buffers; `flush()` writes. `reset(prefix)` starts a new round.

A symmetric `_fail_writer` handles failed-page output (error details + raw HTML).

### ProgressReporter (`progress.py`)

Real-time progress display. Auto-detects Jupyter (HTML widget with animated spider + activity log) vs terminal (plain text with ETA). Tracks success/fail counts across rounds via `prior_success`/`prior_fail`.

**Environment detection:** `_in_notebook()` checks the IPython shell class name against `_NOTEBOOK_SHELL_NAMES` (`"ZMQInteractiveShell"` for standard Jupyter, `"Shell"` for Google Colab). `_in_colab()` checks `"google.colab" in sys.modules`. The reporter stores `_use_notebook` (enables HTML widget) and `_use_colab` (enables Colab-safe rendering).

**Activity tracking:** `set_activity(label)` records what the crawler is currently doing (crawling, extracting, flushing, delay, discovering links). Each activity's duration and completion timestamp are captured and shown in a recent-activity log (last 10 entries by default, configurable via `activity_log_size`). Activity log entries are 3-element tuples `(datetime, label, duration)`. The crawler instruments `_crawl_urls_async` with `set_activity()` calls at key phases. Additionally, `update_activity_label(label)` can rename the current activity without closing it (timer keeps running), used to update "Discovering links" with the final link count after extraction.

**Jupyter widget (`_ProgressWidget`):** Renders a rich HTML display via `_repr_html_()` with a gradient progress bar, an animated CSS spider (🕷️) that crawls back and forth near the leading edge of the bar, a spider web SVG decoration at the top-left corner of the bar, a pulsating glow overlay on the filled bar portion, a pulsing current-activity indicator with start timestamp, estimated finish time, and estimated duration (based on average duration of same-category completed activities), an "Activity Log" heading above a compact activity log table with HH:MM:SS timestamps (failed URLs are marked with ❌ in red), and cumulative stats + ETA. All CSS is scoped with `c4md-` prefixed class names. A `@media (prefers-color-scheme: dark)` block overrides text/background colors for dark-mode environments (VS Code, JupyterLab).

**Color palettes:** All widget colors are centralised in two module-level dicts — `_LIGHT_COLORS` and `_DARK_COLORS` — with named keys for each color role (`text`, `header`, `bar_bg`, `bar_gradient`, `activity`, `pulse`, `duration`, `log_heading`, `log_text`, `log_time`, `log_dur`, `log_fail`, `footer`, `pct`, `thread`, `web`, `bar_glow`). The standard Jupyter CSS uses `_LIGHT_COLORS` as defaults and `_DARK_COLORS` inside `@media (prefers-color-scheme: dark)`. The Colab rendering path selects between the two palettes at render time based on the `dark` flag.

**Google Colab compatibility:** When `colab=True`, `_repr_html_()` delegates to `_repr_html_colab()` which renders the same information using only inline `style="..."` attributes — no `<style>` block, no `@keyframes`, no `position: absolute`, no `filter`, no `animation`. This avoids Colab's HTML sanitizer stripping the widget. The spider emoji tracks the progress bar via a `<table>` layout (first cell width set to progress percentage, spider right-aligned inside it). A dashed web-thread `<div>` spans the same width above the bar, mimicking the VS Code animated thread. The spider web SVG decoration uses `margin-bottom: -22px` overlap instead of `position: absolute` to layer over the bar. The bar has a static `box-shadow: inset` glow as a fallback for the animated glow. In Colab mode, `_refresh_display()` uses `display(HTML(widget._repr_html_()))` instead of `display(widget)` to ensure reliable rendering in Colab's output system.

**Colab dark mode:** `_colab_is_dark()` calls `google.colab.output.eval_js()` to read the `data-colab-attr-theme` attribute from the `<html>` element. Returns `True` for dark theme, `False` otherwise (including when the API is unavailable). The result is passed as `dark=True/False` to `_ProgressWidget` from `_build_widget()`, which selects between `_LIGHT_COLORS` and `_DARK_COLORS` for inline style interpolation. Detection runs on each `_refresh_display()` call, so theme changes during a crawl are picked up on the next update.

**`round_label`:** Passed from `_run_rounds_async` to `ProgressReporter` so the widget header shows "Round N/M".

**Backward compatibility:** `set_activity()` is optional — reporters that never call it still produce a valid widget. The `update()` signature is unchanged. Terminal mode is unaffected (plain `print()`).

## Output File Naming

Each crawl creates a timestamped folder (`YYYY-MM-DD_HH-MM-SS`). Files are produced in three tiers:

**Per-round** (written during crawl):

```
round_{N}_success_content_{NNN}.ext   # Extracted Markdown for successful pages
round_{N}_fail_content_{NNN}.ext      # Error details + raw HTML for failed pages
round_{N}_success_urls.txt            # URLs that succeeded this round
round_{N}_fail_urls.txt               # URLs that failed this round
```

**Final merged** (after all rounds, unsorted):

```
final_success_content_{NNN}.ext       # All successful pages merged
final_fail_content_{NNN}.ext          # All failed pages merged
final_success_urls.txt                # All successful URLs (deduplicated)
final_fail_urls.txt                   # URLs that never succeeded
```

**Sorted final** (re-extracted and sorted by URL path):

```
sorted_final_success_content_{NNN}.ext
sorted_final_fail_content_{NNN}.ext
sorted_final_success_urls.txt
sorted_final_fail_urls.txt
```

`{N}` = round number (1-based), `{NNN}` = file index (001, 002, …), `ext` = `PageConfig.output_extension`.

## File Layout

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic config models
├── crawler.py        # SiteCrawler class
├── extractor.py      # ContentExtractor class
├── sorter.py         # ContentSorter class
├── writer.py         # FileWriter class
└── progress.py       # ProgressReporter class
```

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

## Key Constants

| Constant | Module | Value | Notes |
|---|---|---|---|
| `_ROUND_COOLDOWN` | crawler | `30` | Seconds between retry rounds; jittered ×0.8–1.5; patched to 0 in tests via autouse fixture |
| `_JITTER_ROUND1_MIN / _MAX` | crawler | `0.1` / `1.0` | Per-page jitter multiplier range for round 1 (applied to `delay`) |
| `_JITTER_RETRY_MIN / _MAX` | crawler | `0.3` / `3.0` | Per-page jitter multiplier range for retry rounds (applied to `delay`) |
| `_WAF_BACKOFF_MIN / _MAX` | crawler | `2.0` / `5.0` | WAF back-off jitter multiplier range (applied to `delay`) |
| `_WAF_BACKOFF_FLOOR` | crawler | `3.0` | Minimum WAF back-off seconds (ensures pause even when `delay=0`) |
| `_WAF_BACKOFF_CAP` | crawler | `15.0` | Maximum WAF back-off seconds (escalation ceiling) |
| `_WAF_CONSECUTIVE_THRESHOLD` | crawler | `3` | Consecutive WAF blocks before escalating to `_WAF_BACKOFF_CAP` |
| `_ROUND_COOLDOWN_JITTER_MIN / _MAX` | crawler | `0.8` / `1.5` | Round cooldown jitter multiplier range |
| `_BLOCK_SIGNATURES` | crawler | 6 strings | WAF detection keywords (Incapsula, Cloudflare, etc.) |
| `_BLOCK_MAX_CONTENT_LENGTH` | crawler | `500` | Markdown char threshold for block detection |
| `_STATIC_ASSET_EXTENSIONS` | crawler | frozenset | File extensions to skip (CSS, JS, images, media, archives) |
| `_BOILERPLATE_DOMAINS` | crawler | frozenset | Domains to always skip (`browsehappy.com`, `google.com`) |
| `_ITEM_SENTINEL` | extractor | `"CRAWL4MD_ITEM_BREAK"` | Placeholder between repeated items (survives trafilatura) |
| `_COVERAGE_THRESHOLD` | extractor | `0.15` | Trafilatura → markdownify fallback threshold |
| `_MAX_LOG_ENTRIES` | progress | `10` | Maximum recent activities shown in the activity log (default; overridable via `activity_log_size`) |
| `_LIGHT_COLORS` | progress | dict (17 keys) | Light-mode color palette for all widget elements; used as CSS defaults and Colab light inline styles |
| `_DARK_COLORS` | progress | dict (17 keys) | Dark-mode color palette; used in `@media (prefers-color-scheme: dark)` CSS and Colab dark inline styles |

## Testing

- Tests use pytest with mocked HTTP calls — never make real network requests in tests.
- **Every code change must include unit tests** — new features need tests for the happy path and key edge cases; bug fixes need a test that reproduces the bug.
- **All tests must pass before a task is considered complete.** Run `pytest tests/ -v` and confirm zero failures.
- **After tests pass, run linting:** `ruff check src/ tests/` and `ruff format --check src/ tests/`. Fix any errors and re-run both tests and linting until **both pass with zero errors**. A task is not complete until tests AND linting are clean.
- Test files: `test_config.py`, `test_crawler.py`, `test_crawler_output.py`, `test_crawler_retry.py`, `test_extractor.py`, `test_extractor_items.py`, `test_extractor_links.py`, `test_extractor_product.py`, `test_extractor_supplementary.py`, `test_sorter.py`, `test_writer.py`, `test_progress.py`.
- `_ROUND_COOLDOWN` (the 30 s sleep between retry rounds) is globally patched to 0 via an autouse fixture in `conftest.py`. No per-test patching is needed.
- When running tests in a terminal, **always wait for the command to finish and return its full output** before re-running, retrying, or drawing any conclusions. Do not start a new test run while one is still in progress.

## Documentation Sync

For every code change or plan, review `.github/copilot-instructions.md` and `README.md` for accuracy against the change. If either file needs updating (e.g. new/renamed config fields, changed defaults, new modules, altered data flow, new constants, updated dependencies):

- **Plan mode** — include the specific documentation updates as steps in the plan.
- **Agent mode** — make the documentation updates directly alongside the code change.

Common triggers: new or removed config parameters, changed architecture or data flow, new/renamed modules or classes, updated constants or default values, new dependencies, changed output file naming.
