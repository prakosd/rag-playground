"""Backend-neutral vector search seam for retrieval (Step 3).

``retrieve`` depends on the abstract :class:`VectorSearcher` rather than on any
specific vector store, so moving off ChromaDB/LangChain later means writing one
new ``VectorSearcher`` instead of touching the retrieval pipeline. The only
concrete implementation, :class:`ChromaSearcher`, keeps its heavy
``langchain_chroma``/``chromadb`` imports inside its methods so ``import
rag_engine`` stays light, and it returns plain :class:`SearchHit` objects so no
backend-specific types (e.g. LangChain ``Document``) cross the interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vector_indexer import CHROMA_SUBDIR, load_manifest

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["ChromaSearcher", "SearchHit", "VectorSearcher", "open_searcher"]


@dataclass(frozen=True)
class SearchHit:
    """One nearest-neighbour match from a vector search, backend-neutral.

    ``distance`` is the store's raw distance (lower = closer); the retrieval
    layer maps it to a 0-1 similarity. ``metadata`` is stringified so no
    backend-specific value types leak across the interface.
    """

    text: str
    source: str
    distance: float
    metadata: dict[str, str]


class VectorSearcher(ABC):
    """Runs similarity search over a persisted index, independent of backend."""

    @abstractmethod
    def search(self, query: str, k: int) -> list[SearchHit]:
        """Return up to *k* nearest-neighbour hits for *query*, closest first."""


class ChromaSearcher(VectorSearcher):
    """:class:`VectorSearcher` backed by the langchain-chroma store the indexer wrote.

    The store is opened lazily on first search (and may be injected for tests).
    """

    def __init__(
        self,
        run_dir: Path | str,
        embeddings: Embeddings,
        *,
        store: Any | None = None,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._embeddings = embeddings
        self._store = store

    def search(self, query: str, k: int) -> list[SearchHit]:
        store = self._ensure_store()
        hits = store.similarity_search_with_score(query, k=k)
        return [
            SearchHit(
                text=document.page_content,
                source=str(document.metadata.get("source", "")),
                distance=float(distance),
                metadata={str(key): str(value) for key, value in document.metadata.items()},
            )
            for document, distance in hits
        ]

    def _ensure_store(self) -> Any:
        if self._store is None:
            from chromadb.config import Settings
            from langchain_chroma import Chroma

            manifest = load_manifest(self._run_dir)
            self._store = Chroma(
                collection_name=manifest.collection_name,
                embedding_function=self._embeddings,
                persist_directory=str(self._run_dir / CHROMA_SUBDIR),
                client_settings=Settings(anonymized_telemetry=False),
            )
        return self._store


def open_searcher(run_dir: Path | str, embeddings: Embeddings) -> VectorSearcher:
    """Return the default :class:`VectorSearcher` (ChromaDB) for *run_dir*."""
    return ChromaSearcher(run_dir, embeddings)
