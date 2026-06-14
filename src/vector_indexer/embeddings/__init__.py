"""Embedding provider registry and resolution policy.

This package keeps the application layer independent of any specific embedding
backend. ``build_embedding_provider`` maps a model id to a concrete provider,
and ``resolve_embedding`` applies the default-model fallback policy.
"""

from __future__ import annotations

from collections.abc import Callable

from artifact_store import LibraryMessage
from vector_indexer import messages
from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable
from vector_indexer.embeddings.catalog import (
    EMBEDDING_MODEL_INFOS,
    EmbeddingModelInfo,
    get_embedding_model_info,
)
from vector_indexer.embeddings.local import DEFAULT_LOCAL_MODEL
from vector_indexer.embeddings.openai import OPENAI_MODEL
from vector_indexer.embeddings.titan import TITAN_MODEL

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_LOCAL_MODEL",
    "DISABLED_MODELS",
    "EMBEDDING_MODEL_INFOS",
    "EMBEDDING_MODEL_OPTIONS",
    "OPENAI_MODEL",
    "TITAN_MODEL",
    "EmbeddingModelInfo",
    "EmbeddingProvider",
    "EmbeddingProviderUnavailable",
    "build_default_local_provider",
    "build_embedding_provider",
    "get_embedding_model_info",
    "resolve_embedding",
]

DEFAULT_EMBEDDING_MODEL = TITAN_MODEL

# Known model ids that require local model dependencies (PyTorch /
# sentence-transformers) that are intentionally not installed. They are not
# offered in the UI; if one is requested programmatically, construction fails
# gracefully and resolution falls back to the local offline model.
DISABLED_MODELS: tuple[str, ...] = (
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/all-mpnet-base-v2",
    "intfloat/e5-small-v2",
    "intfloat/e5-base-v2",
)

# Runnable models offered in the UI. Any other (or failed) model resolves to the
# local offline model via ``resolve_embedding``.
EMBEDDING_MODEL_OPTIONS: tuple[str, ...] = (
    TITAN_MODEL,
    OPENAI_MODEL,
    DEFAULT_LOCAL_MODEL,
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
) -> tuple[EmbeddingProvider, list[LibraryMessage]]:
    """Resolve an embedding provider, falling back to the local offline model.

    When the requested model is unavailable (missing dependency or credential),
    this falls back to the local offline provider and returns a warning so the
    run still succeeds. It raises ``EmbeddingProviderUnavailable`` only when the
    local model itself was requested and is unavailable (re-raising that error),
    or when the local fallback is also unavailable (a combined error), so the
    caller can surface it.
    """
    warnings: list[LibraryMessage] = []
    try:
        provider = build(model, dimension=dimension)
    except EmbeddingProviderUnavailable as exc:
        if model.strip() == DEFAULT_LOCAL_MODEL:
            raise
        try:
            provider = default_build(dimension=dimension)
        except EmbeddingProviderUnavailable as fallback_exc:
            raise EmbeddingProviderUnavailable(
                f"{exc} The local offline model ({DEFAULT_LOCAL_MODEL}) is also "
                f"unavailable: {fallback_exc}"
            ) from fallback_exc
        warnings.append(
            messages.embedding_fallback(
                requested_model=model.strip(),
                local_model=DEFAULT_LOCAL_MODEL,
                detail=str(exc),
            )
        )
    if dimension is not None and provider.dimension != dimension:
        warnings.append(
            messages.dimension_mismatch(
                requested_dimension=dimension,
                model=provider.model_id,
                actual_dimension=provider.dimension,
            )
        )
    return provider, warnings
