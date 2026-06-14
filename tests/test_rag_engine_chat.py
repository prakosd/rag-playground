from __future__ import annotations

from pathlib import Path

from rag_engine.chat import chat_answer, condense_question, generate_chat_answer
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel
from rag_engine.llm.echo import build_echo_chat_model
from rag_engine.models import ChatTurn, RetrievedChunk
from rag_engine.retrieval import RetrievalResult

_CHUNKS = [
    RetrievedChunk(
        text="Paris is the capital of France.",
        source="a.md",
        score=0.9,
        metadata={"source": "a.md"},
    )
]
_HISTORY = [
    ChatTurn(role="user", content="Tell me about France."),
    ChatTurn(role="assistant", content="France is a country in Europe."),
]


def _echo_resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
    return ResolvedChatModel(model=build_echo_chat_model(), model_id="echo"), []


def test_condense_question_without_history_returns_trimmed_question() -> None:
    assert condense_question(build_echo_chat_model(), [], "  hello  ") == "hello"


def test_generate_chat_answer_with_echo_includes_question() -> None:
    answer = generate_chat_answer(
        build_echo_chat_model(), "What is its capital?", _CHUNKS, _HISTORY
    )

    assert "What is its capital?" in answer


def test_chat_answer_with_echo_skips_condensation(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def retriever(run_dir, query, config):
        captured["query"] = query
        return RetrievalResult(chunks=_CHUNKS)

    answer = chat_answer(
        tmp_path,
        "What is its capital?",
        _HISTORY,
        RagConfig(),
        retriever=retriever,
        chat_resolver=_echo_resolver,
    )

    assert answer.model_used == "echo"
    assert "What is its capital?" in answer.answer
    # Echo cannot rewrite a query, so retrieval must use the raw question.
    assert captured["query"] == "What is its capital?"


def test_chat_answer_condenses_with_real_model(tmp_path: Path) -> None:
    from langchain_core.language_models import SimpleChatModel

    class _Rewriter(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "rewriter"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            return "standalone query"

    def resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        return ResolvedChatModel(model=_Rewriter(), model_id="rewriter"), []

    captured: dict[str, str] = {}

    def retriever(run_dir, query, config):
        captured["query"] = query
        return RetrievalResult(chunks=_CHUNKS)

    chat_answer(
        tmp_path,
        "and its capital?",
        _HISTORY,
        RagConfig(),
        retriever=retriever,
        chat_resolver=resolver,
    )

    assert captured["query"] == "standalone query"


def test_chat_answer_rejects_empty_question(tmp_path: Path) -> None:
    answer = chat_answer(tmp_path, "  ", _HISTORY, RagConfig())

    assert answer.answer == ""
    assert answer.errors
