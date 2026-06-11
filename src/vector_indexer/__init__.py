"""UI-independent library for building vector indexes from text documents.

The library loads ``.md``/``.txt`` files and ``.zip`` archives, splits them into
overlapping chunks, embeds the chunks with a configurable provider, and persists
them to a vector store behind an interface. It does not depend on Streamlit or
any other UI.
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
    get_embedding_model_info,
)
from vector_indexer.indexer import VectorIndexer
from vector_indexer.languages import DEFAULT_LANGUAGE, LUCENE_LANGUAGES
from vector_indexer.models import IndexingResult

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_LANGUAGE",
    "DEFAULT_LOCAL_MODEL",
    "EMBEDDING_MODEL_INFOS",
    "EMBEDDING_MODEL_OPTIONS",
    "LUCENE_LANGUAGES",
    "EmbeddingModelInfo",
    "EmbeddingProviderUnavailable",
    "IndexingConfig",
    "IndexingResult",
    "VectorIndexer",
    "get_embedding_model_info",
]
