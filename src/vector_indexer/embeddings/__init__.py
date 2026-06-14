"""Embedding registry and resolution policy.

This package keeps the application layer independent of any specific embedding
backend. ``build_embeddings`` maps a model id to a concrete LangChain
``Embeddings`` client (wrapped in :class:`ResolvedEmbedding`), and
``resolve_embedding`` applies the default-model fallback policy.
"""

from __future__ import annotations

from collections.abc import Callable

from artifact_store import LibraryMessage
from vector_indexer import messages
from vector_indexer.embeddings.base import EmbeddingProviderUnavailable, ResolvedEmbedding
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
    "EmbeddingProviderUnavailable",
    "ResolvedEmbedding",
    "build_default_local_embeddings",
    "build_embeddings",
    "get_embedding_model_info",
    "resolve_embedding",
]

DEFAULT_EMBEDDING_MODEL = TITAN_MODEL

# Known model ids that require local model dependencies (PyTorch /
# sentence-transformers) that are intentionally not installed. They are not
# offered in the UI; if one is requested programmatically, the build fails
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


def build_default_local_embeddings(*, dimension: int | None = None) -> ResolvedEmbedding:
    """Return the offline default embeddings."""
    from vector_indexer.embeddings.local import build_local_embeddings

    return build_local_embeddings(dimension=dimension)


def build_embeddings(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
    """Return embeddings for *model*, or raise ``EmbeddingProviderUnavailable``."""
    normalized = model.strip()
    if normalized == TITAN_MODEL:
        from vector_indexer.embeddings.titan import build_titan_embeddings

        return build_titan_embeddings(dimension=dimension)
    if normalized == OPENAI_MODEL:
        from vector_indexer.embeddings.openai import build_openai_embeddings

        return build_openai_embeddings(dimension=dimension)
    if normalized == DEFAULT_LOCAL_MODEL:
        return build_default_local_embeddings(dimension=dimension)
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
    build: Callable[..., ResolvedEmbedding] = build_embeddings,
    default_build: Callable[..., ResolvedEmbedding] = build_default_local_embeddings,
) -> tuple[ResolvedEmbedding, list[LibraryMessage]]:
    """Resolve embeddings, falling back to the local offline model.

    When the requested model is unavailable (missing dependency or credential),
    this falls back to the local offline embeddings and returns a warning so the
    run still succeeds. It raises ``EmbeddingProviderUnavailable`` only when the
    local model itself was requested and is unavailable (re-raising that error),
    or when the local fallback is also unavailable (a combined error), so the
    caller can surface it.
    """
    warnings: list[LibraryMessage] = []
    try:
        resolved = build(model, dimension=dimension)
    except EmbeddingProviderUnavailable as exc:
        if model.strip() == DEFAULT_LOCAL_MODEL:
            raise
        try:
            resolved = default_build(dimension=dimension)
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
    if dimension is not None and resolved.dimension != dimension:
        warnings.append(
            messages.dimension_mismatch(
                requested_dimension=dimension,
                model=resolved.model_id,
                actual_dimension=resolved.dimension,
            )
        )
    return resolved, warnings
