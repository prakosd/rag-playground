---
description: "Use when writing or editing tests under tests/ or apps/streamlit/tests/. Covers mocking policy, required coverage per change, app linting, and how to invoke the test-runner agent."
applyTo: "tests/**, apps/streamlit/tests/**"
---

# Testing Rules

- Every code change needs unit tests (happy path + key edge cases). Bug fixes need a reproducing test.
- **Tests use mocked HTTP — never real network requests.** No real filesystem outside `tmp_path` / fixtures.
- Tests are focused — do not assert many unrelated things in one test.
- Core tests run via `python -m pytest tests/ -q`. Core lint runs via `python -m ruff check src/ tests/` and `python -m ruff format --check src/ tests/`.
- Streamlit app tests run via `python -m pytest apps/streamlit/tests/ -q`. App lint runs via `python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/src/ apps/streamlit/tests/` and `python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/src/ apps/streamlit/tests/`.
- **Delegate test/lint runs to the `test-runner` agent.** It uses a two-pass strategy (quiet first, verbose re-run of failures only) and is required because the suite is ~500 tests — full verbose output is too large for the main context.
- Task is complete only when both tests AND linting are clean.
