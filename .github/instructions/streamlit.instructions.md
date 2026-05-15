---
description: "Use when editing the Streamlit app, Streamlit support helpers, or their tests. Covers session isolation, background crawl jobs, progress/cancel events, downloads, and container startup."
applyTo: "apps/streamlit/streamlit_app.py, apps/streamlit/src/crawl4md_streamlit/support.py, apps/streamlit/src/crawl4md_streamlit/controls.py, apps/streamlit/src/crawl4md_streamlit/i18n/**, apps/streamlit/tests/**"
---

# Streamlit App

Browser UI for users who prefer a form-based crawl workflow instead of the notebook.

## Related Skills

- Before Streamlit app work, read `.agents/skills/developing-with-streamlit/SKILL.md`.
- Load the relevant Streamlit sub-skill from `.agents/skills/` for the specific task, such as layout, session state, performance, CLI, markdown, or design work.

## Constraints

- `apps/streamlit/streamlit_app.py` owns UI rendering and Streamlit session state. Keep crawl/job helpers in `apps/streamlit/src/crawl4md_streamlit/support.py`.
- `crawl4md_streamlit.support` must not import Streamlit. Keep it pure Python so it stays unit-testable.
- Keep `session_id` and `crawl_id` separate. Browser sessions write under `outputs/streamlit_sessions/session_<id>/crawl_<id>/`.
- All file access for generated outputs must stay inside the session root. Use the existing path validation helpers instead of manual string checks.
- Background crawls should use `start_crawl_job()` and communicate through queue events. Do not block Streamlit reruns while a crawl is active.
- Cancellation must stay cooperative through `SiteCrawler.should_cancel`; do not terminate threads forcibly.
- Progress UI should consume crawler event mappings and helper estimates. Keep event keys stable unless tests and Streamlit consumers are updated together.
- Downloads should come from the generated-file listing helper and respect the app download-size guard.
- The dev container starts Streamlit on attach at `0.0.0.0:8501`. If the port or startup command changes, update `.devcontainer/devcontainer.json`, `README.md`, and `devcontainer.instructions.md` together.
- Tests must use `tmp_path` and mocked/stubbed crawl jobs. Never make real network requests from Streamlit tests.
- Streamlit tests must follow the `## Streamlit Tests (apps/streamlit/**)` policy in `tests.instructions.md`: test business logic, integration behavior, critical workflows, and startup smoke coverage; do not test static rendering, cosmetic details, individual widget existence, or Streamlit framework behavior.
- **Translation catalog:** Whenever new user-facing text is added to the Streamlit UI, add both an English and an Indonesian entry to the `apps/streamlit/src/crawl4md_streamlit/i18n/` package first — `en.py` and `id.py` — then reference the key via `get_strings()` in the UI code. Never hardcode text directly in Streamlit components. To add a new language, create a new `<code>.py` file in the package and register it in `__init__.py`.