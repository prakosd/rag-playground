"""Offline default embeddings backed by ChromaDB's bundled ONNX MiniLM model.

This provider needs no credentials and no network beyond a one-time model
download performed by ChromaDB on first use. It does not require PyTorch.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from typing import Any

from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable

__all__ = ["DEFAULT_LOCAL_MODEL", "DefaultLocalEmbeddingProvider"]

DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
_LOCAL_DIMENSION = 384


class DefaultLocalEmbeddingProvider(EmbeddingProvider):
    """MiniLM-L6-v2 embeddings via ChromaDB's ONNX runtime (384 dimensions)."""

    def __init__(self) -> None:
        if importlib.util.find_spec("chromadb") is None:
            raise EmbeddingProviderUnavailable(
                "ChromaDB is required for offline embeddings; install chromadb."
            )
        self._embedder: Any = None

    @property
    def model_id(self) -> str:
        return DEFAULT_LOCAL_MODEL

    @property
    def dimension(self) -> int:
        return _LOCAL_DIMENSION

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        embedder = self._ensure_embedder()
        vectors = embedder(list(texts))
        return [[float(value) for value in vector] for vector in vectors]

    def _ensure_embedder(self) -> Any:
        if self._embedder is None:
            from chromadb.utils import embedding_functions

            self._embedder = embedding_functions.ONNXMiniLM_L6_V2()
        return self._embedder
