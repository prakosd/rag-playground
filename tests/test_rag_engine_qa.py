from __future__ import annotations

from pathlib import Path

from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel
from rag_engine.llm.echo import build_echo_chat_model
from rag_engine.models import RetrievedChunk
from rag_engine.qa import answer_question, generate_answer
from rag_engine.retrieval import RetrievalResult

_CHUNKS = [
    RetrievedChunk(
        text="Paris is the capital of France.",
        source="a.md",
        score=0.9,
        metadata={"source": "a.md"},
    )
]


def _echo_resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
    return ResolvedChatModel(model=build_echo_chat_model(), model_id="echo"), []


def _boom_resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
    from langchain_core.language_models import SimpleChatModel

    class _Boom(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "boom"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            raise RuntimeError("kaboom")

    return ResolvedChatModel(model=_Boom(), model_id="boom"), []


def test_generate_answer_with_echo_includes_question() -> None:
    answer = generate_answer(build_echo_chat_model(), "What is the capital?", _CHUNKS)

    assert "What is the capital?" in answer


def test_answer_question_happy_path(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=_CHUNKS)

    answer = answer_question(
        tmp_path,
        "What is the capital?",
        RagConfig(),
        retriever=retriever,
        chat_resolver=_echo_resolver,
    )

    assert answer.model_used == "echo"
    assert answer.sources == _CHUNKS
    assert "What is the capital?" in answer.answer
    assert not answer.errors


def test_answer_question_rejects_empty_question() -> None:
    answer = answer_question("/tmp/index", "   ", RagConfig())

    assert any(e.code == messages.CODE_EMPTY_QUESTION for e in answer.errors)
    assert answer.answer == ""


def test_answer_question_surfaces_retrieval_errors(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        result = RetrievalResult()
        result.errors.append(messages.index_not_found(str(run_dir)))
        return result

    answer = answer_question(
        tmp_path,
        "q",
        RagConfig(),
        retriever=retriever,
        chat_resolver=_echo_resolver,
    )

    assert any(e.code == messages.CODE_INDEX_NOT_FOUND for e in answer.errors)
    assert answer.answer == ""


def test_answer_question_handles_generation_failure(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=_CHUNKS)

    answer = answer_question(
        tmp_path,
        "q",
        RagConfig(),
        retriever=retriever,
        chat_resolver=_boom_resolver,
    )

    assert any(e.code == messages.CODE_GENERATION_FAILED for e in answer.errors)
    assert answer.answer == ""
