# Streamlit App — Developer Guide

A browser-based UI for the `crawl4md` library. Non-technical users fill in a form, click
**Start**, watch live progress, and download their Markdown files. This guide explains how
the code is organised, how the pieces connect, and where to look when extending or debugging.

---

## File Map

```text
apps/streamlit/
├── streamlit_app.py                  # UI entry point — one Streamlit page
├── pyproject.toml                    # Package definition and dependencies
├── .streamlit/config.toml            # Server address (0.0.0.0:8501) and theme
├── src/crawl4md_streamlit/
│   ├── __init__.py                   # Empty — marks this as an installable package
│   ├── controls.py                   # Button definitions and state → button mapping
│   ├── crawl_jobs.py                 # Background crawl jobs, config, progress helpers
│   ├── form_defaults.py              # Default crawl form values and option constants
│   ├── form_ui.py                    # Streamlit crawl settings form renderer
│   ├── generated_files.py            # Session-scoped output listing and previews
│   ├── session_manager.py            # Safe IDs, session records, paths, cleanup
│   └── support.py                    # Compatibility exports for app support helpers
└── tests/
    ├── test_app_smoke.py             # App import/startup and preview CSS smoke coverage
    ├── test_controls.py              # Action-button logic for each crawl state
    ├── test_form_defaults.py         # Default form payload
    ├── test_generated_files.py       # Download-tree helper logic
    ├── test_support.py               # Jobs, path helpers, cleanup, progress estimation
    ├── test_support_facade.py        # Compatibility exports from split helper modules
    └── test_streamlit_boundaries.py  # Streamlit config and import-boundary checks
```

### Why a separate package?

`crawl4md_streamlit` (`src/crawl4md_streamlit/`) is installed as a proper Python package
(`pip install -e "apps/streamlit"`). This lets the helpers in `support.py`, `crawl_jobs.py`,
`form_defaults.py`, `generated_files.py`, `session_manager.py`, and `controls.py` be imported and unit-tested
independently of Streamlit — no Streamlit runtime needed in tests.
Streamlit imports are limited to UI modules such as `streamlit_app.py` and `form_ui.py`.

This package is a reference adapter over the core `crawl4md` library, not a second crawl engine.
The library owns crawling, extraction, file writing, sorted and final outputs, run metadata,
progress events, and cooperative cancellation hooks. The Streamlit package owns form rendering,
browser-session persistence, background thread orchestration, and generated-file presentation.
If a feature is UI-agnostic and needed by other frontends, add it to the core library instead of
reimplementing it here.

---

## Component Responsibilities

### `streamlit_app.py` — UI shell

Everything the user sees and interacts with. Responsibilities:

- Initialises `st.session_state` keys on first load (`_init_state`).
- Hydrates browser-local session records through the inline CCv2 localStorage bridge.
- Renders the selected session ID, searchable session selector, create-session button, and language selector.
- Renders the settings form (`render_crawl_form`) and action buttons (delegated to `controls.py`).
- Translates button presses into job start / stop calls.
- Drains background-thread events every Streamlit rerun and maps them to UI state
  (`_drain_job_events`).
- Renders progress metrics and the activity log (`_render_live_area`, refreshed every 3 seconds
  via `@st.fragment(run_every="3s")`).
- Renders the selected session's generated-file table and a per-file download + preview tree separately
  (`_render_downloads`, refreshed every 7 seconds).
- Runs a one-time startup cleanup of old session folders (`_run_startup_cleanup`, cached with
  `@st.cache_resource`).

### `controls.py` — button definitions

Pure logic; no Streamlit imports. `crawl_action_buttons(state, ...)` returns a tuple of
`CrawlActionButton` dataclasses describing which buttons to show, their labels, icons, and
disabled state. `streamlit_app.py` iterates the tuple and renders each one inside a
`st.form_submit_button`.

This separation makes it easy to unit-test state-machine transitions without needing a
Streamlit environment.

