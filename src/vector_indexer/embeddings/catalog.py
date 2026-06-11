"""Static metadata catalog for the embedding models offered in the UI.

This module lets callers (such as a UI) discover how each model behaves —
whether it runs locally or in the cloud, whether it needs an API key, and which
embedding dimensions it supports — *without* constructing a provider or touching
any network. Dimension facts are imported from the provider modules so this
catalog stays a single source of truth rather than duplicating those values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vector_indexer.embeddings.local import DEFAULT_LOCAL_MODEL, LOCAL_DIMENSION
from vector_indexer.embeddings.openai import MIN_DIMENSION as OPENAI_MIN_DIMENSION
from vector_indexer.embeddings.openai import NATIVE_DIMENSION as OPENAI_NATIVE_DIMENSION
from vector_indexer.embeddings.openai import OPENAI_MODEL
from vector_indexer.embeddings.titan import DEFAULT_DIMENSION as TITAN_DEFAULT_DIMENSION
from vector_indexer.embeddings.titan import SUPPORTED_DIMENSIONS as TITAN_SUPPORTED_DIMENSIONS
from vector_indexer.embeddings.titan import TITAN_MODEL

__all__ = ["EMBEDDING_MODEL_INFOS", "EmbeddingModelInfo", "get_embedding_model_info"]

ModelKind = Literal["local", "cloud"]


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """Describes how an embedding model behaves, for display and input limits.

    ``supported_dimensions`` holds the discrete dimensions a model accepts; when
    it is ``None`` the model accepts any value in ``[min_dimension, max_dimension]``.
    """

    model_id: str
    kind: ModelKind
    default_dimension: int
    supported_dimensions: tuple[int, ...] | None = None
    min_dimension: int | None = None
    max_dimension: int | None = None
    requires_api_key: bool = False
    one_time_download: bool = False


EMBEDDING_MODEL_INFOS: tuple[EmbeddingModelInfo, ...] = (
    EmbeddingModelInfo(
        model_id=TITAN_MODEL,
        kind="cloud",
        default_dimension=TITAN_DEFAULT_DIMENSION,
        supported_dimensions=TITAN_SUPPORTED_DIMENSIONS,
        min_dimension=min(TITAN_SUPPORTED_DIMENSIONS),
        max_dimension=max(TITAN_SUPPORTED_DIMENSIONS),
        requires_api_key=True,
    ),
    EmbeddingModelInfo(
        model_id=OPENAI_MODEL,
        kind="cloud",
        default_dimension=OPENAI_NATIVE_DIMENSION,
        supported_dimensions=None,
        min_dimension=OPENAI_MIN_DIMENSION,
        max_dimension=OPENAI_NATIVE_DIMENSION,
        requires_api_key=True,
    ),
    EmbeddingModelInfo(
        model_id=DEFAULT_LOCAL_MODEL,
        kind="local",
        default_dimension=LOCAL_DIMENSION,
        supported_dimensions=(LOCAL_DIMENSION,),
        min_dimension=LOCAL_DIMENSION,
        max_dimension=LOCAL_DIMENSION,
        requires_api_key=False,
        one_time_download=True,
    ),
)

_INFO_BY_ID = {info.model_id: info for info in EMBEDDING_MODEL_INFOS}


def get_embedding_model_info(model_id: str) -> EmbeddingModelInfo | None:
    """Return metadata for *model_id*, or ``None`` when it is not catalogued."""
    return _INFO_BY_ID.get(model_id.strip())
