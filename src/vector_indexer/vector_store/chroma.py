"""ChromaDB-backed vector store.

ChromaDB is imported lazily so that importing :mod:`vector_indexer` does not
require it. Embeddings are always supplied explicitly, so ChromaDB never invokes
its own embedding function (and never downloads a model on its own).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vector_indexer.models import VectorRecord
from vector_indexer.vector_store.base import VectorStore

__all__ = ["ChromaVectorStore"]


class ChromaVectorStore(VectorStore):
    """Persists embedded chunks to an on-disk ChromaDB collection."""

    def __init__(self, persist_dir: Path | str) -> None:
        self._persist_dir = Path(persist_dir)
        self._client: Any = None
        self._collection: Any = None

    def create_collection(self, name: str) -> None:
        client = self._ensure_client()
        self._collection = client.get_or_create_collection(name=name)

    def add_documents(self, records: Sequence[VectorRecord]) -> None:
        if self._collection is None:
            raise RuntimeError("create_collection must be called before add_documents.")
        if not records:
            return
        self._collection.add(
            ids=[record.id for record in records],
            documents=[record.text for record in records],
            embeddings=[record.embedding for record in records],
            metadatas=[record.metadata for record in records],
        )

    def persist(self) -> None:
        # PersistentClient writes eagerly; there is nothing extra to flush.
        return None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError as exc:  # pragma: no cover - exercised only without the dep
                raise RuntimeError(
                    "chromadb is required for the Chroma vector store; install it."
                ) from exc
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self._persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client
