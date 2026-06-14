"""OpenAI text embeddings via langchain-openai.

The API key is read from ``OPENAI_API_KEY``. When langchain-openai is not
installed or the key is absent, the builder raises
``EmbeddingProviderUnavailable`` so callers can handle it gracefully.
"""

from __future__ import annotations

import importlib.util
import os

from vector_indexer.embeddings.base import EmbeddingProviderUnavailable, ResolvedEmbedding

__all__ = ["MIN_DIMENSION", "NATIVE_DIMENSION", "OPENAI_MODEL", "build_openai_embeddings"]

OPENAI_MODEL = "text-embedding-3-small"
MIN_DIMENSION = 1
NATIVE_DIMENSION = 1536


def build_openai_embeddings(*, dimension: int | None = None) -> ResolvedEmbedding:
    """Return OpenAI embeddings, or raise ``EmbeddingProviderUnavailable``."""
    if importlib.util.find_spec("langchain_openai") is None:
        raise EmbeddingProviderUnavailable(
            "langchain-openai is required for OpenAI embeddings; install the [openai] extra."
        )
    if not os.environ.get("OPENAI_API_KEY"):
        raise EmbeddingProviderUnavailable(
            "OPENAI_API_KEY is not configured for OpenAI embeddings."
        )
    resolved_dimension = dimension if dimension and dimension > 0 else NATIVE_DIMENSION

    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(model=OPENAI_MODEL, dimensions=resolved_dimension)
    return ResolvedEmbedding(
        embeddings=embeddings, model_id=OPENAI_MODEL, dimension=resolved_dimension
    )
