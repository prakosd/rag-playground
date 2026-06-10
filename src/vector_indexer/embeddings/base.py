"""Embedding provider interface and shared error type.

Concrete providers live in sibling modules and import their heavy or
credentialed dependencies lazily so that importing this package never requires
ChromaDB, boto3, or network access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

__all__ = ["EmbeddingProvider", "EmbeddingProviderUnavailable"]


class EmbeddingProviderUnavailable(RuntimeError):
    """Raised when a requested embedding model cannot be used.

    Typical causes are a missing optional dependency (for example boto3 for
    Amazon Titan) or absent credentials/configuration. Callers decide whether to
    fail or fall back to an offline default.
    """


class EmbeddingProvider(ABC):
    """Turns text into numerical vectors for similarity search."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Return the identifier of the embedding model in use."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the vectors this provider produces."""

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in order."""
