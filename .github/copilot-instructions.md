# Copilot Instructions — crawl4md

## Overview

crawl4md crawls websites and extracts content as Markdown. The core `crawl4md` library wraps Crawl4AI with a synchronous API (for Jupyter); a Streamlit app under `apps/streamlit/` offers a browser form. Three helper libraries support it: `artifact_store` (shared, pure-stdlib naming/paths/archive/discovery helpers), `vector_indexer` (UI-independent chunking + embedding + vector-store creation via LangChain, powering the app's Step 2), and `rag_engine` (UI-independent retrieval + QA + conversational RAG over an index, powering Steps 3-5).

**Package map** (full structure + diagrams in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)):

- `src/crawl4md/` — crawl → extract → write → sort; owns output, progress events, cancel hooks.
- `src/artifact_store/` — shared foundation; pure stdlib, no crawler/UI imports.
- `src/vector_indexer/` — load → chunk → embed (LangChain `Embeddings`) → langchain-chroma vector store; no UI imports.
- `src/rag_engine/` — retrieve (reopen index via manifest) → resolve chat model → generate (QA + conversational); no UI imports; depends on `vector_indexer`.
- `apps/streamlit/` — UI adapter only (rendering, session/browser state, background jobs, downloads). Keep the libraries usable without Streamlit; never push UI or path conventions into them.

**Packaging:** one pip distribution named `rag-playground` (import packages unchanged: `crawl4md`, `vector_indexer`, `rag_engine`, `artifact_store`). The base install is dependency-free; each library is an opt-in extra — `[crawl]`, `[vector]`, `[bedrock]`, `[openai]`, `[rag]`, `[all]` — so installs stay atomic. `[vector]` uses langchain-chroma; `[bedrock]`/`[openai]` (langchain-aws/langchain-openai) serve both embeddings and chat models; `[rag]` adds the `langchain` umbrella for `init_chat_model`. The Streamlit app installs `rag-playground[crawl,vector,bedrock,openai,rag]`.

## Data Flow

- **Step 1 (crawl):** `SiteCrawler.crawl()` → Crawl4AI (raw HTML) → `ContentExtractor` (Markdown) → `FileWriter` (size-limited files + URL lists) → `ContentSorter` (sorted final output). Each crawl writes a timestamped dir; results pass through rounds (initial + retries), then merge/dedupe/sort.
- **Step 2 (index):** `VectorIndexer.run()` → `resolve_embedding` (Titan default → LangChain `Embeddings`; raises `EmbeddingProviderUnavailable` when a model's package/credential is missing — recorded as a cause-specific error via `classify_model_unavailable`, no silent local fallback) → `load_documents` (.md/.txt/.zip) → `chunk_documents` → langchain-chroma `Chroma` store → `IndexingResult` + `manifest.json` (records embedding model + `collection_name`).
- **Steps 3-5 (RAG):** `rag_engine.retrieve()` reopens the index via `load_manifest` + `resolve_embedding` + langchain-chroma; `answer_question` / `chat_answer` then call `resolve_chat_model` (LangChain `init_chat_model`, offline echo fallback when a cloud model is unavailable) and run a defensive prompt → `RagAnswer` (answer + source `RetrievedChunk`s + warnings/errors). Conversational chat rewrites the follow-up via `condense_question`.

## Module Rules

Per-module constraints auto-attach from `.github/instructions/*.instructions.md` when you edit matching files. Follow them when loaded.

## Coding Conventions

- Python 3.10+, type hints on all public APIs. Pydantic v2 (`model_validator`, `field_validator`). Lint via ruff.
- Tests use mocked HTTP — never real network requests. Keep Streamlit UX plain-language, no jargon.
- **Structured messages:** libraries report user-facing warnings/errors/progress as `artifact_store.LibraryMessage` (stable `code` + English `default_text` + `params`), never UI strings; codes/builders live in `crawl4md.messages`, `vector_indexer.messages`, and `rag_engine.messages` (codes `rag.*`). `CrawlResult.error_code` and `crawl_warning` events carry crawl codes; `IndexingResult.warnings/errors` and `RagAnswer.warnings/errors` are `LibraryMessage` lists. UIs localize by code (app: `i18n.localize_message`) and fall back to `default_text` — never substring-match library text.
- **No inline magic values:** thresholds, tag lists, regex patterns, repeated string literals → `_UPPER_SNAKE_CASE` constants grouped after imports; regex `re.compile()`d at module level. **Exempt:** Pydantic field defaults, standard idioms, single-use spec keys, trivial markdown (`"- "`, `"### "`).

## Planning

For non-trivial work, write a plan first: short, independently-executable steps readable by a smaller model; call out which steps delegate to a subagent (`Explore`, `test-runner`, `code-reviewer`); end with `test-runner` verification. See the [agent-orchestration](./skills/agent-orchestration/SKILL.md) skill.

## Testing

- Every code change needs unit tests (happy path + key edge cases; bug fixes need a reproducing test). Done only when tests AND lint are clean.
- Delegate test/lint runs to the `test-runner` agent and diff review to the `code-reviewer` agent before finishing.
- Full rules: [tests.instructions.md](./instructions/tests.instructions.md).

## Docs

Update the relevant README/doc when user-facing behavior changes: [README.md](../README.md), per-topic docs under [docs/](../docs/), and per-package READMEs under `src/*/` and `apps/streamlit/`. When adding or removing a dependency, also update [devcontainer.instructions.md](./instructions/devcontainer.instructions.md) and `.devcontainer/devcontainer.json`.
