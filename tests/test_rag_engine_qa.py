from __future__ import annotations

from pathlib import Path

from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel
from rag_engine.llm.echo import build_echo_chat_model
from rag_engine.models import RetrievedChunk
from rag_engine.qa import answer_question, generate_answer, generate_from_prompt, stream_prompt
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


def test_stream_prompt_leads_with_no_think_system_message() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    sink: list = []
    list(stream_prompt(_capture_model(sink), "hello", system_directive="/no_think"))

    sent = sink[0]
    assert isinstance(sent[0], SystemMessage) and sent[0].content == "/no_think"
    assert isinstance(sent[1], HumanMessage) and sent[1].content == "hello"


def test_stream_prompt_without_directive_sends_only_the_prompt() -> None:
    from langchain_core.messages import HumanMessage

    sink: list = []
    list(stream_prompt(_capture_model(sink), "hello"))

    assert len(sink[0]) == 1 and isinstance(sink[0][0], HumanMessage)


def test_generate_from_prompt_leads_with_no_think_system_message() -> None:
    from langchain_core.messages import SystemMessage

    sink: list = []
    generate_from_prompt(_capture_model(sink), "hello", system_directive="/no_think")

    assert isinstance(sink[0][0], SystemMessage) and sink[0][0].content == "/no_think"


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


def test_stream_prompt_with_echo_streams_text_without_usage() -> None:
    from rag_engine.qa import stream_prompt

    generation = stream_prompt(build_echo_chat_model(), "Question:\nHi\n\nAnswer:")
    streamed = "".join(generation)

    assert "Hi" in streamed
    assert generation.text == streamed
    assert generation.usage is None


def test_generate_from_prompt_with_echo_returns_text_without_usage() -> None:
    from rag_engine.qa import generate_from_prompt

    text, usage = generate_from_prompt(build_echo_chat_model(), "Question:\nHello\n\nAnswer:")

    assert "Hello" in text
    assert usage is None


def test_stream_prompt_aggregates_token_usage() -> None:
    from langchain_core.messages import AIMessageChunk

    from rag_engine.models import TokenUsage
    from rag_engine.qa import stream_prompt

    class _FakeStreamingModel:
        def stream(self, messages):
            yield AIMessageChunk(content="Hello ")
            yield AIMessageChunk(
                content="world",
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )

    generation = stream_prompt(_FakeStreamingModel(), "ignored prompt")
    streamed = "".join(generation)

    assert streamed == "Hello world"
    assert generation.text == "Hello world"
    assert generation.usage == TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15)
