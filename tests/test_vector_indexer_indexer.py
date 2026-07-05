from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from vector_indexer import messages
from vector_indexer.config import IndexingConfig
from vector_indexer.embeddings import EmbeddingProviderUnavailable, ResolvedEmbedding
from vector_indexer.indexer import (
    STAGE_CHUNKING,
    STAGE_EMBEDDING,
    STAGE_LOADING,
    STAGE_RESOLVING_MODEL,
    STAGE_SAVING,
    VectorIndexer,
)
from vector_indexer.manifest import load_manifest
from vector_indexer.vector_store.base import VectorStore


class _FakeEmbeddings:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


class _FakeStore(VectorStore):
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = Path(persist_dir)
        self.ids: list[str] = []
        self.texts: list[str] = []
        self.persisted = False

    def add_embeddings(
        self,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, str]],
        ids: Sequence[str],
    ) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.texts.extend(texts)
        self.ids.extend(ids)

    def persist(self) -> None:
        self.persisted = True


def _indexer_with_capture() -> tuple[VectorIndexer, dict[str, object]]:
    created: dict[str, object] = {}

    def factory(persist_dir: Path, collection_name: str, embeddings: object) -> VectorStore:
        store = _FakeStore(persist_dir)
        created["store"] = store
        created["collection_name"] = collection_name
        return store

    def resolver(model: str, dimension: int | None) -> tuple[ResolvedEmbedding, list]:
        return ResolvedEmbedding(embeddings=_FakeEmbeddings(), model_id="fake", dimension=4), []

    return VectorIndexer(store_factory=factory, embedding_resolver=resolver), created


def test_run_indexes_inputs_and_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 50, encoding="utf-8")
    output_base = tmp_path / "vector_01_demo"
    indexer, created = _indexer_with_capture()

    result = indexer.run(IndexingConfig(), [source], output_base)

    assert result.success
    assert result.indexed_file_count == 1
    assert result.indexed_chunk_count >= 1
    assert result.output_dir.parent == output_base
    assert result.output_dir.is_dir()
    assert (result.output_dir / "manifest.json").exists()
    store = created["store"]
    assert isinstance(store, _FakeStore)
    assert store.persisted
    assert len(store.ids) == len(set(store.ids))
    manifest = load_manifest(result.output_dir)
    assert manifest.embedding_model_used == "fake"
    assert manifest.collection_name == created["collection_name"]
    # The run directory is a UTC timestamp slug, so created_at is recoverable.
    assert manifest.created_at is not None
    # Distinct indexed sources are recorded and round-trip through the manifest.
    assert result.indexed_sources
    assert manifest.indexed_sources == tuple(result.indexed_sources)


def test_run_emits_lifecycle_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 50, encoding="utf-8")
    output_base = tmp_path / "vector_01_demo"
    indexer, _ = _indexer_with_capture()

    with caplog.at_level(logging.INFO, logger="vector_indexer"):
        result = indexer.run(IndexingConfig(), [source], output_base)

    assert result.success
    logged = [record.getMessage() for record in caplog.records]
    assert any("Indexing started" in message for message in logged)
    assert any("Embedding model resolved: fake" in message for message in logged)
    assert any("Indexing complete" in message for message in logged)


def test_run_reports_error_when_no_inputs(tmp_path: Path) -> None:
    indexer, _ = _indexer_with_capture()

    result = indexer.run(IndexingConfig(), [], tmp_path / "vector_01_demo")

    assert not result.success
    assert result.errors


def test_run_skips_unsupported_inputs(tmp_path: Path) -> None:
    binary = tmp_path / "x.bin"
    binary.write_bytes(b"\x00\x01")
    indexer, _ = _indexer_with_capture()

    result = indexer.run(IndexingConfig(), [binary], tmp_path / "vector_01_demo")

    assert result.skipped_file_count == 1
    assert not result.success


def test_run_stops_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 50, encoding="utf-8")
    indexer, _ = _indexer_with_capture()

    result = indexer.run(
        IndexingConfig(), [source], tmp_path / "vector_01_demo", should_cancel=lambda: True
    )

    assert not result.success
    assert any(
        warning.code == messages.CODE_CANCELLED_BEFORE_CHUNKING for warning in result.warnings
    )


