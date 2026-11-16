"""End-to-end vector indexing orchestration.

``VectorIndexer.run`` resolves embeddings (recording a cause-specific error when
the requested model is unavailable, with no silent local fallback), loads and
chunks the inputs, and writes the embedded chunks to a vector store inside a new
timestamped run directory. The store factory and the embedding resolver are
injectable so the flow can be tested without langchain-chroma or network access.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

from artifact_store import LibraryMessage
from artifact_store.naming import format_utc_timestamp_slug, parse_utc_timestamp_slug
from log4py import get_logger
from vector_indexer import messages
from vector_indexer.chunk_spill import read_chunk_batches, write_chunks
from vector_indexer.chunking import iter_chunks
from vector_indexer.config import IndexingConfig
from vector_indexer.document_loader import DocumentLoadResult, iter_documents
from vector_indexer.embeddings import (
    DEFAULT_LOCAL_MODEL,
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    resolve_embedding,
)
from vector_indexer.manifest import (
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_STORE_BACKEND,
    write_manifest,
)
from vector_indexer.models import Chunk, Document, IndexingResult
from vector_indexer.vector_store.base import VectorStore
from vector_indexer.vector_store.chroma import ChromaVectorStore

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["DEFAULT_COLLECTION_NAME", "VectorIndexer"]

_logger = get_logger(__name__)

_EMBED_BATCH_SIZE = 32
# Spill chunks to this file in the run dir during chunking, then stream it back for embedding
# so the whole corpus is never held in memory at once (removed when the run finishes).
_CHUNK_SPILL_FILE = ".chunks.jsonl"
# Cap batches in flight to the embedder (per worker) so streaming stays memory-bounded while
# still saturating the parallel workers.
_MAX_INFLIGHT_BATCHES_PER_WORKER = 2

# Coarse pipeline stages reported through the progress callback so a UI can show
# what the run is doing before per-chunk counts are available.
STAGE_RESOLVING_MODEL = "resolving_model"
STAGE_LOADING = "loading"
STAGE_CHUNKING = "chunking"
STAGE_EMBEDDING = "embedding"
STAGE_SAVING = "saving"

StoreFactory = Callable[[Path, str, "Embeddings"], VectorStore]
EmbeddingResolver = Callable[[str, int | None], tuple[ResolvedEmbedding, list[LibraryMessage]]]
ProgressCallback = Callable[[dict[str, object]], None]
CancelCheck = Callable[[], bool]


def _default_store_factory(
    persist_dir: Path, collection_name: str, embeddings: Embeddings
) -> VectorStore:
    return ChromaVectorStore(persist_dir, collection_name, embeddings)


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
        _logger.info("Indexing started: %d input(s) -> %s", len(inputs), run_dir)

        _report_stage(progress_callback, STAGE_RESOLVING_MODEL)
        resolved = self._resolve_embeddings(config, result)
        if resolved is None:
            return self._finalize(
                run_dir,
                config,
                result,
                model_id=None,
                collection_name=collection_name,
                store_backend=DEFAULT_STORE_BACKEND,
            )

        store_backend = self._load_chunk_embed(
            config,
            inputs,
            resolved,
            run_dir,
            collection_name,
            result,
            progress_callback,
            should_cancel,
        )
        return self._finalize(
            run_dir,
            config,
            result,
            model_id=resolved.model_id,
            collection_name=collection_name,
            store_backend=store_backend,
        )

    def _resolve_embeddings(
        self, config: IndexingConfig, result: IndexingResult
    ) -> ResolvedEmbedding | None:
        try:
            resolved, warnings = self._embedding_resolver(
                config.embedding_model, config.embedding_dimension
            )
        except EmbeddingProviderUnavailable as exc:
            _logger.error("Embedding model %r unavailable: %s", config.embedding_model, exc)
            result.errors.append(messages.classify_model_unavailable(str(exc)))
            return None
        result.warnings.extend(warnings)
        _logger.info("Embedding model resolved: %s", resolved.model_id)
        return resolved

    def _load_chunk_embed(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        resolved: ResolvedEmbedding,
        run_dir: Path,
        collection_name: str,
        result: IndexingResult,
        progress_callback: ProgressCallback | None,
        should_cancel: CancelCheck | None,
    ) -> str:
        """Stream inputs through load -> chunk -> (spill) -> embed with bounded memory.

        Chunks are spilled to a temporary file in *run_dir* during chunking (so documents and
        chunks are never all resident at once) and the total counted, then the spill is read
        back in batches for embedding. The spill file is always removed afterwards.
        """
        spill_path = run_dir / _CHUNK_SPILL_FILE
        try:
            total = self._spill_chunks(
                config, inputs, result, spill_path, progress_callback, should_cancel
            )
            if total is None:
                return DEFAULT_STORE_BACKEND
            return self._embed_and_store(
                spill_path,
                total,
                resolved,
                run_dir,
                collection_name,
                result,
                progress_callback,
                should_cancel,
                workers=_worker_count(config.index_workers, resolved.model_id),
            )
        finally:
            spill_path.unlink(missing_ok=True)

    def _spill_chunks(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        result: IndexingResult,
        spill_path: Path,
        progress_callback: ProgressCallback | None,
        should_cancel: CancelCheck | None,
    ) -> int | None:
        """Stream-load, chunk, and spill to disk; return the chunk count (or None to stop).

        Returns None (with the matching error/warning recorded) when there is nothing to
        embed: a chunking failure, a cancel before embedding, no readable documents, or no
        chunks produced.
        """
        _report_stage(progress_callback, STAGE_LOADING)
        load_result = DocumentLoadResult()
        docs_seen = 0

        def _documents() -> Iterator[Document]:
            nonlocal docs_seen
            for document in iter_documents(inputs, load_result):
                docs_seen += 1
                yield document

        _report_stage(progress_callback, STAGE_CHUNKING)
        try:
            total = write_chunks(
                spill_path,
                iter_chunks(
                    _documents(),
                    chunk_size=config.chunk_size,
                    chunk_overlap=config.chunk_overlap,
                    language=config.language,
                ),
            )
        except (RuntimeError, OSError) as exc:
            # RuntimeError: splitter dependency missing; OSError: spill write failed (disk full,
            # permissions) — the spill is part of the chunk-to-disk step, so report it the same
            # way rather than raising out of run().
            self._merge_load_notices(result, load_result)
            result.errors.append(messages.chunking_failed(str(exc)))
            return None

        self._merge_load_notices(result, load_result)
        if _cancelled(should_cancel):
            result.warnings.append(messages.cancelled_before_chunking())
            return None
        if docs_seen == 0:
            result.errors.append(messages.no_readable_content())
            return None
        if total == 0:
            result.errors.append(messages.no_chunks())
            return None
        _logger.info(
            "Loaded %d document(s) (%d skipped); chunked into %d chunk(s)",
            docs_seen,
            load_result.skipped_file_count,
            total,
        )
        return total

    @staticmethod
    def _merge_load_notices(result: IndexingResult, load_result: DocumentLoadResult) -> None:
        """Copy the loader's skipped-count + warnings onto the run result."""
        result.skipped_file_count = load_result.skipped_file_count
        result.warnings.extend(load_result.warnings)

    def _embed_and_store(
        self,
        spill_path: Path,
        total: int,
        resolved: ResolvedEmbedding,
        run_dir: Path,
        collection_name: str,
        result: IndexingResult,
        progress_callback: ProgressCallback | None,
        should_cancel: CancelCheck | None,
        *,
        workers: int,
    ) -> str:
        store = self._store_factory(run_dir / CHROMA_SUBDIR, collection_name, resolved.embeddings)
        backend = store.backend_name
        indexed_sources: set[str] = set()
        # Ids are assigned as each batch is read, so concurrent workers never share a counter.
        ids = count()
        lock = threading.Lock()
        # Embeddings run in parallel (the slow, network-bound step for cloud models), but
        # writes are serialized: the ChromaDB/SQLite backend is not safe for concurrent writes.
        store_lock = threading.Lock()
        _report_stage(progress_callback, STAGE_EMBEDDING)
        _logger.info("Embedding %d chunk(s) with %d worker(s)", total, workers)

        def _store_batch(batch: list[Chunk], batch_ids: list[str]) -> None:
            texts = [chunk.text for chunk in batch]
            vectors = resolved.embeddings.embed_documents(texts)
            with store_lock:
                store.add_embeddings(
                    texts=texts,
                    embeddings=vectors,
                    metadatas=[chunk.metadata for chunk in batch],
                    ids=batch_ids,
                )
            with lock:
                result.indexed_chunk_count += len(batch)
                indexed_sources.update(chunk.document_source for chunk in batch)
                _report_progress(progress_callback, result.indexed_chunk_count, total)

        try:
            if workers > 1:
                cancelled = _embed_parallel(spill_path, ids, _store_batch, should_cancel, workers)
            else:
                cancelled = _embed_serial(spill_path, ids, _store_batch, should_cancel)
            if cancelled:
                result.warnings.append(messages.cancelled_partial())
            _report_stage(progress_callback, STAGE_SAVING)
            store.persist()
        except Exception as exc:  # noqa: BLE001 - boundary around the embedding backend
            _logger.error("Embedding/storage failed: %s", exc)
            result.errors.append(messages.classify_embedding_failure(str(exc)))
            return backend
        result.indexed_file_count = len(indexed_sources)
        result.indexed_sources = sorted(indexed_sources)
        _logger.info(
            "Saved index: %d chunk(s) from %d source(s)",
            result.indexed_chunk_count,
            result.indexed_file_count,
        )
        return backend

    def _finalize(
        self,
        run_dir: Path,
        config: IndexingConfig,
        result: IndexingResult,
        *,
        model_id: str | None,
        collection_name: str,
        store_backend: str,
    ) -> IndexingResult:
        result.success = result.indexed_chunk_count > 0 and not result.errors
        _write_manifest(
            run_dir,
            config,
            result,
            model_id=model_id,
            collection_name=collection_name,
            store_backend=store_backend,
        )
        _logger.info(
            "Indexing complete: success=%s files=%d chunks=%d skipped=%d",
            result.success,
            result.indexed_file_count,
            result.indexed_chunk_count,
            result.skipped_file_count,
        )
        return result


