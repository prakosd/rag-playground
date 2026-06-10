"""Embedding provider registry and resolution policy.

This package keeps the application layer independent of any specific embedding
backend. ``build_embedding_provider`` maps a model id to a concrete provider,
and ``resolve_embedding`` applies the default-model fallback policy.
"""

from __future__ import annotations

from collections.abc import Callable

from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable
from vector_indexer.embeddings.local import DEFAULT_LOCAL_MODEL
from vector_indexer.embeddings.openai import OPENAI_MODEL
from vector_indexer.embeddings.titan import TITAN_MODEL

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_LOCAL_MODEL",
    "DISABLED_MODELS",
    "EMBEDDING_MODEL_OPTIONS",
    "OPENAI_MODEL",
    "TITAN_MODEL",
    "EmbeddingProvider",
    "EmbeddingProviderUnavailable",
    "build_default_local_provider",
    "build_embedding_provider",
    "resolve_embedding",
]

DEFAULT_EMBEDDING_MODEL = TITAN_MODEL

# Listed in the UI but not enabled in this build: they require local model
# dependencies (PyTorch / sentence-transformers) that are intentionally not
# installed. Selecting one fails gracefully with guidance.
DISABLED_MODELS: tuple[str, ...] = (
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/all-mpnet-base-v2",
    "intfloat/e5-small-v2",
    "intfloat/e5-base-v2",
)

EMBEDDING_MODEL_OPTIONS: tuple[str, ...] = (
    TITAN_MODEL,
    OPENAI_MODEL,
    DEFAULT_LOCAL_MODEL,
    *DISABLED_MODELS,
)


def build_default_local_provider(*, dimension: int | None = None) -> EmbeddingProvider:
    """Return the offline default embedding provider."""
    from vector_indexer.embeddings.local import DefaultLocalEmbeddingProvider

    return DefaultLocalEmbeddingProvider()


def build_embedding_provider(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
    """Return a provider for *model*, or raise ``EmbeddingProviderUnavailable``."""
    normalized = model.strip()
    if normalized == TITAN_MODEL:
        from vector_indexer.embeddings.titan import TitanEmbeddingProvider

        return TitanEmbeddingProvider(dimension=dimension)
    if normalized == OPENAI_MODEL:
        from vector_indexer.embeddings.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(dimension=dimension)
    if normalized == DEFAULT_LOCAL_MODEL:
        return build_default_local_provider(dimension=dimension)
    if normalized in DISABLED_MODELS:
        raise EmbeddingProviderUnavailable(
            f"Embedding model {normalized!r} is listed but not enabled in this build. "
            "It requires local model dependencies that are not installed."
        )
    raise EmbeddingProviderUnavailable(f"Unknown embedding model {normalized!r}.")


def resolve_embedding(
    model: str,
    dimension: int | None,
    *,
    build: Callable[..., EmbeddingProvider] = build_embedding_provider,
    default_build: Callable[..., EmbeddingProvider] = build_default_local_provider,
) -> tuple[EmbeddingProvider, list[str]]:
    """Resolve an embedding provider, applying the default-model fallback policy.

    When the default model (Amazon Titan) is requested but unavailable, this
    falls back to the offline default provider and returns a warning. Other
    unavailable models raise ``EmbeddingProviderUnavailable`` for the caller to
    surface as an error.
    """
    warnings: list[str] = []
    try:
        provider = build(model, dimension=dimension)
    except EmbeddingProviderUnavailable as exc:
        if model.strip() != DEFAULT_EMBEDDING_MODEL:
            raise
        provider = default_build(dimension=dimension)
        warnings.append(f"{exc} Falling back to offline embeddings ({DEFAULT_LOCAL_MODEL}).")
    if dimension is not None and provider.dimension != dimension:
        warnings.append(
            f"Requested embedding dimension {dimension} is not supported by "
            f"{provider.model_id!r}; using {provider.dimension}."
        )
    return provider, warnings
