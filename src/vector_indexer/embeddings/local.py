"""Offline default embeddings backed by ChromaDB's bundled ONNX MiniLM model.

Wrapped as a LangChain ``Embeddings`` implementation so the indexer and the
retrieval layer treat every backend uniformly. Needs no credentials and no
network beyond a one-time model download ChromaDB performs on first use; it does
not require PyTorch. The ``Embeddings`` subclass is defined lazily so importing
this module (for its constants) does not pull langchain-core or chromadb.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

from vector_indexer.embeddings.base import EmbeddingProviderUnavailable, ResolvedEmbedding

__all__ = ["DEFAULT_LOCAL_MODEL", "LOCAL_DIMENSION", "build_local_embeddings"]

DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
LOCAL_DIMENSION = 384
_CA_BUNDLE_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")

_embeddings_cls: type | None = None


def build_local_embeddings(*, dimension: int | None = None) -> ResolvedEmbedding:
    """Return the offline default embeddings, or raise if ChromaDB is missing."""
    if importlib.util.find_spec("chromadb") is None:
        raise EmbeddingProviderUnavailable(
            "ChromaDB is required for offline embeddings; install the [vector] extra."
        )
    cls = _local_embeddings_class()
    return ResolvedEmbedding(
        embeddings=cls(), model_id=DEFAULT_LOCAL_MODEL, dimension=LOCAL_DIMENSION
    )


def _local_embeddings_class() -> type:
    """Build (once) and return the ``Embeddings`` subclass over the ONNX model."""
    global _embeddings_cls
    if _embeddings_cls is not None:
        return _embeddings_cls

    from langchain_core.embeddings import Embeddings

    class LocalOnnxEmbeddings(Embeddings):
        """MiniLM-L6-v2 embeddings via ChromaDB's ONNX runtime (384 dimensions)."""

        def __init__(self) -> None:
            self._embedder: Any = None

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            embedder = self._ensure_embedder()
            return [[float(value) for value in vector] for vector in embedder(list(texts))]

        def embed_query(self, text: str) -> list[float]:
            return self.embed_documents([text])[0]

        def _ensure_embedder(self) -> Any:
            if self._embedder is None:
                _propagate_ca_bundle_env()
                from chromadb.utils import embedding_functions

                self._embedder = embedding_functions.ONNXMiniLM_L6_V2()
            return self._embedder

    _embeddings_cls = LocalOnnxEmbeddings
    return _embeddings_cls


def _propagate_ca_bundle_env() -> None:
    """Mirror a configured CA bundle path across the common SSL env vars.

    Corporate networks often intercept TLS with a private root CA. ChromaDB does
    a one-time HTTPS download of the ONNX model on first use; honoring a
    user-provided CA bundle (via any standard variable) lets that download
    succeed. This only copies an existing path to the unset siblings and never
    overrides a value the user already set.
    """
    configured = next(
        (
            os.environ[name]
            for name in _CA_BUNDLE_ENV_VARS
            if os.environ.get(name) and os.path.isfile(os.environ[name])
        ),
        None,
    )
    if configured is None:
        return
    for name in _CA_BUNDLE_ENV_VARS:
        os.environ.setdefault(name, configured)
