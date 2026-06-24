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
from collections.abc import Sequence
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
    def search(
        self,
        query: str,
        k: int,
        *,
        search_type: str = "similarity",
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        source_filter: Sequence[str] = (),
    ) -> list[SearchHit]:
        """Return up to *k* nearest-neighbour hits for *query*, closest first.

        *search_type* is ``"similarity"`` or ``"mmr"`` (max-marginal-relevance,
        diversifying the *k* results from *fetch_k* candidates by *lambda_mult*).
        *source_filter*, when non-empty, restricts hits to those source files.
        """


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

    def search(
        self,
        query: str,
        k: int,
        *,
        search_type: str = "similarity",
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        source_filter: Sequence[str] = (),
    ) -> list[SearchHit]:
        store = self._ensure_store()
        where = _build_source_filter(source_filter)
        if search_type == "mmr":
            return _mmr_hits(store, query, k, fetch_k, lambda_mult, where)
        return _similarity_hits(store, query, k, where)

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


def _build_source_filter(source_filter: Sequence[str]) -> dict[str, Any] | None:
    """Build a Chroma metadata ``where`` clause restricting to given sources."""
    sources = [source for source in source_filter if source]
    if not sources:
        return None
    if len(sources) == 1:
        return {"source": sources[0]}
    return {"source": {"$in": sources}}


def _similarity_hits(
    store: Any, query: str, k: int, where: dict[str, Any] | None
) -> list[SearchHit]:
    hits = store.similarity_search_with_score(query, k=k, filter=where)
    return [_to_hit(document, distance) for document, distance in hits]


def _mmr_hits(
    store: Any,
    query: str,
    k: int,
    fetch_k: int,
    lambda_mult: float,
    where: dict[str, Any] | None,
) -> list[SearchHit]:
    documents = store.max_marginal_relevance_search(
        query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult, filter=where
    )
    # MMR returns documents without scores; recover each result's distance from
    # the scored candidate pool it was selected from (worst seen as fallback).
    scored = store.similarity_search_with_score(query, k=fetch_k, filter=where)
    distances = {_doc_key(document): float(distance) for document, distance in scored}
    worst = max((distance for _, distance in scored), default=0.0)
    return [_to_hit(document, distances.get(_doc_key(document), worst)) for document in documents]


def _doc_key(document: Any) -> tuple[str, str]:
    """Return a stable identity for a document to join MMR results to distances."""
    return (str(document.metadata.get("source", "")), document.page_content)


def _to_hit(document: Any, distance: float) -> SearchHit:
    """Convert a backend document + distance to a backend-neutral SearchHit."""
    return SearchHit(
        text=document.page_content,
        source=str(document.metadata.get("source", "")),
        distance=float(distance),
        metadata={str(key): str(value) for key, value in document.metadata.items()},
    )