def _cancelled(should_cancel: CancelCheck | None) -> bool:
    return bool(should_cancel and should_cancel())


def _worker_count(requested: int, model_id: str) -> int:
    """Resolve effective worker count: the local ONNX model stays sequential."""
    if model_id == DEFAULT_LOCAL_MODEL:
        return 1
    return max(1, requested)


def _report_progress(
    progress_callback: ProgressCallback | None, processed: int, total: int
) -> None:
    if progress_callback is not None:
        progress_callback({"processed_chunks": processed, "total_chunks": total})


def _report_stage(progress_callback: ProgressCallback | None, stage: str) -> None:
    if progress_callback is not None:
        progress_callback({"stage": stage})


def _embed_parallel(
    spill_path: Path,
    ids: count[int],
    store_batch: Callable[[list[Chunk], list[str]], None],
    should_cancel: CancelCheck | None,
    workers: int,
) -> bool:
    """Embed spilled batches with a bounded in-flight window; return True if cancelled.

    At most ``workers * _MAX_INFLIGHT_BATCHES_PER_WORKER`` batches are in flight, so memory
    stays bounded regardless of corpus size while the workers stay saturated. Waiting on the
    oldest future when the window is full also surfaces worker errors early.
    """
    max_in_flight = workers * _MAX_INFLIGHT_BATCHES_PER_WORKER
    with ThreadPoolExecutor(max_workers=workers) as pool:
        in_flight: deque[Future[None]] = deque()
        for batch in read_chunk_batches(spill_path, _EMBED_BATCH_SIZE):
            if _cancelled(should_cancel):
                for future in in_flight:
                    future.result()  # let the already-submitted batches finish (partial index)
                return True
            batch_ids = [str(next(ids)) for _ in batch]
            in_flight.append(pool.submit(store_batch, batch, batch_ids))
            if len(in_flight) >= max_in_flight:
                in_flight.popleft().result()
        for future in in_flight:
            future.result()  # propagate any worker exception
    return False