def test_run_records_error_when_embedding_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello", encoding="utf-8")

    def factory(persist_dir: Path, collection_name: str, embeddings: object) -> VectorStore:
        return _FakeStore(persist_dir)

    def resolver(model: str, dimension: int | None) -> tuple[ResolvedEmbedding, list]:
        raise EmbeddingProviderUnavailable("no provider configured")

    indexer = VectorIndexer(store_factory=factory, embedding_resolver=resolver)

    result = indexer.run(IndexingConfig(), [source], tmp_path / "vector_01_demo")

    assert not result.success
    assert any(error.code == messages.CODE_MODEL_UNAVAILABLE for error in result.errors)
    assert any("no provider configured" in str(error) for error in result.errors)


def test_run_records_cause_specific_error_for_missing_credentials(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello", encoding="utf-8")

    def factory(persist_dir: Path, collection_name: str, embeddings: object) -> VectorStore:
        return _FakeStore(persist_dir)

    def resolver(model: str, dimension: int | None) -> tuple[ResolvedEmbedding, list]:
        raise EmbeddingProviderUnavailable(
            "OPENAI_API_KEY is not configured for OpenAI embeddings."
        )

    indexer = VectorIndexer(store_factory=factory, embedding_resolver=resolver)

    result = indexer.run(IndexingConfig(), [source], tmp_path / "vector_01_demo")

    assert not result.success
    assert any(error.code == messages.CODE_MISSING_OPENAI_KEY for error in result.errors)


def test_run_emits_progress(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 200, encoding="utf-8")
    events: list[dict[str, object]] = []
    indexer, _ = _indexer_with_capture()

    result = indexer.run(
        IndexingConfig(chunk_size=120, chunk_overlap=20),
        [source],
        tmp_path / "vector_01_demo",
        progress_callback=events.append,
    )

    assert result.success
    count_events = [event for event in events if "processed_chunks" in event]
    assert count_events
    assert count_events[-1]["processed_chunks"] == result.indexed_chunk_count


def test_run_emits_pipeline_stages_in_order(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 200, encoding="utf-8")
    events: list[dict[str, object]] = []
    indexer, _ = _indexer_with_capture()

    result = indexer.run(
        IndexingConfig(chunk_size=120, chunk_overlap=20),
        [source],
        tmp_path / "vector_01_demo",
        progress_callback=events.append,
    )

    assert result.success
    stages = [event["stage"] for event in events if "stage" in event]
    assert stages == [
        STAGE_RESOLVING_MODEL,
        STAGE_LOADING,
        STAGE_CHUNKING,
        STAGE_EMBEDDING,
        STAGE_SAVING,
    ]


def test_partial_index_is_finalized_when_stopped_mid_run(tmp_path: Path) -> None:
    # Stop after the first embedded batch: the already-indexed chunks must
    # persist with a usable manifest (success) so semantic search still works.
    source = tmp_path / "a.md"
    source.write_text("hello world " * 4000, encoding="utf-8")
    indexer, _ = _indexer_with_capture()
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2  # pass the pre-chunk check + first batch, then stop

    result = indexer.run(
        IndexingConfig(chunk_size=120, chunk_overlap=20),
        [source],
        tmp_path / "vector_01_demo",
        should_cancel=should_cancel,
    )

    assert result.indexed_chunk_count > 0
    assert result.success  # partial index stays usable
    assert any(w.code == messages.CODE_CANCELLED_PARTIAL for w in result.warnings)
    manifest = load_manifest(result.output_dir)
    assert manifest.success
    assert manifest.indexed_chunk_count == result.indexed_chunk_count


def test_parallel_workers_index_all_chunks(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("hello world " * 4000, encoding="utf-8")
    indexer, created = _indexer_with_capture()

    result = indexer.run(
        IndexingConfig(chunk_size=120, chunk_overlap=20, index_workers=4),
        [source],
        tmp_path / "vector_01_demo",
    )

    assert result.success
    store = created["store"]
    assert isinstance(store, _FakeStore)
    assert len(store.ids) == result.indexed_chunk_count
    assert len(store.ids) == len(set(store.ids))  # no id collisions across workers
    manifest = load_manifest(result.output_dir)
    assert manifest.index_workers == 4


def test_local_model_runs_sequentially() -> None:
    from vector_indexer.embeddings import DEFAULT_LOCAL_MODEL
    from vector_indexer.indexer import _worker_count

    assert _worker_count(8, DEFAULT_LOCAL_MODEL) == 1
    assert _worker_count(4, "fake") == 4
