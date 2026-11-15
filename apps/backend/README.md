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
| `POST /rag/generate` | Stream an answer for a raw, pre-built prompt (Step 4 "send"): NDJSON `{token}` frames then a final `{done, usage, model_used, warnings}` frame | `{prompt, llm_model?}` |
| `POST /rag/conversational` | Stream a Step 5 conversational turn: NDJSON `{progress}`/`{token}` frames then a final `{done: <ConversationalAnswer>}` frame | `{run_dir, question, state, config, history?, cached_chunks?}` |
| `POST /crawl` | Run a Step 1 crawl, streaming NDJSON `{job_id}` then `{event}` progress frames then a final `{result}` frame (needs the `[crawl]` extra + a browser in the image) | `{output_base, crawler_config, page_config?, activity_log_size?}` |
| `POST /crawl/{job_id}/cancel` | Request cooperative cancel of a running crawl job | — |
| `POST /index` | Run a Step 2 index job, streaming NDJSON `{job_id}` then `{event}` progress frames then a final `{result}` frame | `{output_base, input_paths, config}` |
| `POST /index/{job_id}/cancel` | Request cooperative cancel of a running index job | — |

- `run_dir` (and the crawl `output_base`) is resolved **under `ARTIFACTS_ROOT`** with
  containment (path traversal is rejected with `400`); `run_dir` points at an index
  directory containing `manifest.json`.
- Library warnings/errors are returned in the `200` payload as `{code, text,
  params, severity}` objects (from `LibraryMessage.as_dict()`), so any client localizes
  by `code` — never by matching text.

## Storage note

The full offload is exposed: the Step 1 crawl job, the Step 2 index job, and the Steps 3–5
RAG reads. The crawl and index jobs additionally require frontend and backend to **share
storage** (they write under `ARTIFACTS_ROOT`, which the frontend reads back). See the roadmap
in [docs/CLOUD_DEPLOYMENT.md](../../docs/CLOUD_DEPLOYMENT.md).

## Test

```bash
python -m pytest -q      # from apps/backend; mocks the library calls (no network)
```