### `form_defaults.py` and `form_ui.py` — crawl settings

`form_defaults.py` is pure Python and owns the default crawl settings used when the form first
loads or resets after a terminal crawl state. `form_ui.py` is a UI module: it imports Streamlit,
renders the crawl settings form, and returns the submitted values to `streamlit_app.py`.

`streamlit_app.py` still owns `st.session_state`; it passes the active strings, defaults, and
disabled state into `render_crawl_form()`.

### `support.py` — compatibility exports

No Streamlit imports. Keeps the existing `crawl4md_streamlit.support` import surface stable while
delegating implementation to smaller pure-Python modules:

| Group | Functions |
| --- | --- |
| **`session_manager.py`** | `SessionRecord`, ID generation, session serialization, safe paths, session cleanup |
| **`generated_files.py`** | `GeneratedFile`, `TextPreview`, output listing, download-tree building, activity-log lookup, text previews |
| **`crawl_jobs.py`** | `CrawlJob`, config building, progress estimates, crawl-thread lifecycle, event mapping |

New code can import from the focused module directly. Existing code may continue importing from
`support.py`.

---

## Event / State Lifecycle

Each crawl runs in a **background daemon thread**. The thread communicates with the UI through
a `queue.Queue[dict]` (the `CrawlJob.events` field). Events are drained on every Streamlit
rerun by `_drain_job_events`.

```text
Background thread                    st.session_state.job_state
──────────────────                   ──────────────────────────
starts          → emits "started"  → "running"
page done       → emits "page_processed" (no state change)
stop signal     → emits "cancel_requested" → "cancel_requested"
thread ends     → emits "cancelled"  → "stopped"
thread ends     → emits "completed" → "completed"
thread ends     → emits "failed"   → "failed"
```

Full `job_state` values and the transitions that produce them:

| State | What triggered it |
| --- | --- |
| `idle` | App first load |
| `running` | User clicked **Start** |
| `cancel_requested` | User clicked **Stop** while running |
| `stopped` | Thread confirmed cancellation after a Stop request |
| `completed` | Thread finished all pages successfully |
| `failed` | Thread threw an unhandled exception |

---

## Start / Stop Sequence

```text
Initial load
  └─ job_state = "idle"
     Start is enabled; settings are editable

User clicks Start
  └─ _start_job(values)
       calls build_configs(values)
       creates a fresh crawl_id
       calls start_crawl_job(...)
       job_state = "running"
       settings are disabled and the visible action is Stop

User clicks Stop
  └─ _stop_job()
       sets job_state = "cancel_requested"
       calls request_cancel(job)   ← sets cancel_event + queues "cancel_requested"
       background thread sees cancel_event, finishes current page, emits "cancelled"
  └─ _drain_job_events() maps "cancelled" to "stopped"
       clears the active job
       resets form defaults
       keeps active_output_dir so generated files stay visible

User clicks Start again
  └─ creates a new crawl_id and starts from the beginning
```

Stop is cooperative: the worker is not force-killed. `SiteCrawler` owns sidecars and final
output regeneration so completed pages are still written into the final output folder. The
app does not persist crawl state and does not load any previous crawl when starting again.

---

## Session and Path Safety

Each browser stores known session IDs and UTC creation times in localStorage under a versioned
`crawl4md` key. The app reads those records through a small inline `st.components.v2` bridge,
validates them server-side, and selects the newest valid session on page load. If localStorage
has no valid sessions, the server creates one safe ID, sends it back to the bridge for storage,
and selects it. Users can switch sessions with the searchable `st.selectbox()` or create a new
session with the adjacent button.

All output lives inside:

```text
outputs/streamlit_sessions/
└── session_{session_id}/          ← one folder per browser tab / session
    └── crawl_{crawl_id}/          ← one folder per Start click
        └── {timestamped-dir}/     ← created by SiteCrawler inside the crawl_id folder
```

