# app-backend — FastAPI service

An **additive** HTTP layer over the rag-playground libraries. It reuses `rag_engine`
(and the shared `artifact_store` path guard) without changing the Streamlit app or
the libraries, so the frontend keeps working in-process today and can call this
service later (see the app's `BACKEND_MODE=http`). Part of the Tier-2 split in
[docs/CLOUD_DEPLOYMENT.md](../../docs/CLOUD_DEPLOYMENT.md).

## Run

```bash
pip install -e ".[dev]"          # from apps/backend, plus the library extras it serves
export ARTIFACTS_ROOT=/data/outputs   # shared volume the indexer writes to (default: outputs)
uvicorn app_backend.main:app --host 0.0.0.0 --port 8000
```

## Endpoints

| Method + path | Purpose | Body |
|---|---|---|
| `GET /health` | Liveness probe | — |
| `POST /rag/search` | Semantic search over an index (Step 3) | `{run_dir, query, top_k?, score_threshold?, search_type?, source_filter?}` |
| `POST /rag/answer` | Grounded answer over an index (Step 4) | `{run_dir, question, llm_model?, temperature?, max_tokens?, top_k?}` |

- `run_dir` is resolved **under `ARTIFACTS_ROOT`** with containment (path traversal is
  rejected with `400`); it points at an index directory containing `manifest.json`.
- Library warnings/errors are returned in the `200` payload as `{code, default_text,
  params, severity}` objects (from `LibraryMessage.as_dict()`), so any client localizes
  by `code` — never by matching text.

## Not yet exposed (roadmap)

Crawl and index jobs (long-running, need progress/cancel + SSE) and the conversational
(Step 5) + streaming endpoints. See the roadmap in
[docs/CLOUD_DEPLOYMENT.md](../../docs/CLOUD_DEPLOYMENT.md).

## Test

```bash
python -m pytest -q      # from apps/backend; mocks the library calls (no network)
```
