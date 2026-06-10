---
name: test-runner
description: "Run pytest and ruff lint/format checks for crawl4md. Use when: run tests, run lint, verify changes, check code quality, finalize code changes, validate implementation."
argument-hint: "Run all tests and lint checks and report results"
---

# Test & Lint Runner

Run pytest and ruff checks, then return a structured report. Two-pass strategy: quiet run first, verbose re-run of failures only. Ruff checks only run when all tests pass.

## Terminal Command Protocols

This is the most important section.

### Pytest user-confirmation strategy (Steps 1 & 2)

Pytest runs take minutes. Run in a background terminal and ask the user to confirm when it's done:

1. **Launch pytest in the background.** Run the pytest command via `run_in_terminal` with `isBackground=true`. Record its terminal ID.
2. **Ask the user to confirm completion.** Use `vscode_askQuestions` with a single-click button — no freeform input:
   ```json
   {
     "questions": [{
       "header": "Pytest status",
       "question": "Pytest is running. Open the Terminal panel (Ctrl+`) to watch progress, then click Done when it finishes.",
       "options": [{"label": "Done", "recommended": true}],
       "allowFreeformInput": false
     }]
   }
   ```
   Wait for the user to click **Done** before proceeding.
3. **Read pytest output.** After confirmation, read the terminal's output via `get_terminal_output` using the ID from step 1. Look for a **completion indicator** to parse results.

**Pytest completion indicators** (at least one must appear in the output):
- `passed`, `failed`, `error`, or `no tests ran`

### Ruff direct strategy (Steps 3 & 4)

Ruff commands finish in seconds. Run them directly — no confirmation needed:

1. Run the ruff command via `run_in_terminal` with `isBackground=false`.
2. Read the output directly.

**Ruff completion indicators:**
- **ruff check:** `Found N error`, `All checks passed`, or a shell prompt (`>` or `$` at start of line)
- **ruff format:** `would be reformatted`, `already formatted`, or a shell prompt

## Workflow

This project has core library tests plus a separated Streamlit app test suite. Verbose output would be too large to parse. Use the two-pass strategy below.

### Step 1 — core pytest quick pass

```
python -m pytest tests/ -q
```

Run using the **pytest user-confirmation strategy** above.

- If the summary says **all passed**: move to Step 3 (skip Step 2).
- If there are **failures or errors**: proceed to Step 2.

### Step 2 — re-run core failures only (verbose)

Only run this if Step 1 reported failures:

```
python -m pytest tests/ --lf -v --tb=long
```

Run using the **pytest user-confirmation strategy** above. This re-runs only the last-failed tests with full tracebacks. Record each failure with its full traceback.

If tests still fail after Step 2, **skip Steps 3–8** and go directly to Step 9.

### Step 3 — app pytest quick pass

```
python -m pytest apps/streamlit/tests/ -q
```

Run using the **pytest user-confirmation strategy** above.

- If the summary says **all passed**: move to Step 5 (skip Step 4).
- If there are **failures or errors**: proceed to Step 4.

### Step 4 — re-run app failures only (verbose)

Only run this if Step 3 reported failures:

```
python -m pytest apps/streamlit/tests/ --lf -v --tb=long
```

Run using the **pytest user-confirmation strategy** above. Record each failure with its full traceback.

If tests still fail after Step 4, **skip Steps 5–8** and go directly to Step 9.

### Step 5 — core ruff lint check

**Only proceed if all tests passed.** If any tests failed, skip to Step 9.

```
python -m ruff check src/ tests/
```

Run using the **ruff direct strategy** above.

### Step 6 — core ruff format check

```
python -m ruff format --check src/ tests/
```

Run using the **ruff direct strategy** above.

### Step 7 — app ruff lint check

```
python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
```

Run using the **ruff direct strategy** above.

### Step 8 — app ruff format check

```
python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
```

Run using the **ruff direct strategy** above.

### Step 9 — Return structured report

```
## Test Results
- Status: PASSED / FAILED
- Core actual: X passed, Y failed, Z errors
- App actual: X passed, Y failed, Z errors
- Failed tests: (list each with full traceback from Step 2 or Step 4, or "None")

## Lint Results
- core ruff check: PASSED / FAILED (N errors) / SKIPPED (tests failed)
- core ruff format: PASSED / FAILED (N files need reformatting) / SKIPPED (tests failed)
- app ruff check: PASSED / FAILED (N errors) / SKIPPED (tests failed)
- app ruff format: PASSED / FAILED (N files need reformatting) / SKIPPED (tests failed)
- Error details: (list each, or "None")

## Summary
- Overall: ALL CLEAR / ISSUES FOUND
- (If issues found, list the specific files and line numbers that need attention)
```

## Constraints

- DO NOT fix any code — only report results
- DO NOT skip any of the commands except failure reruns when the matching quick pass succeeds, and ruff commands when tests fail
- DO NOT summarize away error details — include the full error message for each failure
- For Streamlit app tests, enforce the Streamlit Tests policy in `.github/instructions/tests.instructions.md`.
- For pytest commands, ALWAYS run in background and ask the user to confirm completion before reading output
- For ruff commands, run directly — no confirmation needed
- ALWAYS wait for pytest to fully complete before starting any ruff commands
- Only run ruff if all tests passed — if any tests failed, skip ruff and go to Step 9
- NEVER run `python -m pytest tests/ -v` without `--lf` — the full verbose output is too large
- ALWAYS use `python -m pytest` instead of bare `pytest` — ensures the correct environment is used
- ALWAYS prefer `python -m ruff` instead of bare `ruff` — ensures the correct environment is used
