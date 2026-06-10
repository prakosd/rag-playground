---
description: "Use when editing the Streamlit app, Streamlit support helpers, or their tests. Covers session isolation, background crawl jobs, progress/cancel events, downloads, and container startup."
applyTo: "apps/streamlit/**"
---

# Streamlit App

Browser UI for users who prefer a form-based crawl workflow instead of the notebook.

## Related Skills

- Before Streamlit app work, read `.agents/skills/developing-with-streamlit/SKILL.md`.
- Load the relevant Streamlit sub-skill from `.agents/skills/` for the specific task, such as layout, session state, performance, CLI, markdown, or design work.

## Constraints

- `apps/streamlit/streamlit_app.py` owns the shared app shell and global Streamlit session state. Keep crawl/job helpers in `apps/streamlit/src/crawl4md_streamlit/support.py`.
- Page modules live under `apps/streamlit/app_pages/`. They must expose `render_page()` and render content-area UI only.
- When a page needs shell-owned callbacks or shared runtime state, pass a small context object from `streamlit_app.py` into the page module instead of importing `streamlit_app.py` from the page module.
- Prefix page-specific session keys with the page id when adding complex state to Steps 2-5, for example `vector_index_*` or `rag_qa_*`.
- `crawl4md_streamlit.support` must not import Streamlit. Keep it pure Python so it stays unit-testable.
- The multipage shell uses native `st.navigation` in `streamlit_app.py`. Keep `crawl4md_streamlit.pages` pure; it owns page metadata only and must not import Streamlit.
- The shared page shell renders the title/subtitle, session controls, language selector, page content, footer, and portfolio modal. Do not duplicate any of these inside page modules.
- App-wide notifications, including progress toasts that should appear on every workflow page, belong in the shared shell rather than individual page modules. Do not call `st.toast()` in `apps/streamlit/app_pages/**`; if a future page needs an app-wide toast, pass a shell-owned callback/context. Keep page-local feedback inline with page content (`st.info`, `st.warning`, `st.success`, or page panels).
- RAG placeholder pages (Steps 3-5) inherit the crawler page shell unchanged; only the page-specific work-area copy differs during the placeholder phase.
- **Step 2 — Build Vector Index** is implemented and mirrors Step 1's shell. The page (`app_pages/vector_index.py`) receives a `VectorIndexPageContext` from the shell and only collects form input and calls callbacks. Indexing logic lives in the UI-independent `vector_indexer` library; the background job lives in `vector_index_jobs.py` (mirrors `crawl_jobs.py` — thread + event queue + cooperative cancel). Do not put indexing business logic in the app.
  - Prefix Step 2 session keys with `vector_index_` and keep them separate from crawl keys. Reuse the Step 1 start/stop confirmation-dialog pattern with its own handler and `vector_stop_*` button keys; do not modify `crawl_jobs.py` or the crawl stop handler.
  - Reuse the existing output-files display (`_render_downloads`) and the form action buttons (`crawl_action_buttons`); the form lives in `vector_form_ui.py` with pure, testable option/validation helpers (`crawl_result_options`, `has_index_inputs`).
  - Vector outputs are written under `outputs/streamlit_sessions/session_<id>/vector_<id>/<timestamp>/`. Build the base with `session_manager.prepare_vector_output_base`; discover crawl inputs with `artifact_store.crawl_results.list_crawl_result_files`.
- Keep `session_id` and `crawl_id` separate. Browser sessions write under `outputs/streamlit_sessions/session_<id>/crawl_<id>/`.
- All file access for generated outputs must stay inside the session root. Use the existing path validation helpers instead of manual string checks.
- Background crawls should use `start_crawl_job()` and communicate through queue events. Do not block Streamlit reruns while a crawl is active.
- Cancellation must stay cooperative through `SiteCrawler.should_cancel`; do not terminate threads forcibly.
- Progress UI should consume crawler event mappings and helper estimates. Keep event keys stable unless tests and Streamlit consumers are updated together.
- Downloads should come from the generated-file listing helper and respect the app download-size guard.
- The dev container starts Streamlit on attach at `0.0.0.0:8501`. If the port or startup command changes, update `.devcontainer/devcontainer.json`, `README.md`, and `devcontainer.instructions.md` together.
- Tests must use `tmp_path` and mocked/stubbed crawl jobs. Never make real network requests from Streamlit tests.
- Streamlit tests follow the Streamlit Tests policy in [tests.instructions.md](./tests.instructions.md).
- **Translation catalog:** Whenever new user-facing text is added to the Streamlit UI, add both an English and an Indonesian entry to the `apps/streamlit/src/crawl4md_streamlit/i18n/` package first — `en.py` and `id.py` — then reference the key via `get_strings()` in the UI code. Never hardcode text directly in Streamlit components. To add a new language, create a new `<code>.py` file in the package and register it in `__init__.py`.
- **Load Session dialog:** The 📁 button in `streamlit_app.py` (`_load_session_dialog`) lets users paste a session ID to restore access from another browser or device. Session IDs are validated with `validate_safe_id()` before any server-side path is constructed. `touch_session()` must be called after a successful load to reset the 7-day retention clock. The dialog must stay disabled while a crawl is running.