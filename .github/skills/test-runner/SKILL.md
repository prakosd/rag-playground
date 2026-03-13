---
name: test-runner
description: "Run pytest and ruff lint/format checks for crawl4md. Use when: run tests, run lint, verify changes, check code quality, finalize code changes, validate implementation."
argument-hint: "Run all tests and lint checks and report results"
---

# Test & Lint Runner

Run pytest and ruff checks, then return a structured report. Two-pass strategy: quiet run first, verbose re-run of failures only.

## Configurable Constants (pytest only)

<!-- ✏️ Adjust these values to match your machine's performance -->
- **WAIT_SECONDS = 5** — seconds to sleep while pytest runs
- **MAX_RETRIES = 3** — maximum sleep-then-check cycles before reporting timeout

These constants apply **only to pytest commands** (Steps 1 & 2). Ruff commands are fast and do not need them.

## Terminal Command Protocols

This is the most important section. Violating these rules causes `KeyboardInterrupt` cascades that corrupt test results.

### Pytest wait strategy (Steps 1 & 2)

Pytest runs take minutes. Run pytest and a sleep timer **in parallel**, then check output after the sleep finishes:

1. **Launch pytest in the background.** Run the pytest command via `run_in_terminal` with `isBackground=true`. Record its terminal ID.
2. **Immediately start a sleep timer.** In a **separate** `run_in_terminal` call (with `isBackground=false` and `timeout=0`), run `python -c "import time; time.sleep(WAIT_SECONDS)"`. This blocks until the sleep completes — by then pytest should be done.
3. **Check pytest output.** When the sleep returns, read the pytest terminal's output via `get_terminal_output` using the ID from step 1. Look for a **completion indicator**.
4. **Retry if not done.** If no completion indicator is found, repeat steps 2–3 (sleep again, then re-check). After **MAX_RETRIES** cycles with no indicator, report the command as timed out — do NOT retry it.

**Pytest completion indicators** (at least one must appear):
- `passed`, `failed`, `error`, or `no tests ran`

### Ruff direct strategy (Steps 3 & 4)

Ruff commands finish in seconds. Run them directly — no sleep timer needed:

1. Run the ruff command via `run_in_terminal` with `isBackground=false`.
2. Read the output directly. No sleep, no retry loop.

**Ruff completion indicators:**
- **ruff check:** `Found N error`, `All checks passed`, or a shell prompt (`>` or `$` at start of line)
- **ruff format:** `would be reformatted`, `already formatted`, or a shell prompt

## Workflow

This project has ~500 tests. Verbose output would be ~1000 lines — too large to parse. Use the two-pass strategy below.

### Step 0 — collect test count

```
python -m pytest tests/ --collect-only -q -q
```

Run using the **ruff direct strategy** (fast, no sleep needed). Double `-q` suppresses individual test names — output is just `N tests collected`. Record this number as **EXPECTED_TOTAL**.

### Step 1 — pytest quick pass

```
python -m pytest tests/ -q
```

Wait for completion using the **pytest wait strategy** above.

- If the summary says **all passed**: verify the passed count equals **EXPECTED_TOTAL**. If it doesn't, report the mismatch as a warning. Move to Step 3 (skip Step 2).
- If there are **failures or errors**: proceed to Step 2.

### Step 2 — re-run failures only (verbose)

Only run this if Step 1 reported failures:

```
python -m pytest tests/ --lf -v --tb=long
```

Wait for completion using the **pytest wait strategy** above. This re-runs only the last-failed tests with full tracebacks. Record each failure with its full traceback.

### Step 3 — ruff lint check

```
ruff check src/ tests/
```

Run using the **ruff direct strategy** above.

### Step 4 — ruff format check

```
ruff format --check src/ tests/
```

Run using the **ruff direct strategy** above.

### Step 5 — Return structured report

```
## Test Results
- Status: PASSED / FAILED
- Expected: EXPECTED_TOTAL tests (from --collect-only)
- Actual: X passed, Y failed, Z errors
- Count check: MATCH / MISMATCH (if passed ≠ EXPECTED_TOTAL, flag it)
- Failed tests: (list each with full traceback from Step 2, or "None")

## Lint Results
- ruff check: PASSED / FAILED (N errors)
- ruff format: PASSED / FAILED (N files need reformatting)
- Error details: (list each, or "None")

## Summary
- Overall: ALL CLEAR / ISSUES FOUND
- (If issues found, list the specific files and line numbers that need attention)
```

## Constraints

- DO NOT fix any code — only report results
- DO NOT skip any of the commands (except Step 2 when all tests pass)
- DO NOT summarize away error details — include the full error message for each failure
- For pytest commands, ALWAYS use the pytest wait strategy — sleep the full WAIT_SECONDS before checking output
- For ruff commands, run directly — no sleep timer needed
- If a pytest command times out after MAX_RETRIES cycles, report it explicitly — do NOT retry
- ALWAYS wait for pytest to fully complete (Steps 1–2) before starting any ruff commands (Steps 3–4)
- NEVER run `python -m pytest tests/ -v` without `--lf` — the full verbose output is too large
- ALWAYS use `python -m pytest` instead of bare `pytest` — ensures the correct environment is used
- ALWAYS verify that total passed tests equals EXPECTED_TOTAL from Step 0 — a mismatch means tests were silently skipped or deselected
