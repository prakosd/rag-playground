from __future__ import annotations

from pathlib import Path

from rag_engine.chat import (
    chat_answer,
    condense_question,
    generate_chat_answer,
    stream_chat_answer_with_usage,
)
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


def _capture_model(sink: list):
    """A chat model that records the messages it is asked to answer."""
    from langchain_core.language_models import SimpleChatModel

    class _Capture(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capture"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            sink.append(list(messages))
            return "reply"

    return _Capture()


def test_chat_answer_appends_no_think_to_system_message() -> None:
    from langchain_core.messages import SystemMessage

    sink: list = []
    generate_chat_answer(
        _capture_model(sink), "What is the capital?", _CHUNKS, [], system_directive="/no_think"
    )

    system = sink[0][0]
    assert isinstance(system, SystemMessage)
    assert system.content.endswith("/no_think")


def test_condense_question_without_history_returns_trimmed_question() -> None:
    assert condense_question(build_echo_chat_model(), [], "  hello  ") == "hello"


def test_generate_chat_answer_with_echo_includes_question() -> None:
    answer = generate_chat_answer(
        build_echo_chat_model(), "What is its capital?", _CHUNKS, _HISTORY
    )

    assert "What is its capital?" in answer


def test_generate_chat_answer_uses_custom_system_prompt() -> None:
    from langchain_core.language_models import SimpleChatModel

    captured: list[str] = []

    class _Capture(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capture"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            captured.append(str(messages[0].content))  # the formatted system message
            return "ok"

    answer = generate_chat_answer(
        _Capture(), "q", _CHUNKS, [], system_prompt="CUSTOM_SYS {context} {tone}"
    )

    assert answer == "ok"
    assert captured and captured[0].startswith("CUSTOM_SYS ")


def test_generate_chat_answer_writes_requested_language() -> None:
    from langchain_core.language_models import SimpleChatModel

    captured: list[str] = []

    class _Capture(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capture"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            captured.append(str(messages[0].content))  # the formatted system message
            return "ok"

    generate_chat_answer(_Capture(), "q", _CHUNKS, [], language="Indonesian")

    assert captured and "Indonesian" in captured[0]


def test_stream_chat_answer_with_usage_streams_and_collects_text() -> None:
    stream = stream_chat_answer_with_usage(
        build_echo_chat_model(), "What is its capital?", _CHUNKS, _HISTORY
    )
    tokens = list(stream)

    assert tokens  # streamed at least one token
    assert stream.text == "".join(tokens)
    assert "What is its capital?" in stream.text  # the echo model reflects the question


def test_generate_chat_answer_ignores_invalid_system_prompt() -> None:
    from langchain_core.language_models import SimpleChatModel

    captured: list[str] = []

    class _Capture(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capture2"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            captured.append(str(messages[0].content))
            return "ok"

    # A system prompt missing the {context}/{tone} slots falls back to the default.
    generate_chat_answer(_Capture(), "q", _CHUNKS, [], system_prompt="broken {oops}")

    assert captured and "question-answering assistant" in captured[0]


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
