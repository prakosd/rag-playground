from __future__ import annotations

from pathlib import Path

from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from rag_engine import messages
from rag_engine.chat import conversational_answer, conversational_answer_stream
from rag_engine.config import ConversationalConfig
from rag_engine.llm import ResolvedChatModel
from rag_engine.models import ChatTurn, ConversationState, RetrievedChunk
from rag_engine.retrieval import RetrievalResult

_CHUNKS = [
    RetrievedChunk(text="Paris is the capital of France.", source="a.md", score=0.9, metadata={}),
]


class _ScriptedModel(SimpleChatModel):
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        return self.reply


class _UsageModel(BaseChatModel):
    """A chat model whose reply carries usage_metadata, for token-capture tests."""

    reply: str = "ANSWER"
    tokens: tuple[int, int, int] = (1, 2, 3)

    @property
    def _llm_type(self) -> str:
        return "usage"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        input_tokens, output_tokens, total_tokens = self.tokens
        message = AIMessage(
            content=self.reply,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _StreamingUsageModel(BaseChatModel):
    """Streams answer chunks and reports usage on the final chunk (like real models)."""

    pieces: tuple[str, ...] = ("AN", "SWER")
    tokens: tuple[int, int, int] = (1, 2, 3)

    @property
    def _llm_type(self) -> str:
        return "streaming-usage"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        i, o, t = self.tokens
        message = AIMessage(
            content="".join(self.pieces),
            usage_metadata={"input_tokens": i, "output_tokens": o, "total_tokens": t},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        last = len(self.pieces) - 1
        for index, piece in enumerate(self.pieces):
            if index == last:
                i, o, t = self.tokens
                message = AIMessageChunk(
                    content=piece,
                    usage_metadata={"input_tokens": i, "output_tokens": o, "total_tokens": t},
                )
            else:
                message = AIMessageChunk(content=piece)
            yield ChatGenerationChunk(message=message)


def _main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
    return ResolvedChatModel(model=_ScriptedModel(reply="ANSWER"), model_id="main"), []


def _echo_aux_resolver(config):
    # Aux is the offline echo model -> planning is skipped/degraded.
    return ResolvedChatModel(model=_ScriptedModel(reply=""), model_id="echo"), []


def test_conversational_answer_empty_question_returns_error() -> None:
    result = conversational_answer(
        "/tmp/x",
        "   ",
        ConversationState(),
        ConversationalConfig(),
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == ""
    assert any(e.code == messages.CODE_EMPTY_QUESTION for e in result.errors)


def test_conversational_answer_basic_flow(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def retriever(run_dir, query, config):
        captured["query"] = query
        return RetrievalResult(chunks=list(_CHUNKS))

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == "ANSWER"
    assert result.sources == _CHUNKS
    assert result.model_used == "main"
    assert result.aux_model_used == "echo"
    assert result.reranker_used == "off"
    assert {"plan", "retrieve", "rerank", "answer"} <= set(result.timings)
    assert captured["query"] == "What is the capital of France?"
    assert result.plan.degraded is True


def test_conversational_answer_records_individual_asked_questions(tmp_path: Path) -> None:
    # The live pipeline must fold the plan's *individual* sub-questions into
    # asked_questions (matching disk rehydration), not the joined resolved string,
    # so follow-up de-dup behaves the same before and after a reload.
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def aux_resolver(config):
        return (
            ResolvedChatModel(
                model=_ScriptedModel(reply='["What is X?", "What is Y?"]'), model_id="aux"
            ),
            [],
        )

    result = conversational_answer(
        tmp_path,
        "What is X and what is Y?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
    )

    assert result.plan.sub_questions == ["What is X?", "What is Y?"]
    assert result.state.asked_questions == ("What is X?", "What is Y?")


def test_conversational_answer_captures_answer_token_usage(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_UsageModel(reply="ANSWER"), model_id="main"), []

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    # Only the answer stage runs an LLM here (planning short-circuits; no
    # rerank/followups/state), so exactly one usage row is captured for the answer model.
    assert result.answer == "ANSWER"
    assert len(result.token_usage) == 1
    stage = result.token_usage[0]
    assert stage.process == "answer"
    assert stage.model_id == "main"
    assert stage.usage.total_tokens == 3


def test_conversational_answer_token_usage_empty_without_reported_usage(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    # The scripted answer model reports no usage_metadata, so nothing is recorded.
    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.token_usage == []


def test_conversational_answer_reports_progress_stages(tmp_path: Path) -> None:
    codes: list[str] = []

    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def aux_resolver(config):
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
        progress_callback=lambda message: codes.append(message.code),
    )

    # Search stages report in order; the answer stage precedes wrap-up.
    assert codes[:3] == [
        messages.CODE_PROGRESS_PLAN,
        messages.CODE_PROGRESS_RETRIEVE,
        messages.CODE_PROGRESS_RERANK,
    ]
    assert messages.CODE_PROGRESS_ANSWER in codes
    assert messages.CODE_PROGRESS_STATE in codes
    assert codes.index(messages.CODE_PROGRESS_ANSWER) < codes.index(messages.CODE_PROGRESS_STATE)


def test_conversational_answer_stream_streams_tokens_and_finalizes(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_StreamingUsageModel(), model_id="main"), []

    generation = conversational_answer_stream(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=_echo_aux_resolver,
    )
    tokens = list(generation)

    assert tokens == ["AN", "SWER"]  # streamed token-by-token
    assert generation.answer is not None
    assert generation.answer.answer == "ANSWER"
    assert generation.answer.sources == _CHUNKS
    assert {"retrieve", "answer", "state"} <= set(generation.answer.timings)


def test_conversational_answer_stream_empty_question_yields_nothing() -> None:
    generation = conversational_answer_stream(
        "/tmp/x",
        "   ",
        ConversationState(),
        ConversationalConfig(),
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert list(generation) == []  # nothing to stream
    assert generation.answer is not None
    assert any(e.code == messages.CODE_EMPTY_QUESTION for e in generation.answer.errors)


def test_conversational_answer_stream_captures_answer_usage(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_StreamingUsageModel(), model_id="main"), []

    generation = conversational_answer_stream(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=_echo_aux_resolver,
    )
    list(generation)

    # Only the answer stage runs an LLM here, so exactly one usage row is captured.
    assert len(generation.answer.token_usage) == 1
    stage = generation.answer.token_usage[0]
    assert stage.process == "answer"
    assert stage.model_id == "main"
    assert stage.usage.total_tokens == 3


def test_conversational_answer_stream_matches_blocking(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    config = ConversationalConfig(reranker="off", followups_enabled=False)
    blocking = conversational_answer(
        tmp_path,
        "What is the capital?",
        ConversationState(),
        config,
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )
    generation = conversational_answer_stream(
        tmp_path,
        "What is the capital?",
        ConversationState(),
        config,
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )
    list(generation)

    # The streaming and blocking paths produce the same grounded answer.
    assert generation.answer.answer == blocking.answer == "ANSWER"


def test_conversational_answer_stream_survives_bad_history_brace(tmp_path: Path) -> None:
    # A prior turn containing a stray "{" breaks ChatPromptTemplate construction; the
    # streaming path must catch it and record an error, not raise a raw traceback.
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    generation = conversational_answer_stream(
        tmp_path,
        "What is the capital?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        history=[ChatTurn(role="assistant", content="see config {oops")],
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )
    tokens = list(generation)  # must not raise

    assert tokens == []  # nothing streamed
    assert generation.answer is not None
    assert generation.answer.errors  # a generation error was recorded


def test_conversational_answer_decomposes_with_real_aux(tmp_path: Path) -> None:
    queries: list[str] = []

    def retriever(run_dir, query, config):
        queries.append(query)
        return RetrievalResult(chunks=list(_CHUNKS))

    def aux_resolver(config):
        model = _ScriptedModel(reply='["capital of France", "population of France"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "capital and population?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
    )

    assert result.plan.sub_questions == ["capital of France", "population of France"]
    # Phase C retrieves every sub-question in parallel.
    assert sorted(queries) == ["capital of France", "population of France"]


def test_conversational_answer_cached_chunks_skip_retrieval(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):  # pragma: no cover - must not be called
        raise AssertionError("retriever should not be called on a cache hit")

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(),
        cached_chunks=_CHUNKS,
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == "ANSWER"
    assert result.sources == _CHUNKS
    # A cache hit still rolls conversation state forward.
    assert result.state.recent_resolved == ("What is the capital of France?",)


def test_conversational_answer_updates_state(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert "state" in result.timings
    assert result.state.recent_resolved == ("What is the capital of France?",)


def test_conversational_answer_threads_tone_into_prompt(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class _CapturingModel(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capturing"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            captured["system"] = messages[0].content
            return "ANSWER"

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_CapturingModel(), model_id="main"), []

    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", tone="Formal"),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    # The requested tone is baked into the grounded-answer system prompt.
    assert "Formal" in captured["system"]


def test_conversational_answer_populates_followups(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(
            chunks=[RetrievedChunk(text="ctx", source="a.md", score=0.9, metadata={})]
        )

    def aux_resolver(config):
        # Single-topic question short-circuits planning; the same reply supplies
        # the follow-up candidate when suggest_followups invokes the model.
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
    )

    assert [f.question for f in result.follow_ups] == ["What else about France?"]
    assert "followups" in result.timings


def test_conversational_answer_answer_failure_still_returns_followups(tmp_path: Path) -> None:
    class _BoomModel(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "boom"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            raise RuntimeError("model down")

    def retriever(run_dir, query, config):
        return RetrievalResult(
            chunks=[RetrievedChunk(text="ctx", source="a.md", score=0.9, metadata={})]
        )

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_BoomModel(), model_id="main"), []

    def aux_resolver(config):
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=aux_resolver,
    )

    # The answer branch failed, but the concurrent follow-up branch still returned.
    assert result.answer == ""
    assert any(e.code == messages.CODE_GENERATION_FAILED for e in result.errors)
    assert [f.question for f in result.follow_ups] == ["What else about France?"]
