"""UI-independent library for building vector indexes from text documents.

The library loads ``.md``/``.txt`` files and ``.zip`` archives, splits them into
overlapping chunks, embeds the chunks with a configurable LangChain embeddings
backend, and persists them to a ChromaDB collection via langchain-chroma. It does
not depend on Streamlit or any other UI. The retrieval layer (``rag_engine``)
reopens an index from its run directory using ``load_manifest`` plus
``resolve_embedding``.
"""

from __future__ import annotations

from vector_indexer.config import IndexingConfig
from vector_indexer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LOCAL_MODEL,
    EMBEDDING_MODEL_INFOS,
    EMBEDDING_MODEL_OPTIONS,
    EmbeddingModelInfo,
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    build_embeddings,
    get_embedding_model_info,
    resolve_embedding,
)
from vector_indexer.indexer import VectorIndexer
from vector_indexer.languages import DEFAULT_LANGUAGE, LUCENE_LANGUAGES
from vector_indexer.manifest import (
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION_NAME,
    IndexManifest,
    load_manifest,
)
from vector_indexer.models import IndexingResult

__all__ = [
    "CHROMA_SUBDIR",
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_LANGUAGE",
    "DEFAULT_LOCAL_MODEL",
    "EMBEDDING_MODEL_INFOS",
    "EMBEDDING_MODEL_OPTIONS",
    "LUCENE_LANGUAGES",
    "EmbeddingModelInfo",
    "EmbeddingProviderUnavailable",
    "IndexManifest",
    "IndexingConfig",
    "IndexingResult",
    "ResolvedEmbedding",
    "VectorIndexer",
    "build_embeddings",
    "get_embedding_model_info",
    "load_manifest",
    "resolve_embedding",
]