def _embed_serial(
    spill_path: Path,
    ids: count[int],
    store_batch: Callable[[list[Chunk], list[str]], None],
    should_cancel: CancelCheck | None,
) -> bool:
    """Embed spilled batches sequentially; return True if cancelled."""
    for batch in read_chunk_batches(spill_path, _EMBED_BATCH_SIZE):
        if _cancelled(should_cancel):
            return True
        batch_ids = [str(next(ids)) for _ in batch]
        store_batch(batch, batch_ids)
    return False


def _write_manifest(
    run_dir: Path,
    config: IndexingConfig,
    result: IndexingResult,
    *,
    model_id: str | None,
    collection_name: str,
    store_backend: str,
) -> None:
    write_manifest(
        run_dir,
        {
            "created_at": _run_created_at(run_dir),
            "embedding_model_requested": config.embedding_model,
            "embedding_model_used": model_id,
            "embedding_dimension": config.embedding_dimension,
            "collection_name": collection_name,
            "store_backend": store_backend,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "language": config.language,
            "index_workers": config.index_workers,
            "success": result.success,
            "indexed_file_count": result.indexed_file_count,
            "indexed_chunk_count": result.indexed_chunk_count,
            "skipped_file_count": result.skipped_file_count,
            "indexed_sources": result.indexed_sources,
            "warnings": [message.as_dict() for message in result.warnings],
            "errors": [message.as_dict() for message in result.errors],
        },
    )


def _run_created_at(run_dir: Path) -> str | None:
    """Return the run's creation time (ISO-8601 UTC) from its timestamp slug."""
    created = parse_utc_timestamp_slug(run_dir.name)
    return created.isoformat() if created else None
