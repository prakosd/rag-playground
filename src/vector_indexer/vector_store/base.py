"""Abstract vector store interface.

The indexer depends only on this interface, never on a specific database, so the
backend (currently ChromaDB via langchain-chroma) can be replaced without
touching the orchestration. Embeddings are supplied to the concrete store at
construction; ``add_texts`` embeds and writes each batch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

__all__ = ["VectorStore"]


class VectorStore(ABC):
    """Stores embedded text chunks and persists them for later retrieval."""

    @abstractmethod
    def add_texts(
        self,
        texts: Sequence[str],
        metadatas: Sequence[dict[str, str]],
        ids: Sequence[str],
    ) -> None:
        """Embed and add a batch of chunks to the active collection."""

    @abstractmethod
    def persist(self) -> None:
        """Flush the collection to durable storage."""
