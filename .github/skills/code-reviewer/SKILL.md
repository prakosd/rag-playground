---
name: code-reviewer
description: "Review a code change for cleanliness, simplicity, and crawl4md conventions. Use when: reviewing a diff, checking for bloat, validating lightweight code, finalizing a change before declaring complete."
---

# Code Reviewer Workflow

Review code against the crawl4md project's bar: **clean, simple, lightweight, not bloated, not overly verbose**. Return a structured report. Do NOT modify any code — only report findings.

## Inputs

The orchestrator should tell you:

- Which files or diff to review (paths or a `git diff` reference).
- Optional: the user request that motivated the change, so you can judge whether the change stays within scope.

If unclear, list the changed files first via `get_changed_files` or `grep_search` and proceed.

## Review Checklist

Walk through every item. Flag violations with file + line.

### 1. Scope discipline
- Does the change do **only** what was asked? Flag unrelated edits, drive-by refactors, or "improvements" that weren't requested.
- Are there new features, abstractions, or helpers that aren't required for the stated task?

### 2. No bloat
- Any helper / class / abstraction used only **once**? Inline it.
- Any new layer of indirection without a concrete second caller? Flag it.
- Any added config flags or parameters with no real consumer? Flag.
- Any duplicated logic that should be consolidated? Flag.

### 3. No unnecessary verbosity
- Comments that restate what the code obviously does → remove.
- Docstrings added to **unchanged** code → must be removed (per `implementationDiscipline`).
- Type annotations added to internal helpers that didn't have them before → remove unless on a public API.
- Defensive error handling for impossible cases → remove. Validate only at system boundaries.
- Redundant logging / progress prints → trim.

### 4. crawl4md conventions (from `.github/copilot-instructions.md`)
- **No inline magic values:** thresholds, repeated string literals, regex patterns must be `_UPPER_SNAKE_CASE` constants grouped after imports. Regex must be `re.compile()`d at module level. (Exempt: Pydantic field defaults, single-use spec keys, trivial markdown like `"- "`.)
- **Pydantic v2** patterns (`model_validator`, `field_validator`) — flag v1 style.
- **Type hints on public APIs** — required.
- **Tests use mocked HTTP** — flag any real network call.

### 5. Tests
- Every code change has a test (happy path + key edge cases). Bug fixes need a reproducing test.
- Tests are focused — flag tests that assert too many unrelated things.
- No real network, no real filesystem outside `tmp_path` / fixtures.

### 6. Readability
- Function/method longer than ~40 lines and doing >1 thing? Suggest a split — but only if there is a real second use case or a clear cognitive boundary. Do NOT suggest splits that just create one-time helpers (that's bloat).
- Names match domain language (`CrawlResult`, `ExtractedPage`, `flush_interval`).
- Control flow is flat — flag deep nesting (>3 levels).

### 7. Public API surface
- Any new export in `__init__.py` that isn't required? Flag.
- Any breaking change to a public model field? Flag and require justification.

## Report Format

```
## Code Review

**Scope:** <files reviewed>
**Verdict:** APPROVE / APPROVE WITH MINOR / REQUEST CHANGES

### Must fix (blockers)
- [file:line] <issue> — <suggested fix>

### Should fix (bloat / verbosity)
- [file:line] <issue> — <suggested fix>

### Nits (optional)
- [file:line] <issue>

### What's good
- <one or two genuine positives, brief>
```

## Constraints

- Do NOT edit code. Report only.
- Do NOT suggest changes that add complexity (more layers, more config, more abstractions) unless they remove more complexity than they add.
- Do NOT request docstrings, type hints, or comments on code the change did not touch.
- Bias toward **removing** lines, not adding them. If your suggestions on net add code, re-examine them.
- Be specific. "Function is too long" is not actionable. "Lines 80–120 mix HTTP fetch and parsing — extract `_parse_response`" is.
- If the change is small and clean, say so in one line and stop. Don't manufacture findings.