`ensure_within_root(root, path)` is called before every file read or listing. It resolves
both paths and raises `ValueError` if `path` escapes `root`. This prevents path-traversal
attacks when any server-generated path is forwarded back into a file read. Browser-provided
session records are treated as untrusted input and filtered through `validate_safe_id()` before
they can affect any server-side path.

`validate_safe_id(id)` enforces that IDs only contain `[a-z0-9_-]` before they are
interpolated into directory names.

Session folders older than 7 days are removed by `cleanup_old_sessions_with_lock` after browser
session hydration (using a `.cleanup.lock` file so only one Streamlit worker runs the cleanup).
Session IDs known to the browser are passed as active IDs so the selector does not point to
folders removed during the same startup.

---

## Data Flow (one crawl from click to download)

```text
User fills form and clicks Start
  │
  ▼
render_crawl_form()     collects raw form values into a dict
  │
  ▼
build_configs()         validates and converts to CrawlerConfig + PageConfig
  │
  ▼
start_crawl_job()       creates output dirs, spawns background thread
  │                     thread: SiteCrawler.crawl() → extractor → writer
  │                     emits progress events to job.events queue
  │
  ▼ (live area every 3 s; downloads every 7 s, via @st.fragment)
_drain_job_events()     dequeues events, updates st.session_state
  │
  ▼
_render_status()        progress bar, metrics, current URL, elapsed time
_render_activity_log()  tail of activity_log.txt from the output dir
_render_downloads()     dataframe + download/preview buttons for the selected session
```

---

## Testing Map

| Test file | What it covers |
| --- | --- |
| `tests/test_controls.py` | Every `job_state` value → correct buttons (label, disabled, type) |
| `tests/test_form_defaults.py` | Default crawl form payload and independent dict creation |
| `tests/test_generated_files.py` | Pure generated-file tree building for nested downloads |
| `tests/test_support.py` | ID safety, browser session records, path helpers, file listing, session cleanup, progress, job start/stop with a fake `SiteCrawler` |
| `tests/test_support_facade.py` | Compatibility exports from the split helper modules |
| `tests/test_app_smoke.py` | App import/startup smoke coverage and preview CSS guardrails |
| `tests/test_streamlit_boundaries.py` | `.streamlit/config.toml` sets the right address and port; no config leaks to repo root; helper package stays Streamlit-free |

Tests mock `SiteCrawler` — no real network calls are made. The split between `streamlit_app.py`
(Streamlit imports) and the pure helper modules is what makes pure-Python testing possible.

---

## Common Extension Points

| Task | Where to look |
| --- | --- |
| Add a new form field | `render_crawl_form()` in `form_ui.py` + `default_form_values()` in `form_defaults.py` + `build_configs()` in `crawl_jobs.py` |
| Change action buttons or states | `controls.py` (`CrawlActionButton`, `crawl_action_buttons`) + `test_controls.py` |
| Add a new event type from the crawler | `job_state_from_event()` in `crawl_jobs.py` + `_drain_job_events()` in `streamlit_app.py` |
| Add a new output panel | A new `_render_*` function in `streamlit_app.py`; use `_render_live_area` for crawl-status panels and a separate fragment for selected-session downloads |
| Change retention or cleanup logic | `cleanup_old_sessions()` in `session_manager.py` + `test_support.py` |
| Change the server port or theme | `apps/streamlit/.streamlit/config.toml` |

---

## Running Locally

```bash
# From the repo root — install both packages (core + app):
pip install -e ".[dev]" -e "apps/streamlit[dev]"

# Run the app (from the apps/streamlit directory so config.toml is picked up):
cd apps/streamlit && streamlit run streamlit_app.py

# Or explicitly from the repo root:
python -m streamlit run apps/streamlit/streamlit_app.py --server.address=0.0.0.0 --server.port=8501
```

```bash
# Tests and lint:
python -m pytest apps/streamlit/tests/ -q
python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/src/ apps/streamlit/tests/
```
