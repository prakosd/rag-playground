# Streamlit App — Developer Guide

A browser-based UI for the `crawl4md` library. Non-technical users fill in a form, click
**Start**, watch live progress, and download their Markdown files. This guide explains how
the code is organised, how the pieces connect, and where to look when extending or debugging.

---

## File Map

```
apps/streamlit/
├── streamlit_app.py                  # UI entry point — one Streamlit page
├── pyproject.toml                    # Package definition and dependencies
├── .streamlit/config.toml            # Server address (0.0.0.0:8501) and theme
├── src/crawl4md_streamlit/
│   ├── __init__.py                   # Empty — marks this as an installable package
│   ├── controls.py                   # Button definitions and state → button mapping
│   └── support.py                    # Background jobs, path safety, session cleanup
└── tests/
    ├── test_controls.py              # Action-button logic for each crawl state
    ├── test_support.py               # Jobs, path helpers, cleanup, progress estimation
    └── test_launcher.py              # Streamlit server config sanity checks
```

### Why a separate package?

`crawl4md_streamlit` (`src/crawl4md_streamlit/`) is installed as a proper Python package
(`pip install -e "apps/streamlit"`). This lets the helpers in `support.py` and `controls.py`
be imported and unit-tested independently of Streamlit — no Streamlit runtime needed in tests.
`streamlit_app.py` is the only file that imports `streamlit`.

---

## Component Responsibilities

### `streamlit_app.py` — UI shell

Everything the user sees and interacts with. Responsibilities:

- Initialises `st.session_state` keys on first load (`_init_state`).
- Renders the settings form (`_form_values`) and action buttons (delegated to `controls.py`).
- Translates button presses into job start / stop calls.
- Drains background-thread events every Streamlit rerun and maps them to UI state
  (`_drain_job_events`).
- Renders progress metrics, the activity log, and the file download table (`_render_live_area`,
  refreshed every 1 second via `@st.fragment(run_every="1s")`).
- Runs a one-time startup cleanup of old session folders (`_run_startup_cleanup`, cached with
  `@st.cache_resource`).

### `controls.py` — button definitions

Pure logic; no Streamlit imports. `crawl_action_buttons(state, ...)` returns a tuple of
`CrawlActionButton` dataclasses describing which buttons to show, their labels, icons, and
disabled state. `streamlit_app.py` iterates the tuple and renders each one inside a
`st.form_submit_button`.

This separation makes it easy to unit-test state-machine transitions without needing a
Streamlit environment.

### `support.py` — background jobs and helpers

No Streamlit imports. Contains everything that would clutter `streamlit_app.py`:

| Group | Functions |
|---|---|
| **ID generation** | `generate_safe_id`, `validate_safe_id`, `generate_crawl_id` |
| **Path helpers** | `session_dir`, `crawl_output_base`, `ensure_within_root` |
| **Directory setup** | `prepare_session_dir`, `prepare_crawl_output_base` |
| **Config building** | `build_configs` (form values → `CrawlerConfig` + `PageConfig`) |
| **Progress** | `estimate_progress` |
| **File listing** | `list_generated_files` (session-scoped, rejects path traversal) |
| **Log reading** | `read_recent_lines` |
| **Crawl jobs** | `start_crawl_job`, `request_cancel`, `drain_events` |
| **State mapping** | `job_state_from_event` |
| **Session cleanup** | `cleanup_old_sessions`, `cleanup_old_sessions_with_lock` |

---

## Event / State Lifecycle

Each crawl runs in a **background daemon thread**. The thread communicates with the UI through
a `queue.Queue[dict]` (the `CrawlJob.events` field). Events are drained on every Streamlit
rerun by `_drain_job_events`.

```
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
|---|---|
| `idle` | App first load |
| `running` | User clicked **Start** |
| `cancel_requested` | User clicked **Stop** while running |
| `stopped` | Thread confirmed cancellation after a Stop request |
| `completed` | Thread finished all pages successfully |
| `failed` | Thread threw an unhandled exception |

---

## Start / Stop Sequence

```
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

Each browser session gets a unique `session_id` (stored in `st.session_state`). All output
lives inside:

```
outputs/streamlit_sessions/
└── session_{session_id}/          ← one folder per browser tab / session
    └── crawl_{crawl_id}/          ← one folder per Start click
        └── {timestamped-dir}/     ← created by SiteCrawler inside the crawl_id folder
```

`ensure_within_root(root, path)` is called before every file read or listing. It resolves
both paths and raises `ValueError` if `path` escapes `root`. This prevents path-traversal
attacks when any server-generated path is forwarded back into a file read.

`validate_safe_id(id)` enforces that IDs only contain `[a-z0-9_-]` before they are
interpolated into directory names.

Session folders older than 7 days are removed by `cleanup_old_sessions_with_lock` at app
startup (using a `.cleanup.lock` file so only one Streamlit worker runs the cleanup).

---

## Data Flow (one crawl from click to download)

```
User fills form and clicks Start
  │
  ▼
_form_values()          collects raw form values into a dict
  │
  ▼
build_configs()         validates and converts to CrawlerConfig + PageConfig
  │
  ▼
start_crawl_job()       creates output dirs, spawns background thread
  │                     thread: SiteCrawler.crawl() → extractor → writer
  │                     emits progress events to job.events queue
  │
  ▼ (every 1 s, via @st.fragment)
_drain_job_events()     dequeues events, updates st.session_state
  │
  ▼
_render_status()        progress bar, metrics, current URL, elapsed time
_render_activity_log()  tail of activity_log.txt from the output dir
_render_files()         dataframe + download buttons for all generated files
```

---

## Testing Map

| Test file | What it covers |
|---|---|
| `tests/test_controls.py` | Every `job_state` value → correct buttons (label, disabled, type) |
| `tests/test_support.py` | ID safety, path helpers, file listing, session cleanup, progress, job start/stop with a fake `SiteCrawler` |
| `tests/test_launcher.py` | `.streamlit/config.toml` sets the right address and port; no config leaks to repo root |

Tests mock `SiteCrawler` — no real network calls are made. The split between `streamlit_app.py`
(Streamlit imports) and `support.py` / `controls.py` (no Streamlit imports) is what makes
pure-Python testing possible.

---

## Common Extension Points

| Task | Where to look |
|---|---|
| Add a new form field | `_form_values()` in `streamlit_app.py` + `build_configs()` in `support.py` |
| Change action buttons or states | `controls.py` (`CrawlActionButton`, `crawl_action_buttons`) + `test_controls.py` |
| Add a new event type from the crawler | `job_state_from_event()` in `support.py` + `_drain_job_events()` in `streamlit_app.py` |
| Add a new output panel | A new `_render_*` function in `streamlit_app.py`, called from `_render_live_area` |
| Change retention or cleanup logic | `cleanup_old_sessions()` in `support.py` + `test_support.py` |
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
