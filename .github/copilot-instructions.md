# Copilot Instructions — crawl4md

## Project Overview

crawl4md is a Python library for crawling websites and extracting content as Markdown-formatted text files. It wraps Crawl4AI with a synchronous API designed for non-technical Jupyter Notebook users.

## Data Flow

```
SiteCrawler.crawl()
  ├─ Crawl4AI (async) → CrawlResult (raw HTML per page)
  ├─ ContentExtractor  → ExtractedPage (clean Markdown per page)
  ├─ FileWriter         → size-limited content files + URL lists
  └─ ContentSorter      → sorted final files grouped by URL path
```

Each crawl creates a timestamped output directory. Results pass through multiple rounds (initial + retries), then merged, deduplicated, and sorted.

## File Layout

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic config models
├── crawler.py        # SiteCrawler class
├── extractor.py      # ContentExtractor class
├── sorter.py         # ContentSorter class
├── writer.py         # FileWriter class
└── progress.py       # ProgressReporter class
```

## Module-Specific Rules

Detailed constraints for each module live in on-demand instruction files under `.github/instructions/`. They auto-attach when you edit matching files:

| File | When it loads |
|------|---------------|
| [`config.instructions.md`](./instructions/config.instructions.md) | editing `config.py` or its tests |
| [`crawler.instructions.md`](./instructions/crawler.instructions.md) | editing `crawler.py` or crawler/session/pdf tests |
| [`extractor.instructions.md`](./instructions/extractor.instructions.md) | editing `extractor.py` or extractor tests |
| [`writer.instructions.md`](./instructions/writer.instructions.md) | editing `writer.py`, `sorter.py`, or their tests |
| [`progress.instructions.md`](./instructions/progress.instructions.md) | editing `progress.py` or its tests |
| [`tests.instructions.md`](./instructions/tests.instructions.md) | editing anything under `tests/` |
| [`devcontainer.instructions.md`](./instructions/devcontainer.instructions.md) | editing `.devcontainer/**` or `pyproject.toml` |

## Coding Conventions

- Python 3.10+, type hints on all public APIs. Pydantic v2 (`model_validator`, `field_validator`). Linting via ruff (`pyproject.toml`).
- Tests use mocked HTTP — never real network requests. Keep notebook UX simple: plain language, no jargon.
- **No inline magic values:** Thresholds, tag lists, regex patterns, repeated string literals → `_UPPER_SNAKE_CASE` constants (grouped after imports). Regex `re.compile()`d at module level. **Exempt:** Pydantic field defaults, standard Python idioms, spec-defined keys used once, trivial markdown strings (`"- "`, `"### "`).

## Planning

For any non-trivial task, write a plan **before** implementing. Every plan must:

- Be **understandable by Claude Sonnet 4.6** — clear, simple, short steps; no jargon; each step independently executable. Sonnet 4.6 is a smaller model, so prefer many narrow steps over a few broad ones.
- **Use AI agent orchestration** — explicitly call out which steps delegate to a subagent (`Explore`, `test-runner`, `code-reviewer`) and which run inline. Break large work into small subtasks and combine results in a named integration step. End with verification via `test-runner`.
- See the [`agent-orchestration`](./skills/agent-orchestration/SKILL.md) skill for patterns and decision rules.

## Testing Policy (summary)

- Every code change needs unit tests (happy path + key edge cases; bug fixes need a reproducing test).
- Start with a TODO list before implementing. Task is complete only when tests AND linting are both clean.
- **Delegate test/lint runs to the `test-runner` agent** (two-pass: quiet first, then verbose re-run of failures only).
- **Delegate diff review to the `code-reviewer` agent** before declaring a task complete — it enforces the "clean, lightweight, not bloated" bar.
- Full testing rules live in [`tests.instructions.md`](./instructions/tests.instructions.md).

## Maintaining This File

**Keep here:** project-wide conventions and cross-module rules that apply to *every* turn (overview, data flow, coding conventions, planning, testing policy summary).

**Move to `instructions/*.instructions.md`:** module-scoped constraints that only matter when a specific file is being edited.

**Omit:** implementation details readable from source. Update README.md for user-facing behavior changes. When adding/removing Python dependencies or system packages, also update [`devcontainer.instructions.md`](./instructions/devcontainer.instructions.md) and `.devcontainer/devcontainer.json`.
