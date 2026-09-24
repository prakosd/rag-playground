"""Vector store interface and built-in implementations."""

from __future__ import annotations

from vector_indexer.vector_store.base import VectorStore
from vector_indexer.vector_store.chroma import ChromaVectorStore

__all__ = ["ChromaVectorStore", "VectorStore"]
