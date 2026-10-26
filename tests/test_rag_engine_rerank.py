from __future__ import annotations

from langchain_core.language_models import SimpleChatModel

from rag_engine.config import ConversationalConfig
from rag_engine.messages import CODE_RERANK_UNAVAILABLE
from rag_engine.models import RetrievedChunk
from rag_engine.rerank import CrossEncoderUnavailable, rerank_chunks


def _chunk(text: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(text=text, source="a.md", score=score, metadata={})


_CHUNKS = [_chunk("c0"), _chunk("c1"), _chunk("c2")]


class _FakeEncoder:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def predict(self, pairs):
        return self._scores


class _RankingModel(SimpleChatModel):
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "ranking"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        return self.reply


def test_off_keeps_order_and_truncates() -> None:
    top, overflow, warnings = rerank_chunks(["q"], _CHUNKS, 2, ConversationalConfig(reranker="off"))

    assert [chunk.text for chunk in top] == ["c0", "c1"]
    assert [chunk.text for chunk in overflow] == ["c2"]  # beyond top_n, retained for display
    assert warnings == []


def test_stamps_passage_number_in_incoming_order() -> None:
    # Every strategy stamps retrieval_rank 1..N in the incoming (pre-rerank) order, so the
    # UI shows a stable passage number that lines up with the LLM re-ranker's output.
    for config in (
        ConversationalConfig(reranker="off"),
        ConversationalConfig(reranker="local"),
        ConversationalConfig(reranker="llm"),
    ):
        top, overflow, _ = rerank_chunks(
            ["q"],
            _CHUNKS,
            2,
            config,
            encoder_loader=lambda: _FakeEncoder([0.1, 0.9, 0.5]),
            chat_model=_RankingModel(reply="[3, 1, 2]"),
        )
        ranks = {chunk.text: chunk.retrieval_rank for chunk in (*top, *overflow)}
        assert ranks == {"c0": 1, "c1": 2, "c2": 3}


def test_empty_chunks_returns_empty() -> None:
    top, overflow, warnings = rerank_chunks(["q"], [], 5, ConversationalConfig(reranker="local"))

    assert top == []
    assert overflow == []
    assert warnings == []


def test_local_reorders_by_cross_encoder_score() -> None:
    config = ConversationalConfig(reranker="local")
    result, _, warnings = rerank_chunks(
        ["q"], _CHUNKS, 2, config, encoder_loader=lambda: _FakeEncoder([0.1, 0.9, 0.5])
    )

    assert [chunk.text for chunk in result] == ["c1", "c2"]
    assert warnings == []


def test_local_unavailable_degrades_with_warning() -> None:
    def loader():
        raise CrossEncoderUnavailable("not installed")

    config = ConversationalConfig(reranker="local")
    result, _, warnings = rerank_chunks(["q"], _CHUNKS, 5, config, encoder_loader=loader)

    assert [chunk.text for chunk in result] == ["c0", "c1", "c2"]
    assert any(w.code == CODE_RERANK_UNAVAILABLE and w.params["mode"] == "local" for w in warnings)


def test_local_predict_failure_degrades() -> None:
    class _BoomEncoder:
        def predict(self, pairs):
            raise RuntimeError("boom")

    config = ConversationalConfig(reranker="local")
    result, _, warnings = rerank_chunks(
        ["q"], _CHUNKS, 5, config, encoder_loader=lambda: _BoomEncoder()
    )

    assert [chunk.text for chunk in result] == ["c0", "c1", "c2"]
    assert any(w.code == CODE_RERANK_UNAVAILABLE for w in warnings)


def test_local_broken_dependency_stack_degrades() -> None:
    def loader():
        # An incompatible torch/transformers stack raises NameError during import.
        raise NameError("name 'nn' is not defined")

    config = ConversationalConfig(reranker="local")
    result, _, warnings = rerank_chunks(["q"], _CHUNKS, 5, config, encoder_loader=loader)

    assert [chunk.text for chunk in result] == ["c0", "c1", "c2"]
    assert any(w.code == CODE_RERANK_UNAVAILABLE for w in warnings)


def test_llm_reorders_by_ranking() -> None:
    config = ConversationalConfig(reranker="llm")
    result, _, warnings = rerank_chunks(
        ["q"], _CHUNKS, 3, config, chat_model=_RankingModel(reply="[3, 1, 2]")
    )

    assert [chunk.text for chunk in result] == ["c2", "c0", "c1"]
    assert warnings == []


def test_llm_without_model_degrades() -> None:
    config = ConversationalConfig(reranker="llm")
    result, _, warnings = rerank_chunks(["q"], _CHUNKS, 5, config, chat_model=None)

    assert [chunk.text for chunk in result] == ["c0", "c1", "c2"]
    assert any(w.code == CODE_RERANK_UNAVAILABLE and w.params["mode"] == "llm" for w in warnings)


def test_llm_unparsable_degrades() -> None:
    config = ConversationalConfig(reranker="llm")
    result, _, warnings = rerank_chunks(
        ["q"], _CHUNKS, 5, config, chat_model=_RankingModel(reply="no ranking here")
    )

    assert [chunk.text for chunk in result] == ["c0", "c1", "c2"]
    assert any(w.code == CODE_RERANK_UNAVAILABLE for w in warnings)


def test_llm_appends_omitted_indices() -> None:
    config = ConversationalConfig(reranker="llm")
    result, _, warnings = rerank_chunks(
        ["q"], _CHUNKS, 5, config, chat_model=_RankingModel(reply="[3]")
    )

    # Model returned only passage 3; the rest follow in search order.
    assert [chunk.text for chunk in result] == ["c2", "c0", "c1"]
    assert warnings == []


def test_overflow_holds_reranked_chunks_beyond_top_n() -> None:
    config = ConversationalConfig(reranker="llm")
    top, overflow, warnings = rerank_chunks(
        ["q"], _CHUNKS, 1, config, chat_model=_RankingModel(reply="[3, 1, 2]")
    )

    # top_n=1 → only the best is answer context; the rest are retained as display overflow.
    assert [chunk.text for chunk in top] == ["c2"]
    assert [chunk.text for chunk in overflow] == ["c0", "c1"]
    assert warnings == []
