"""Configuration model for a vector indexing run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from vector_indexer.embeddings import DEFAULT_EMBEDDING_MODEL
from vector_indexer.languages import DEFAULT_LANGUAGE, is_supported_language

__all__ = ["IndexingConfig"]

_DEFAULT_CHUNK_SIZE = 600
_DEFAULT_CHUNK_OVERLAP = 100
_DEFAULT_EMBEDDING_DIMENSION = 512
_DEFAULT_INDEX_WORKERS = 4
_MAX_INDEX_WORKERS = 8


class IndexingConfig(BaseModel):
    """User-supplied parameters that control chunking and embedding."""

    chunk_size: int = _DEFAULT_CHUNK_SIZE
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = _DEFAULT_EMBEDDING_DIMENSION
    language: str = DEFAULT_LANGUAGE
    index_workers: int = _DEFAULT_INDEX_WORKERS

    @field_validator("chunk_size", "embedding_dimension")
    @classmethod
    def _require_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be at least 1.")
        return value

    @field_validator("index_workers")
    @classmethod
    def _require_worker_range(cls, value: int) -> int:
        if not 1 <= value <= _MAX_INDEX_WORKERS:
            raise ValueError(f"index_workers must be between 1 and {_MAX_INDEX_WORKERS}.")
        return value

    @field_validator("chunk_overlap")
    @classmethod
    def _require_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Chunk overlap must not be negative.")
        return value

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        if not is_supported_language(value):
            raise ValueError(f"Unsupported language: {value!r}.")
        return value

    @model_validator(mode="after")
    def _check_overlap(self) -> IndexingConfig:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self
