# vector_indexer

UI-independent Python library that turns text documents into a persisted vector
index. It powers **Step 2 — Build Vector Index** in the Streamlit app, but it has
no Streamlit dependency and is equally usable from a notebook, a CLI, or tests.

## What it does

```
VectorIndexer.run(config, inputs, output_base)
  ├─ resolve_embedding()      → provider (+ Titan→offline fallback warnings)
  ├─ load_documents()         → .md / .txt files and .zip members (via artifact_store)
  ├─ chunk_documents()        → overlapping chunks (langchain-text-splitters)
  ├─ provider.embed_documents → vectors
  └─ VectorStore.add_documents / persist
        → vector_<id>/<timestamp>/chroma  +  manifest.json
```

The result is a structured `IndexingResult` (success flag, output directory,
indexed/skipped counts, warnings, errors) that any caller can render.

## Install

The backends are opt-in extras on the `crawl4md` distribution (the library ships
inside it):

```bash
pip install -e ".[vector]"            # chromadb + langchain-text-splitters
pip install -e ".[vector,bedrock]"    # + boto3 for Amazon Titan
pip install -e ".[vector,openai]"     # + openai
```

## Quick start

```python
from vector_indexer import IndexingConfig, VectorIndexer

config = IndexingConfig(
    chunk_size=600,
    chunk_overlap=100,
    embedding_model="amazon.titan-embed-text-v2:0",
    embedding_dimension=512,
    language="english",
)

indexer = VectorIndexer()
result = indexer.run(
    config,
    inputs=["outputs/.../final/sorted_success_content_001.md", "notes.zip"],
    output_base="outputs/.../vector_01_navigate",
)

print(result.success, result.indexed_chunk_count, result.warnings)
```

## Supported inputs

- `.md` and `.txt` files.
- `.zip` archives — only their `.md` / `.txt` members are indexed; everything else
  is ignored. Extraction is zip-slip-safe (handled by `artifact_store.archives`).

Unsupported or unreadable inputs are skipped and reported in `IndexingResult.warnings`.

## Embedding providers

The application layer never depends on a specific provider. `EmbeddingProvider`
(an ABC) has three implementations, selected by model id:

| Model id | Provider | Requirement |
|---|---|---|
| `amazon.titan-embed-text-v2:0` *(default)* | Amazon Bedrock Titan | `boto3` + AWS credentials |
| `text-embedding-3-small` | OpenAI | `openai` + `OPENAI_API_KEY` |
| `all-MiniLM-L6-v2` | Offline ONNX (ChromaDB) | none (downloads ~80 MB on first use) |
| `BAAI/bge-*`, `intfloat/e5-*`, `sentence-transformers/*` | listed but **disabled** | not installed (no PyTorch) |

**Graceful failure & fallback.** When a provider's dependency or credential is
missing, construction raises `EmbeddingProviderUnavailable`. The default model
(Titan) then **falls back to the offline model** and records a warning, so an
out-of-the-box run still succeeds. Other explicitly chosen but unavailable models
fail with a clear error instead of silently changing behavior.

## Credentials

Credentials are read only from the environment — never hardcoded:

- Amazon Titan: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`.
- OpenAI: `OPENAI_API_KEY`.

See [`.env.example`](../../.env.example). In Codespaces/CI, set them as
environment secrets/variables.

## Vector store

`VectorStore` (an ABC with `create_collection` / `add_documents` / `persist`) hides
the database. `ChromaVectorStore` is the default implementation; it writes a
persistent ChromaDB collection under `<run>/chroma/` and always receives explicit
embeddings, so ChromaDB never runs its own embedding model. Swapping in a different
backend only requires a new `VectorStore` implementation — callers do not change.

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | `IndexingConfig` (Pydantic v2 validation) |
| `models.py` | `Document`, `Chunk`, `VectorRecord`, `IndexingResult` |
| `languages.py` | `LUCENE_LANGUAGES`, `DEFAULT_LANGUAGE` |
| `document_loader.py` | load `.md` / `.txt` / `.zip` into documents |
| `chunking.py` | overlapping chunks via langchain-text-splitters |
| `embeddings/` | `EmbeddingProvider` interface, providers, registry, fallback policy |
| `vector_store/` | `VectorStore` interface and `ChromaVectorStore` |
| `indexer.py` | `VectorIndexer.run` orchestration |
