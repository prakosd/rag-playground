"""Offline default embeddings backed by ChromaDB's bundled ONNX MiniLM model.

This provider needs no credentials and no network beyond a one-time model
download performed by ChromaDB on first use. It does not require PyTorch.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Sequence
from typing import Any

from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable

__all__ = ["DEFAULT_LOCAL_MODEL", "LOCAL_DIMENSION", "DefaultLocalEmbeddingProvider"]

DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
LOCAL_DIMENSION = 384
_CA_BUNDLE_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


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
        return LOCAL_DIMENSION

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        embedder = self._ensure_embedder()
        vectors = embedder(list(texts))
        return [[float(value) for value in vector] for vector in vectors]

    def _ensure_embedder(self) -> Any:
        if self._embedder is None:
            _propagate_ca_bundle_env()
            from chromadb.utils import embedding_functions

            self._embedder = embedding_functions.ONNXMiniLM_L6_V2()
        return self._embedder


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
