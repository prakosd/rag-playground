"""Embedding registry and resolution policy.

This package keeps the application layer independent of any specific embedding
backend. ``build_embeddings`` maps a model id to a concrete LangChain
``Embeddings`` client (wrapped in :class:`ResolvedEmbedding`), and
``resolve_embedding`` returns it with any non-fatal warnings, raising
``EmbeddingProviderUnavailable`` when the requested model cannot be used.
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
# gracefully with ``EmbeddingProviderUnavailable`` (never importing torch).
DISABLED_MODELS: tuple[str, ...] = (
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/all-mpnet-base-v2",
    "intfloat/e5-small-v2",
    "intfloat/e5-base-v2",
)

# Runnable models offered in the UI. The local offline model needs no
# credentials; cloud models raise ``EmbeddingProviderUnavailable`` when their
# package or credential is missing, which the caller surfaces as an error.
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
) -> tuple[ResolvedEmbedding, list[LibraryMessage]]:
    """Resolve embeddings for *model*, plus any non-fatal warnings.

    Raises ``EmbeddingProviderUnavailable`` when the requested model cannot be
    used (a missing provider package or credential). There is no automatic
    fallback to the local offline model: a failed cloud model surfaces an
    actionable error rather than silently switching backends, so the caller can
    record it and recommend the local offline model. The only warning today is a
    dimension-mismatch notice when a model ignores the requested dimension.
    """
    resolved = build(model, dimension=dimension)
    warnings: list[LibraryMessage] = []
    if dimension is not None and resolved.dimension != dimension:
        warnings.append(
            messages.dimension_mismatch(
                requested_dimension=dimension,
                model=resolved.model_id,
                actual_dimension=resolved.dimension,
            )
        )
    return resolved, warnings
