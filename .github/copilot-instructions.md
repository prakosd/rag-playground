# Copilot Instructions — crawl4md

## Overview

crawl4md crawls websites and extracts content as Markdown. The core `crawl4md` library wraps Crawl4AI with a synchronous API (for Jupyter); a Streamlit app under `apps/streamlit/` offers a browser form. Two helper libraries support it: `artifact_store` (shared, pure-stdlib naming/paths/archive/discovery helpers) and `vector_indexer` (UI-independent chunking + embedding + vector-store creation, powering the app's Step 2).

**Package map** (full structure + diagrams in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)):

- `src/crawl4md/` — crawl → extract → write → sort; owns output, progress events, cancel hooks.
- `src/artifact_store/` — shared foundation; pure stdlib, no crawler/UI imports.
- `src/vector_indexer/` — load → chunk → embed → vector store; no UI imports.
- `apps/streamlit/` — UI adapter only (rendering, session/browser state, background jobs, downloads). Keep the libraries usable without Streamlit; never push UI or path conventions into them.

## Data Flow

- **Step 1 (crawl):** `SiteCrawler.crawl()` → Crawl4AI (raw HTML) → `ContentExtractor` (Markdown) → `FileWriter` (size-limited files + URL lists) → `ContentSorter` (sorted final output). Each crawl writes a timestamped dir; results pass through rounds (initial + retries), then merge/dedupe/sort.
- **Step 2 (index):** `VectorIndexer.run()` → `resolve_embedding` (Titan default, local-model fallback for any failed model) → `load_documents` (.md/.txt/.zip) → `chunk_documents` → embed + `VectorStore` (ChromaDB) → `IndexingResult` + `manifest.json`.

## Module Rules

Per-module constraints auto-attach from `.github/instructions/*.instructions.md` when you edit matching files. Follow them when loaded.

## Coding Conventions

- Python 3.10+, type hints on all public APIs. Pydantic v2 (`model_validator`, `field_validator`). Lint via ruff.
- Tests use mocked HTTP — never real network requests. Keep Streamlit UX plain-language, no jargon.
- **No inline magic values:** thresholds, tag lists, regex patterns, repeated string literals → `_UPPER_SNAKE_CASE` constants grouped after imports; regex `re.compile()`d at module level. **Exempt:** Pydantic field defaults, standard idioms, single-use spec keys, trivial markdown (`"- "`, `"### "`).

## Planning

For non-trivial work, write a plan first: short, independently-executable steps readable by a smaller model; call out which steps delegate to a subagent (`Explore`, `test-runner`, `code-reviewer`); end with `test-runner` verification. See the [agent-orchestration](./skills/agent-orchestration/SKILL.md) skill.

## Testing

- Every code change needs unit tests (happy path + key edge cases; bug fixes need a reproducing test). Done only when tests AND lint are clean.
- Delegate test/lint runs to the `test-runner` agent and diff review to the `code-reviewer` agent before finishing.
- Full rules: [tests.instructions.md](./instructions/tests.instructions.md).

## Docs

Update the relevant README/doc when user-facing behavior changes: [README.md](../README.md), per-topic docs under [docs/](../docs/), and per-package READMEs under `src/*/` and `apps/streamlit/`. When adding or removing a dependency, also update [devcontainer.instructions.md](./instructions/devcontainer.instructions.md) and `.devcontainer/devcontainer.json`.
