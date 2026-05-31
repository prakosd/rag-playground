---
description: "Use when editing the Streamlit app, Streamlit support helpers, or their tests. Covers session isolation, background crawl jobs, progress/cancel events, downloads, and container startup."
applyTo: "apps/streamlit/streamlit_app.py, apps/streamlit/app_pages/**, apps/streamlit/src/crawl4md_streamlit/support.py, apps/streamlit/src/crawl4md_streamlit/controls.py, apps/streamlit/src/crawl4md_streamlit/crawl_jobs.py, apps/streamlit/src/crawl4md_streamlit/form_defaults.py, apps/streamlit/src/crawl4md_streamlit/form_ui.py, apps/streamlit/src/crawl4md_streamlit/generated_files.py, apps/streamlit/src/crawl4md_streamlit/pages.py, apps/streamlit/src/crawl4md_streamlit/session_manager.py, apps/streamlit/src/crawl4md_streamlit/i18n/**, apps/streamlit/tests/**"
---

# Streamlit App

Browser UI for users who prefer a form-based crawl workflow instead of the notebook.

## Related Skills

- Before Streamlit app work, read `.agents/skills/developing-with-streamlit/SKILL.md`.
- Load the relevant Streamlit sub-skill from `.agents/skills/` for the specific task, such as layout, session state, performance, CLI, markdown, or design work.

## Constraints

- `apps/streamlit/streamlit_app.py` owns the shared app shell and global Streamlit session state. Keep crawl/job helpers in `apps/streamlit/src/crawl4md_streamlit/support.py`.
- Page modules live under `apps/streamlit/app_pages/`. They must expose `render_page()` and render content-area UI only. Do not duplicate the shared title/subtitle, session controls, language selector, footer, or portfolio modal inside page modules.
- When a page needs shell-owned callbacks or shared runtime state, pass a small context object from `streamlit_app.py` into the page module instead of importing `streamlit_app.py` from the page module.
- Prefix page-specific session keys with the page id when adding complex state to Steps 2-5, for example `vector_index_*` or `rag_qa_*`.
- `crawl4md_streamlit.support` must not import Streamlit. Keep it pure Python so it stays unit-testable.
- The multipage shell uses native `st.navigation` in `streamlit_app.py`. Keep `crawl4md_streamlit.pages` pure; it owns page metadata only and must not import Streamlit.
- The shared page shell renders the active title/subtitle, session controls, language selector, page content, footer, and portfolio modal. Do not duplicate session controls or the footer inside individual pages.
- App-wide notifications, including progress toasts that should appear on every workflow page, belong in the shared shell rather than individual page modules. Do not call `st.toast()` in `apps/streamlit/app_pages/**`; if a future page needs an app-wide toast, pass a shell-owned callback/context. Keep page-local feedback inline with page content (`st.info`, `st.warning`, `st.success`, or page panels).
- RAG placeholder pages (Steps 2-5) must visually inherit the crawler page shell: same page width, title/subtitle placement, session-control row, language selector position, footer placement, spacing, and Streamlit-native styling. During the placeholder phase, only the page-specific work-area copy should change.
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
- **Load Session dialog:** The 📁 button in `streamlit_app.py` (`_load_session_dialog`) lets users paste a session ID to restore access from another browser or device. Session IDs are validated with `validate_safe_id()` before any server-side path is constructed. `touch_session()` must be called after a successful load to reset the 7-day retention clock. The dialog must stay disabled while a crawl is running.