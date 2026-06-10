"""End-to-end vector indexing orchestration.

``VectorIndexer.run`` resolves an embedding provider (applying the Titan ->
offline fallback policy), loads and chunks the inputs, embeds the chunks, and
writes them to a vector store inside a new timestamped run directory. The store
factory and embedding resolver are injectable so the flow can be tested without
ChromaDB or network access.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Iterator, Sequence
from itertools import count
from pathlib import Path

from artifact_store.naming import format_utc_timestamp_slug
from vector_indexer.chunking import chunk_documents
from vector_indexer.config import IndexingConfig
from vector_indexer.document_loader import load_documents
from vector_indexer.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderUnavailable,
    resolve_embedding,
)
from vector_indexer.models import Chunk, IndexingResult, VectorRecord
from vector_indexer.vector_store.base import VectorStore
from vector_indexer.vector_store.chroma import ChromaVectorStore

__all__ = ["DEFAULT_COLLECTION_NAME", "VectorIndexer"]

DEFAULT_COLLECTION_NAME = "crawl4md_documents"
_CHROMA_SUBDIR = "chroma"
_MANIFEST_NAME = "manifest.json"
_EMBED_BATCH_SIZE = 32

StoreFactory = Callable[[Path], VectorStore]
EmbeddingResolver = Callable[[str, int | None], tuple[EmbeddingProvider, list[str]]]
ProgressCallback = Callable[[dict[str, int]], None]
CancelCheck = Callable[[], bool]


def _default_store_factory(persist_dir: Path) -> VectorStore:
    return ChromaVectorStore(persist_dir)


class VectorIndexer:
    """Builds a persisted vector index from text inputs."""

    def __init__(
        self,
        *,
        store_factory: StoreFactory | None = None,
        embedding_resolver: EmbeddingResolver | None = None,
    ) -> None:
        self._store_factory = store_factory or _default_store_factory
        self._embedding_resolver = embedding_resolver or resolve_embedding

    def run(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        output_base: Path | str,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> IndexingResult:
        """Run the full indexing pipeline and return a structured result."""
        run_dir = Path(output_base) / format_utc_timestamp_slug()
        run_dir.mkdir(parents=True, exist_ok=True)
        result = IndexingResult(success=False, output_dir=run_dir)

        provider = self._resolve_provider(config, result)
        if provider is None:
            return self._finalize(run_dir, config, result, model_id=None)

        chunks = self._prepare_chunks(config, inputs, result, should_cancel)
        if chunks is None:
            return self._finalize(run_dir, config, result, model_id=provider.model_id)

        self._embed_and_store(
            chunks,
            provider,
            run_dir,
            collection_name,
            result,
            progress_callback,
            should_cancel,
        )
        return self._finalize(run_dir, config, result, model_id=provider.model_id)

    def _resolve_provider(
        self, config: IndexingConfig, result: IndexingResult
    ) -> EmbeddingProvider | None:
        try:
            provider, warnings = self._embedding_resolver(
                config.embedding_model, config.embedding_dimension
            )
        except EmbeddingProviderUnavailable as exc:
            result.errors.append(str(exc))
            return None
        result.warnings.extend(warnings)
        return provider

    def _prepare_chunks(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        result: IndexingResult,
        should_cancel: CancelCheck | None,
    ) -> list[Chunk] | None:
        load_result = load_documents(inputs)
        result.skipped_file_count = load_result.skipped_file_count
        result.warnings.extend(load_result.warnings)
        if not load_result.documents:
            result.errors.append(
                "No readable .md or .txt content was found in the selected inputs."
            )
            return None
        if _cancelled(should_cancel):
            result.warnings.append("Indexing was cancelled before chunking started.")
            return None
        try:
            chunks = chunk_documents(
                load_result.documents,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                language=config.language,
            )
        except RuntimeError as exc:
            result.errors.append(str(exc))
            return None
        if not chunks:
            result.errors.append("The selected inputs produced no indexable text chunks.")
            return None
        return chunks

    def _embed_and_store(
        self,
        chunks: list[Chunk],
        provider: EmbeddingProvider,
        run_dir: Path,
        collection_name: str,
        result: IndexingResult,
        progress_callback: ProgressCallback | None,
        should_cancel: CancelCheck | None,
    ) -> None:
        store = self._store_factory(run_dir / _CHROMA_SUBDIR)
        store.create_collection(collection_name)
        ids = count()
        indexed_sources: set[str] = set()
        total = len(chunks)
        try:
            for batch in _batched(chunks, _EMBED_BATCH_SIZE):
                if _cancelled(should_cancel):
                    result.warnings.append("Indexing was cancelled; partial results were saved.")
                    break
                embeddings = provider.embed_documents([chunk.text for chunk in batch])
                records = [
                    VectorRecord(
                        id=str(next(ids)),
                        text=chunk.text,
                        embedding=embedding,
                        metadata=chunk.metadata,
                    )
                    for chunk, embedding in zip(batch, embeddings, strict=True)
                ]
                store.add_documents(records)
                result.indexed_chunk_count += len(records)
                indexed_sources.update(chunk.document_source for chunk in batch)
                _report_progress(progress_callback, result.indexed_chunk_count, total)
            store.persist()
        except Exception as exc:  # noqa: BLE001 - boundary around the embedding backend
            result.errors.append(f"Embedding or storage failed: {exc}")
            return
        result.indexed_file_count = len(indexed_sources)

    def _finalize(
        self,
        run_dir: Path,
        config: IndexingConfig,
        result: IndexingResult,
        *,
        model_id: str | None,
    ) -> IndexingResult:
        result.success = result.indexed_chunk_count > 0 and not result.errors
        _write_manifest(run_dir, config, result, model_id=model_id)
        return result


def _cancelled(should_cancel: CancelCheck | None) -> bool:
    return bool(should_cancel and should_cancel())


def _report_progress(
    progress_callback: ProgressCallback | None, processed: int, total: int
) -> None:
    if progress_callback is not None:
        progress_callback({"processed_chunks": processed, "total_chunks": total})


def _batched(items: Sequence[Chunk], size: int) -> Iterator[list[Chunk]]:
    batch: list[Chunk] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _write_manifest(
    run_dir: Path,
    config: IndexingConfig,
    result: IndexingResult,
    *,
    model_id: str | None,
) -> None:
    manifest = {
        "embedding_model_requested": config.embedding_model,
        "embedding_model_used": model_id,
        "embedding_dimension": config.embedding_dimension,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "language": config.language,
        "success": result.success,
        "indexed_file_count": result.indexed_file_count,
        "indexed_chunk_count": result.indexed_chunk_count,
        "skipped_file_count": result.skipped_file_count,
        "warnings": result.warnings,
        "errors": result.errors,
    }
    with contextlib.suppress(OSError):
        (run_dir / _MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
