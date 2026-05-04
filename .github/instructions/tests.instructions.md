---
description: "Use when writing or editing tests under tests/. Covers mocking policy, required coverage per change, root Streamlit app linting, and how to invoke the test-runner agent."
applyTo: "tests/**"
---

# Testing Rules

- Every code change needs unit tests (happy path + key edge cases). Bug fixes need a reproducing test.
- **Tests use mocked HTTP — never real network requests.** No real filesystem outside `tmp_path` / fixtures.
- Tests are focused — do not assert many unrelated things in one test.
- Run via `python -m pytest tests/ -q`. Lint via `python -m ruff check src/ tests/ streamlit_app.py` and `python -m ruff format --check src/ tests/ streamlit_app.py`.
- **Delegate test/lint runs to the `test-runner` agent.** It uses a two-pass strategy (quiet first, verbose re-run of failures only) and is required because the suite is ~500 tests — full verbose output is too large for the main context.
- Task is complete only when both tests AND linting are clean.
