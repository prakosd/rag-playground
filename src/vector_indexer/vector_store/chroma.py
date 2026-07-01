"""ChromaDB-backed vector store via langchain-chroma.

langchain-chroma (and chromadb) are imported lazily so importing
:mod:`vector_indexer` stays light. The same ``langchain_chroma.Chroma`` class is
used by the retrieval layer to reopen the persisted collection, which guarantees
the on-disk format matches. Embeddings are supplied at construction so the
collection can be reopened for querying; write batches arrive already embedded
via ``add_embeddings`` (the indexer embeds them, in parallel for cloud models).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vector_indexer.vector_store.base import VectorStore

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["ChromaVectorStore"]


class ChromaVectorStore(VectorStore):
    """Persists embedded chunks to an on-disk ChromaDB collection."""

    def __init__(
        self,
        persist_dir: Path | str,
        collection_name: str,
        embeddings: Embeddings,
    ) -> None:
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name
        self._embeddings = embeddings
        self._store: Any = None

    def add_embeddings(
        self,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, str]],
        ids: Sequence[str],
    ) -> None:
        if not texts:
            return
        store = self._ensure_store()
        # Write the pre-computed vectors straight to the underlying collection so
        # the model is never re-invoked here; the indexer already embedded this
        # batch (in parallel for cloud models) and serializes these writes.
        store._collection.upsert(
            ids=list(ids),
            embeddings=[list(vector) for vector in embeddings],
            documents=list(texts),
            metadatas=list(metadatas),
        )

    def persist(self) -> None:
        # langchain-chroma uses a PersistentClient that writes eagerly.
        return None

    def _ensure_store(self) -> Any:
        if self._store is None:
            try:
                from chromadb.config import Settings
                from langchain_chroma import Chroma
            except ImportError as exc:  # pragma: no cover - exercised only without the dep
                raise RuntimeError(
                    "langchain-chroma is required for the vector store; "
                    'install it with: pip install "rag-playground[vector]"'
                ) from exc
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._store = Chroma(
                collection_name=self._collection_name,
                embedding_function=self._embeddings,
                persist_directory=str(self._persist_dir),
                client_settings=Settings(anonymized_telemetry=False),
            )
        return self._store
