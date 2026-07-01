"""Abstract vector store interface.

The indexer depends only on this interface, never on a specific database, so the
backend (currently ChromaDB via langchain-chroma) can be replaced without
touching the orchestration. The indexer embeds each batch and passes the vectors
to ``add_embeddings``; the concrete store still receives an embeddings client at
construction so the persisted collection can be reopened for querying.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

__all__ = ["VectorStore"]


class VectorStore(ABC):
    """Stores embedded text chunks and persists them for later retrieval."""

    @abstractmethod
    def add_embeddings(
        self,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, str]],
        ids: Sequence[str],
    ) -> None:
        """Write a batch of pre-embedded chunks to the active collection."""

    @abstractmethod
    def persist(self) -> None:
        """Flush the collection to durable storage."""
