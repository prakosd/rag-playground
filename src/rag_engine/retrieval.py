"""Open a persisted vector index and run similarity search over it (Step 3).

The index is reopened with the *same* embedding model that wrote it (read from
the run manifest) via the same ``langchain_chroma.Chroma`` class the indexer
used, which guarantees on-disk compatibility. Heavy imports (langchain-chroma,
chromadb) stay inside the functions that need them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage
from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.models import RetrievedChunk
from vector_indexer import (
    CHROMA_SUBDIR,
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    load_manifest,
    resolve_embedding,
)

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["RetrievalResult", "load_index_embeddings", "open_index", "retrieve"]


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


def open_index(run_dir: Path | str, embeddings: Embeddings) -> Any:
    """Open the persisted ChromaDB collection for *run_dir*."""
    from chromadb.config import Settings
    from langchain_chroma import Chroma

    manifest = load_manifest(run_dir)
    return Chroma(
        collection_name=manifest.collection_name,
        embedding_function=embeddings,
        persist_directory=str(Path(run_dir) / CHROMA_SUBDIR),
        client_settings=Settings(anonymized_telemetry=False),
    )


def retrieve(
    run_dir: Path | str,
    query: str,
    config: RagConfig,
    *,
    embedding_loader: Callable[
        [Path | str], tuple[ResolvedEmbedding, list[LibraryMessage]]
    ] = load_index_embeddings,
    store_opener: Callable[[Path | str, Any], Any] = open_index,
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
        store = store_opener(run_path, resolved_emb.embeddings)
        hits = store.similarity_search_with_score(query, k=config.top_k)
    except Exception as exc:  # noqa: BLE001 - boundary around the vector store
        result.errors.append(messages.retrieval_failed(str(exc)))
        return result
    result.chunks = [
        RetrievedChunk(
            text=document.page_content,
            source=str(document.metadata.get("source", "")),
            score=_distance_to_similarity(distance),
            metadata={str(key): str(value) for key, value in document.metadata.items()},
        )
        for document, distance in hits
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
