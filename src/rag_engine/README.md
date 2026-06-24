# rag_engine

UI-independent retrieval-augmented generation over the vector indexes built by
[`vector_indexer`](../vector_indexer/README.md). It powers **Steps 3-5** of the
app — semantic search, single-turn QA, and conversational (history-aware) RAG —
and stays usable from a notebook, CLI, or tests without Streamlit.

## Data flow

```
retrieve(run_dir, query, config)            # Step 3
  ├─ load_manifest(run_dir)                  → embedding model + collection name
  ├─ resolve_embedding(model, dim)           → LangChain Embeddings (or raises if unavailable)
  └─ VectorSearcher.search(...)               → RetrievedChunk[] (+ similarity scores)

answer_question(run_dir, question, config)  # Step 4
  ├─ retrieve(...)                           → context chunks
  ├─ resolve_chat_model(llm_model)           → BaseChatModel (init_chat_model, echo fallback)
  └─ prompt | model | StrOutputParser        → RagAnswer(answer, sources, warnings, errors)

chat_answer(run_dir, question, history, config)  # Step 5
  ├─ condense_question(model, history, q)    → standalone search query
  ├─ retrieve(...)                           → context chunks
  └─ generate_chat_answer(...)               → RagAnswer (history-aware)
```

## Install

```bash
pip install -e ".[vector,rag]"            # retrieval + QA + chat (offline echo model)
pip install -e ".[vector,rag,bedrock]"    # + Amazon Bedrock chat models (langchain-aws)
pip install -e ".[vector,rag,openai]"     # + OpenAI chat models (langchain-openai)
```

`rag_engine` depends on `vector_indexer` to open indexes, so the `vector` extra is
always required alongside `rag`. Cloud chat models are additional opt-in extras.

## Quick start

```python
from rag_engine import RagConfig, answer_question

config = RagConfig(llm_model="anthropic.claude-3-5-sonnet-20240620-v1:0", top_k=4)
answer = answer_question(run_dir, "What does the API return on error?", config)

print(answer.answer)              # generated answer (or an echo when no credentials)
for chunk in answer.sources:      # the retrieved context, with provenance + score
    print(chunk.source, round(chunk.score, 3))
for message in answer.warnings:   # structured LibraryMessage warnings (e.g. echo fallback)
    print(message)
```

`run_dir` is a timestamped index directory produced by `VectorIndexer.run`.

## Design

### Chat models — one interface, graceful fallback

The application layer never depends on a specific LLM SDK. `resolve_chat_model`
maps a catalogued model id to a LangChain `BaseChatModel` through the umbrella
`langchain` package's `init_chat_model`, gating on the provider package and
credentials **before** construction so the offline path never touches the network.
When a requested cloud model is unavailable it falls back to the offline **echo**
model (which repeats the question instead of generating an answer) and appends a
warning, so the workflow always produces output. Credentials come **only** from
environment variables (`AWS_*`, `OPENAI_API_KEY`).

`CHAT_MODEL_OPTIONS` / `get_chat_model_info` expose the catalog (Bedrock, OpenAI,
echo) for a UI to render a model picker without constructing anything.

### Retrieval — reopen the exact index

`retrieve` reads the run `manifest.json` to learn which embedding model and
collection produced the vectors, rebuilds the matching embeddings with
`vector_indexer.resolve_embedding`, and runs the query through a `VectorSearcher`
— a small backend-neutral interface (`search.py`). Its only implementation,
`ChromaSearcher`, reopens the collection with the same `langchain_chroma.Chroma`
class the indexer wrote with (guaranteeing on-disk compatibility) and returns
plain `SearchHit`s, so no LangChain types leak across the boundary. Swapping
vector backends later means writing one new `VectorSearcher`, not touching the
pipeline. The embedding loader and `searcher_factory` are injectable so the flow
can be tested without ChromaDB or network access.

### Prompts — injection-defensive

Retrieved context is wrapped in `<context>` delimiters and the model is told to
treat it as data only and never follow instructions embedded inside it (see
`prompts.py`).

### Structured results

`answer_question` / `chat_answer` return a `RagAnswer` (answer text, source
chunks, `model_used`, and `warnings` / `errors` as
[`artifact_store.LibraryMessage`](../artifact_store/README.md) objects with stable
codes); `retrieve` returns a `RetrievalResult`. They never raise on expected
failures (missing index, unavailable model) — they record a structured error so a
UI can render it. Message codes/builders live in `rag_engine.messages`.

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | `RagConfig` (Pydantic v2): `llm_model`, `temperature`, `max_tokens`, `top_k`, `score_threshold`, `search_type`, `fetch_k`, `lambda_mult`, `source_filter` |
| `catalog.py` | `ChatModelInfo`, `CHAT_MODEL_OPTIONS`, `DEFAULT_CHAT_MODEL`, `ECHO_MODEL` |
| `llm/` | `resolve_chat_model` (init_chat_model + echo fallback), lazy echo model |
| `retrieval.py` | reopen a persisted index via a `VectorSearcher`, run similarity or MMR search with an optional source filter, and post-filter by score threshold (Step 3) |
| `search.py` | `VectorSearcher` interface + `ChromaSearcher` + backend-neutral `SearchHit` |
| `prompts.py` | QA + condense-question prompts, context formatting |
| `qa.py` | `answer_question` / `generate_answer` / `stream_answer` (Step 4) |
| `chat.py` | `chat_answer` / `condense_question` / `generate_chat_answer` (Step 5) |
| `models.py` | `RetrievedChunk`, `RagAnswer`, `ChatTurn` |
| `messages.py` | stable `rag.*` message codes + builders |

## Constraints

- **No UI / crawler imports.** `rag_engine` must not import `streamlit`,
  `crawl4md_streamlit`, or `crawl4md`. It may depend on `vector_indexer`,
  `artifact_store`, and `pydantic`. A boundary test enforces this.
- **Lazy heavy imports.** `langchain` (umbrella), `langchain_aws`,
  `langchain_openai`, and `langchain_chroma` are imported inside the functions
  that need them, so `import rag_engine` stays light.
