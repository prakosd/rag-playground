---
description: "Use when editing the vector_indexer library in src/vector_indexer/ or its tests. Covers lazy heavy imports, the embedding-provider interface with graceful failure and Titan fallback, the vector-store interface, and no-model-download testing."
applyTo: "src/vector_indexer/**, tests/test_vector_indexer_*.py"
---

# vector_indexer

UI-independent library that loads documents, chunks them, embeds the chunks, and
persists them to a vector store behind an interface. Powers Step 2 of the app but
must stay usable from a notebook, CLI, or tests without Streamlit.

## Data flow

```
VectorIndexer.run(config, inputs, output_base)
  ├─ resolve_embedding()      → provider (+ local-model fallback warnings)
  ├─ load_documents()         → Document[]  (.md/.txt, .zip via artifact_store)
  ├─ chunk_documents()        → Chunk[]      (langchain RecursiveCharacterTextSplitter)
  ├─ provider.embed_documents → vectors
  └─ VectorStore.add_documents/persist → vector_<id>/<timestamp>/chroma + manifest.json
```

## Constraints

- **No UI / crawler imports.** `vector_indexer` must not import `streamlit`, `crawl4md_streamlit`, or `crawl4md`. It may depend on `artifact_store` and `pydantic`. A boundary test enforces this.
- **Lazy heavy imports.** Never import `chromadb`, `langchain_text_splitters`, `boto3`, or `openai` at module top level. Import them inside the function/method that needs them so `import vector_indexer` stays light (a subprocess test asserts none are eagerly loaded). These ship as opt-in extras (`vector`, `bedrock`, `openai`).
- **Config.** `IndexingConfig` is Pydantic v2 (`field_validator`/`model_validator`): `chunk_size`≥1, `chunk_overlap`≥0 and `< chunk_size`, `embedding_dimension`≥1, `language` normalized and validated against `LUCENE_LANGUAGES`. Defaults: 600 / 100 / Titan / 512 / english.
- **Embedding providers.** Implement `EmbeddingProvider` (ABC). Construction probes availability and raises `EmbeddingProviderUnavailable` when a dependency or credential is missing — never raise raw import/credential errors. Credentials come **only** from environment variables (`AWS_*`, `OPENAI_API_KEY`); never hardcode secrets.
- **Resolution policy.** `resolve_embedding` applies a universal fallback: when the requested model is unavailable it falls back to the local offline provider (`all-MiniLM-L6-v2`) and appends a warning, so a run still succeeds. It re-raises only when the local model itself was requested and is unavailable, or when the local fallback is also unavailable (combined error the indexer records). Heavy HuggingFace ids in `DISABLED_MODELS` are not offered in the UI and fail gracefully (no torch), then fall back to local.
- **Vector store interface.** Callers depend on `VectorStore` (ABC: `create_collection`/`add_documents`/`persist`), never on ChromaDB directly. `ChromaVectorStore` always receives explicit embeddings, so ChromaDB never invokes its own embedding function (no model download). ChromaDB collection names must be 3–512 chars of `[a-zA-Z0-9._-]`.
- **Structured result.** `run` returns `IndexingResult` (success, output_dir, indexed/skipped counts, warnings, errors) and writes a `manifest.json`. `warnings`/`errors` are `artifact_store.LibraryMessage` objects (codes/builders in `vector_indexer.messages`); `str()` yields English and `manifest.json` stores `as_dict()`. Cancellation is cooperative via `should_cancel`.

## Tests

- Live in `tests/` (run by `python -m pytest tests/ -q`, linted by `ruff check src/ tests/`).
- **Never download a model.** The offline embedder downloads ~80 MB on first `embed_documents` — do not call it in tests. Use a fake provider, fake/`importorskip` the store, and pass explicit embeddings.
- Test config validation, loader filtering, chunk size/overlap, graceful provider failure (monkeypatch env), the Titan→offline fallback decision (inject fake build callables), the indexer flow with a fake store + resolver, and the import-boundary subprocess check.
