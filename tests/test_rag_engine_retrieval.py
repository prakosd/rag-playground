from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.retrieval import retrieve
from rag_engine.search import ChromaSearcher, SearchHit, VectorSearcher
from vector_indexer import EmbeddingProviderUnavailable, ResolvedEmbedding


class _FakeDoc:
    def __init__(self, content: str, metadata: dict) -> None:
        self.page_content = content
        self.metadata = metadata


class _FakeStore:
    def __init__(self, hits: list, *, mmr_docs: list | None = None) -> None:
        self._hits = hits
        self._mmr_docs = mmr_docs or []
        self.last_filter: object = "unset"
        self.mmr_kwargs: dict | None = None

    def similarity_search_with_score(self, query: str, k: int, filter=None) -> list:
        self.last_filter = filter
        return self._hits[:k]

    def max_marginal_relevance_search(
        self, query: str, k: int, fetch_k: int, lambda_mult: float, filter=None
    ) -> list:
        self.mmr_kwargs = {
            "k": k,
            "fetch_k": fetch_k,
            "lambda_mult": lambda_mult,
            "filter": filter,
        }
        return self._mmr_docs[:k]


class _FakeSearcher(VectorSearcher):
    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = hits

    def search(
        self,
        query: str,
        k: int,
        *,
        search_type: str = "similarity",
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        source_filter=(),
    ) -> list[SearchHit]:
        return self._hits[:k]


def _loader_ok(run_dir: Path | str):
    return ResolvedEmbedding(embeddings=object(), model_id="fake", dimension=4), []


def test_retrieve_returns_ranked_chunks() -> None:
    # The searcher returns raw distances which the retriever maps to a 0-1
    # similarity (lower distance -> higher score).
    hits = [
        SearchHit(text="hello", source="a.md", distance=0.0, metadata={"source": "a.md"}),
        SearchHit(text="world", source="b.md", distance=1.0, metadata={"source": "b.md"}),
    ]

    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(top_k=2),
        embedding_loader=_loader_ok,
        searcher_factory=lambda run_dir, embeddings: _FakeSearcher(hits),
    )

    assert [chunk.source for chunk in result.chunks] == ["a.md", "b.md"]
    assert result.chunks[0].score == 1.0  # distance 0.0 -> perfect similarity
    assert result.chunks[1].score == 0.5  # distance 1.0 -> 1/(1+1)
    assert not result.errors


def test_retrieve_logs_semantic_search(caplog: pytest.LogCaptureFixture) -> None:
    hits = [SearchHit(text="hello", source="a.md", distance=0.0, metadata={"source": "a.md"})]

    with caplog.at_level(logging.INFO, logger="rag_engine"):
        retrieve(
            "/tmp/index",
            "q",
            RagConfig(top_k=1),
            embedding_loader=_loader_ok,
            searcher_factory=lambda run_dir, embeddings: _FakeSearcher(hits),
        )

    logged = [record.getMessage() for record in caplog.records]
    assert any("Semantic search" in message for message in logged)
    assert any("returned 1 chunk" in message for message in logged)


def test_retrieve_empty_warns_no_context() -> None:
    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(),
        embedding_loader=_loader_ok,
        searcher_factory=lambda run_dir, embeddings: _FakeSearcher([]),
    )

    assert result.chunks == []
    assert any(w.code == messages.CODE_NO_CONTEXT for w in result.warnings)


def test_retrieve_filters_chunks_below_score_threshold() -> None:
    hits = [
        SearchHit(text="hello", source="a.md", distance=0.0, metadata={"source": "a.md"}),
        SearchHit(text="world", source="b.md", distance=3.0, metadata={"source": "b.md"}),
    ]

    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(top_k=2, score_threshold=0.5),
        embedding_loader=_loader_ok,
        searcher_factory=lambda run_dir, embeddings: _FakeSearcher(hits),
    )

    # distance 0.0 -> score 1.0 (kept); distance 3.0 -> score 0.25 (dropped).
    assert [chunk.source for chunk in result.chunks] == ["a.md"]


