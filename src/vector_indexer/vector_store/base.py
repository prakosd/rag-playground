"""Abstract vector store interface.

The application and the indexer depend only on this interface, never on a
specific database, so the backend (currently ChromaDB) can be replaced without
touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from vector_indexer.models import VectorRecord

__all__ = ["VectorStore"]


class VectorStore(ABC):
    """Stores embedded chunks and persists them for later retrieval."""

    @abstractmethod
    def create_collection(self, name: str) -> None:
        """Create or open the named collection that records are added to."""

    @abstractmethod
    def add_documents(self, records: Sequence[VectorRecord]) -> None:
        """Add embedded chunk records to the active collection."""

    @abstractmethod
    def persist(self) -> None:
        """Flush the collection to durable storage."""
