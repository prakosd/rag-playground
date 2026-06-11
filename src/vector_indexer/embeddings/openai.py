"""OpenAI text embeddings.

The API key is read from ``OPENAI_API_KEY``. When the ``openai`` package is not
installed or the key is absent, construction raises
``EmbeddingProviderUnavailable`` so callers can handle it gracefully.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Sequence
from typing import Any

from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable

__all__ = ["MIN_DIMENSION", "NATIVE_DIMENSION", "OPENAI_MODEL", "OpenAIEmbeddingProvider"]

OPENAI_MODEL = "text-embedding-3-small"
MIN_DIMENSION = 1
NATIVE_DIMENSION = 1536


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeds text with an OpenAI embedding model."""

    def __init__(self, *, dimension: int | None = None) -> None:
        if importlib.util.find_spec("openai") is None:
            raise EmbeddingProviderUnavailable(
                "The openai package is required for OpenAI embeddings; install the [openai] extra."
            )
        if not os.environ.get("OPENAI_API_KEY"):
            raise EmbeddingProviderUnavailable(
                "OPENAI_API_KEY is not configured for OpenAI embeddings."
            )
        self._dimension = dimension if dimension and dimension > 0 else NATIVE_DIMENSION
        self._client: Any = None

    @property
    def model_id(self) -> str:
        return OPENAI_MODEL

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._ensure_client()
        response = client.embeddings.create(
            model=OPENAI_MODEL,
            input=list(texts),
            dimensions=self._dimension,
        )
        return [[float(value) for value in item.embedding] for item in response.data]

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client
