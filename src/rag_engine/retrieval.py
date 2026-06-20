"""Open a persisted vector index and run similarity search over it (Step 3).

The index is reopened with the *same* embedding model that wrote it (read from
the run manifest) through a :class:`~rag_engine.search.VectorSearcher`, so the
retrieval pipeline never touches a specific vector store directly. Heavy imports
(langchain-chroma, chromadb) stay inside the searcher that needs them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from artifact_store import LibraryMessage
from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.models import RetrievedChunk
from rag_engine.search import VectorSearcher, open_searcher
from vector_indexer import (
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    load_manifest,
    resolve_embedding,
)

__all__ = ["RetrievalResult", "load_index_embeddings", "retrieve"]


@dataclass
class RetrievalResult:
    """Chunks returned by a search plus any structured warnings/errors."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)


def load_index_embeddings(
    run_dir: Path | str,
) -> tuple[ResolvedEmbedding, list[LibraryMessage]]:
    """Build the embeddings recorded in *run_dir*'s manifest."""
    manifest = load_manifest(run_dir)
    model = manifest.embedding_model_used or manifest.embedding_model_requested
    if not model:
        raise ValueError("The index manifest does not record an embedding model.")
    return resolve_embedding(model, manifest.embedding_dimension)


def retrieve(
    run_dir: Path | str,
    query: str,
    config: RagConfig,
    *,
    embedding_loader: Callable[
        [Path | str], tuple[ResolvedEmbedding, list[LibraryMessage]]
    ] = load_index_embeddings,
    searcher_factory: Callable[[Path | str, Any], VectorSearcher] = open_searcher,
) -> RetrievalResult:
    """Run similarity search for *query* over the index in *run_dir*."""
    result = RetrievalResult()
    run_path = Path(run_dir)
    try:
        resolved_emb, emb_warnings = embedding_loader(run_path)
    except FileNotFoundError:
        result.errors.append(messages.index_not_found(str(run_path)))
        return result
    except EmbeddingProviderUnavailable as exc:
        result.errors.append(messages.embedding_unavailable(str(exc)))
        return result
    except (OSError, ValueError) as exc:
        result.errors.append(messages.index_unreadable(str(run_path), str(exc)))
        return result
    result.warnings.extend(emb_warnings)
    try:
        searcher = searcher_factory(run_path, resolved_emb.embeddings)
        hits = searcher.search(query, config.top_k)
    except Exception as exc:  # noqa: BLE001 - boundary around the vector store
        result.errors.append(messages.retrieval_failed(str(exc)))
        return result
    result.chunks = [
        RetrievedChunk(
            text=hit.text,
            source=hit.source,
            score=_distance_to_similarity(hit.distance),
            metadata=hit.metadata,
        )
        for hit in hits
    ]
    if not result.chunks:
        result.warnings.append(messages.no_context())
    return result


def _distance_to_similarity(distance: float) -> float:
    """Map a vector-store distance (lower = closer) to a 0-1 similarity score.

    ``similarity_search_with_score`` returns the backend's raw distance, which is
    always defined (unlike the relevance-score variant, which assumes a known
    metric range). ``1 / (1 + distance)`` gives a bounded, monotonic score that is
    1.0 for an exact match and approaches 0 as the distance grows.
    """
    return 1.0 / (1.0 + max(0.0, float(distance)))
