# Case Study — rag-playground

← Back to [README](../README.md) · see also [ARCHITECTURE.md](ARCHITECTURE.md) · [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)

A portfolio write-up of **what** this project solves, **how** it is engineered, the
**results**, and **how it was built** — an experiment in agentic, AI-assisted software
engineering. Written to be readable by both engineers and non-technical reviewers.

> **One line:** turn messy public websites into **grounded, cited, injection-resistant
> answers** — crawl → index → search → ask → converse — runnable **offline**, shipped as
> small independent libraries plus a browser app.

---

## TL;DR (for a quick skim)

| | |
| --- | --- |
| **What** | An end-to-end Retrieval-Augmented Generation (RAG) playground: crawl a site → build a vector index → semantic search → grounded Q&A → history-aware chat. |
| **Why it's interesting** | Works **offline** (no cloud key needed), defends against **prompt injection** from crawled text, and is split into **reusable libraries** a non-Streamlit UI can drive. |
| **Stack** | Python 3.11–3.14 · Crawl4AI/Playwright · LangChain · ChromaDB · Streamlit · FastAPI · pydantic v2 · pytest/ruff. |
| **Scale** | ~36k lines of library/app code, **2,000+ tests** (~1:1 test-to-code), 6 import packages, boundary-enforced layering. |
| **Live demo** | <https://rag-playground-prakosd.streamlit.app/> |
| **How it was built** | Most code authored by **GitHub Copilot** working as an agent; my role was architect, instruction-writer, reviewer, and tester. |

---

## The problem

Organizations constantly need to answer questions grounded in their **own** web content,
product docs, and FAQs. Doing that well is deceptively hard:

1. **Web content is messy.** Pages hide the real text inside navigation, banners,
   accordions, and scripts; some sites sit behind bot/WAF protection; some content is in
   PDFs or Word files.
2. **Naïve RAG is untrustworthy.** Answers need **citations** back to the source, must
   avoid hallucination, and must say "I don't know" when the index can't support an answer.
3. **Crawled text is hostile input.** A crawled page can contain **prompt-injection**
   ("ignore previous instructions…"), so retrieved text must be treated as untrusted.
4. **Cloud LLMs are a barrier to learning.** Keys, cost, and quotas make it hard to simply
   *try* RAG and understand each moving part.

## The solution

An offline-capable RAG pipeline exposed as **five independent, single-purpose libraries**
plus a thin Streamlit app, so each stage is understandable, testable, and reusable:

1. **Crawl → Markdown** (`crawl4md`): drives a real browser, extracts the *main* content
   (trafilatura + fallbacks, PDF/OCR and `.docx` support), handles WAF/bot retries, and
   writes size-limited, sorted Markdown.
2. **Index** (`vector_indexer`): chunks the Markdown and builds a ChromaDB vector store
   with pluggable embeddings (Amazon Titan, OpenAI, or an offline default).
3. **Search / Q&A / Chat** (`rag_engine`): semantic search, grounded single-turn Q&A, and
   history-aware conversational RAG with query decomposition, multi-query retrieval,
   re-ranking, validated follow-ups, and an opt-in prompt-injection defense.
4. **Shared foundations** (`artifact_store`, `log4py`): pure-stdlib naming/path-safety/
   archive helpers and a zero-dependency logging layer every package can use.

**Engineering decisions that make it portfolio-worthy:**

- **Strict separation of concerns.** Libraries never import the UI; the Streamlit app is
  just one adapter. This is **enforced by boundary tests**, so the layering can't silently
  rot. (See [BUILDING_ANOTHER_UI.md](BUILDING_ANOTHER_UI.md).)
- **Atomic, opt-in dependencies.** The base install has **zero third-party dependencies**;
  each capability is an extra (`[crawl]`, `[vector]`, `[bedrock]`, `[openai]`, `[rag]`,
  `[rerank]`, `[s3]`). You never download a browser stack just to build an index.
- **Graceful degradation.** With no cloud credentials, an **offline echo model** and a
  default embedder keep every step runnable; a mis-configured cloud key fails with a clear,
  localized message instead of crashing.
- **Structured, localizable messaging.** Libraries emit stable message **codes** (never UI
  strings); the app localizes them (English + Indonesian), so the libraries stay UI- and
  language-agnostic.
- **Security-aware.** Retrieved text is sanitized and "spotlighted"/datamarked before it
  reaches the answer prompt; downloadable archives are signed and extracted zip-slip-safe.
- **Cloud-ready by design.** A 12-factor config, a storage-backend seam (local **or** S3),
  and an additive FastAPI service let the same libraries run as a scalable backend. (See
  [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) and [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md).)

## Results & impact

- **A working, hosted product.** Five-step pipeline live on Streamlit Community Cloud,
  usable in-browser with zero setup.
- **Quality bar held high.** **2,000+ automated tests** across 129 files with a ~1:1
  test-to-code ratio and **~91% coverage on the libraries / ~88% on the app**; HTTP and model
  downloads are mocked, so the suite is fast and deterministic. Lint/format (ruff) and type
  hints on all public APIs are part of "done."
- **Genuinely reusable.** Any front end (React, a CLI, an API) can drive the libraries;
  the included FastAPI backend proves the seam.
- **Breadth of modern techniques** in one codebase: web crawling, content extraction,
  OCR, chunking/embeddings, vector search, re-ranking, conversational memory, query
  decomposition, prompt-injection defense, and token/cost accounting.

## How it was built — agentic AI development

Most of the code in this repository was **authored by GitHub Copilot acting as a coding
agent.** My role as the project owner was the part that actually determines quality:

- **Architecting** the system — the library boundaries, the data flow, and the
  separation that keeps it maintainable.
- **Writing precise instructions and skills** — the repository-level
  [copilot-instructions](../.github/copilot-instructions.md), per-module instruction files,
  and reusable agent skills that steer the AI toward the project's conventions.
- **Reviewing every change** — reading diffs for correctness, simplicity, and adherence to
  the conventions, and sending work back when it drifted.
- **Testing and verifying** — insisting on reproducing tests for bugs, high coverage, and
  clean lint before anything is "done."

In other words, this project is a **double showcase**: it demonstrates a non-trivial RAG
system *and* a repeatable way of working — using agentic AI to design, build, and verify
real software while a human owns the architecture, specification, review, and quality gate.

### Skills demonstrated

System design & clean architecture · RAG and LLM application engineering · prompt-injection
defense · Python library design & packaging · test-driven, high-coverage development ·
CI/CD · cloud architecture (AWS, 3-tier) · technical writing · **directing and reviewing AI
coding agents** (specification, orchestration, quality control).

---

## Explore further

- **Try it:** [live demo](https://rag-playground-prakosd.streamlit.app/) ·
  [run it locally](../README.md#set-up-local-development)
- **Understand it:** [ARCHITECTURE.md](ARCHITECTURE.md) (helicopter → magnified views)
- **Deploy it:** [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) ·
  [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) · [CI/CD](CICD_GITHUB_ACTIONS.md)
- **Extend it:** [BUILDING_ANOTHER_UI.md](BUILDING_ANOTHER_UI.md)
