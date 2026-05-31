---
description: "Use when writing or editing tests under tests/ or apps/streamlit/tests/. Covers mocking policy, required coverage per change, app linting, and how to invoke the test-runner agent."
applyTo: "tests/**, apps/streamlit/tests/**"
---

# Testing Rules

- Every code change needs unit tests (happy path + key edge cases). Bug fixes need a reproducing test.
- **Tests use mocked HTTP — never real network requests.** No real filesystem outside `tmp_path` / fixtures.
- Tests are focused — do not assert many unrelated things in one test.
- Core tests run via `python -m pytest tests/ -q`. Core lint runs via `python -m ruff check src/ tests/` and `python -m ruff format --check src/ tests/`.
- Streamlit app tests run via `python -m pytest apps/streamlit/tests/ -q`. App lint runs via `python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/` and `python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/`.
- **Delegate test/lint runs to the `test-runner` agent.** It uses a two-pass strategy (quiet first, verbose re-run of failures only) and is required because the suite is ~500 tests — full verbose output is too large for the main context.
- Task is complete only when both tests AND linting are clean.

## Streamlit Tests (apps/streamlit/**)

Before adding or recommending a Streamlit app test, inspect the app code and classify the target behavior:

1. Business logic — should be unit tested.
2. Data processing logic — should be unit tested.
3. Integration behavior — may need mocked integration tests.
4. Critical user workflow — may need a small app-level or UI-flow test.
5. Pure presentation/UI rendering — should not be tested unless explicitly required.

Do not create tests that only verify:

- Static display calls such as `st.title`, `st.header`, `st.markdown`, `st.write`, `st.caption`, or `st.divider`.
- Exact labels, wording, layout, column positions, tabs, expanders, visual formatting, styling, spacing, ordering, icons, emojis, or cosmetic details.
- Every individual Streamlit widget such as `st.button`, `st.selectbox`, `st.text_input`, `st.number_input`, `st.checkbox`, `st.radio`, `st.slider`, or `st.date_input`.
- Streamlit framework behavior itself.
- Chart or visualization styling: colors, legend position or orientation, padding, margins, spacing, axis label wording, or any chart spec property that does not affect data values. For charts, only test the data represented — correct counts, correct time values, correct series values, row shapes — never the visual style.

Only add Streamlit tests for meaningful application risk:

- Pure Python business logic extracted from the page.
- Data transformations, filtering, aggregation, validation, calculations, and formatting contracts that can break runtime behavior.
- Permission, role, authentication, or authorization logic.
- API, database, file, browser-storage, or crawl-job integration behavior with mocks or fixtures.
- Error handling for invalid user input.
- Critical user flows where a broken UI would cause incorrect output or production impact.
- App startup smoke tests that ensure the app imports and renders without crashing.

Prefer moving testable logic out of `streamlit_app.py` into pure modules such as `crawl4md_streamlit.support`, `crawl4md_streamlit.controls`, or purpose-built `services/`, `utils/`, `logic/`, `validators/`, and `repositories/` modules. Test those modules instead of mocking Streamlit rendering calls.

When reviewing existing Streamlit tests, recommend removal or simplification for tests that mock Streamlit excessively, assert static UI text, assert visual layout, duplicate Streamlit framework behavior, require frequent updates for harmless UI changes, or add maintenance cost without validating business behavior.

For every recommended Streamlit test, briefly state the risk it covers, why it is worth testing, and whether it is unit, integration, smoke, or UI-flow coverage. For tests you choose not to create, briefly state why they are unnecessary.