def test_retrieve_missing_index_reports_error() -> None:
    def loader(run_dir: Path | str):
        raise FileNotFoundError()

    result = retrieve("/tmp/missing", "q", RagConfig(), embedding_loader=loader)

    assert any(e.code == messages.CODE_INDEX_NOT_FOUND for e in result.errors)


def test_retrieve_embedding_unavailable_reports_error() -> None:
    def loader(run_dir: Path | str):
        raise EmbeddingProviderUnavailable("no chromadb")

    result = retrieve("/tmp/index", "q", RagConfig(), embedding_loader=loader)

    assert any(e.code == messages.CODE_EMBEDDING_UNAVAILABLE for e in result.errors)


def test_retrieve_searcher_failure_reports_error() -> None:
    def factory(run_dir: Path | str, embeddings: object):
        raise RuntimeError("boom")

    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(),
        embedding_loader=_loader_ok,
        searcher_factory=factory,
    )

    assert any(e.code == messages.CODE_RETRIEVAL_FAILED for e in result.errors)


def test_retrieve_real_index_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("langchain_chroma")
    from langchain_core.embeddings import Embeddings

    from vector_indexer import IndexingConfig, VectorIndexer

    class _FakeEmbeddings(Embeddings):
        # Unit vectors keep relevance scores within [0, 1] (as real, normalized
        # embedding models produce), mirroring production behaviour.
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    fake = _FakeEmbeddings()

    def resolver(model: str, dimension: int | None):
        return ResolvedEmbedding(embeddings=fake, model_id="fake", dimension=3), []

    source = tmp_path / "a.md"
    source.write_text("Paris is the capital of France. " * 10, encoding="utf-8")
    run = VectorIndexer(embedding_resolver=resolver).run(
        IndexingConfig(chunk_size=120, chunk_overlap=20), [source], tmp_path / "vec"
    )

    result = retrieve(
        run.output_dir,
        "France",
        RagConfig(top_k=2),
        embedding_loader=lambda run_dir: (
            ResolvedEmbedding(embeddings=fake, model_id="fake", dimension=3),
            [],
        ),
    )

    assert result.chunks
    assert any("Paris" in chunk.text for chunk in result.chunks)


def test_chroma_searcher_maps_documents_to_search_hits() -> None:
    store = _FakeStore([(_FakeDoc("hello", {"source": "a.md", "language": "en"}), 0.25)])
    searcher = ChromaSearcher("/tmp/index", embeddings=object(), store=store)

    hits = searcher.search("q", k=5)

    assert hits == [
        SearchHit(
            text="hello",
            source="a.md",
            distance=0.25,
            metadata={"source": "a.md", "language": "en"},
        )
    ]


def test_chroma_searcher_mmr_recovers_distances_from_candidates() -> None:
    doc_a = _FakeDoc("alpha", {"source": "a.md"})
    doc_b = _FakeDoc("beta", {"source": "b.md"})
    store = _FakeStore([(doc_a, 0.2), (doc_b, 0.8)], mmr_docs=[doc_b, doc_a])
    searcher = ChromaSearcher("/tmp/index", embeddings=object(), store=store)

    hits = searcher.search("q", k=2, search_type="mmr", fetch_k=5, lambda_mult=0.3)

    # MMR order is preserved (b then a); distances are joined from the scored pool.
    assert [(hit.source, hit.distance) for hit in hits] == [("b.md", 0.8), ("a.md", 0.2)]
    assert store.mmr_kwargs == {"k": 2, "fetch_k": 5, "lambda_mult": 0.3, "filter": None}


def test_chroma_searcher_applies_multi_source_filter() -> None:
    store = _FakeStore([(_FakeDoc("hello", {"source": "a.md"}), 0.1)])
    searcher = ChromaSearcher("/tmp/index", embeddings=object(), store=store)

    searcher.search("q", k=5, source_filter=["a.md", "b.md"])

    assert store.last_filter == {"source": {"$in": ["a.md", "b.md"]}}


def test_chroma_searcher_single_source_filter_uses_exact_match() -> None:
    store = _FakeStore([(_FakeDoc("hello", {"source": "a.md"}), 0.1)])
    searcher = ChromaSearcher("/tmp/index", embeddings=object(), store=store)

    searcher.search("q", k=5, source_filter=["a.md"])

    assert store.last_filter == {"source": "a.md"}
