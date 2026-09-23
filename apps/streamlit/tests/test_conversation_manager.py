"""Tests for grouping, titling, and replaying Step 5 conversations from records."""

from __future__ import annotations

from rag_engine import ConversationalAnswer, RetrievedChunk, StagePromptTrace, ValidatedFollowup

from app_support.conversational_rag.conversation_manager import (
    asked_questions_from_records,
    conversation_summaries,
    conversation_title,
    conversation_turns,
    new_conversation_id,
    new_transaction_id,
    trim_old_turn_payloads,
    turn_from_record,
)
from app_support.conversational_rag.conversational_rag_history import (
    ConversationalPromptTrace,
    ConversationalStageUsage,
    ConversationalTurnRecord,
)
from app_support.rag_shared.result_snapshot import StoredResult

_ID_ALPHABET = set("abcdefghijklmnopqrstuvwxyz0123456789")


def _record(
    timestamp: str,
    *,
    conversation_id: str = "conv1",
    question: str = "q",
    answer: str = "a",
    state_summary: str = "",
    sub_questions: tuple[str, ...] = (),
    follow_ups: tuple[str, ...] = (),
    results: tuple[StoredResult, ...] = (),
    token_usage: tuple[ConversationalStageUsage, ...] = (),
    prompt_traces: tuple[ConversationalPromptTrace, ...] = (),
) -> ConversationalTurnRecord:
    return ConversationalTurnRecord(
        timestamp_utc=timestamp,
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="main",
        aux_model="aux",
        reranker="local",
        raw_question=question,
        sub_questions=sub_questions,
        answer=answer,
        follow_ups_shown=follow_ups,
        results=results,
        token_usage=token_usage,
        prompt_traces=prompt_traces,
        conversation_id=conversation_id,
        state_summary=state_summary,
    )


def test_new_ids_are_short_and_path_safe() -> None:
    for value in (new_conversation_id(), new_transaction_id()):
        assert len(value) == 6
        assert set(value) <= _ID_ALPHABET  # lowercase alnum → safe in paths and columns


def test_conversation_title_prefers_summary_then_first_question() -> None:
    assert conversation_title("Rolling summary", "First question?") == "Rolling summary"
    assert conversation_title("", "First question?") == "First question?"
    assert conversation_title("", "") == ""  # caller supplies a localized placeholder


def test_conversation_title_truncates_long_text_with_ellipsis() -> None:
    title = conversation_title("", "x" * 80)

    assert title.endswith("…")
    assert len(title) <= 48


def test_turn_from_record_rebuilds_display_adequate_answer() -> None:
    record = _record(
        "2026-09-01T10:00:00.000+00:00",
        question="What is X?",
        answer="X is Y.",
        state_summary="About X",
        sub_questions=("What is X exactly?",),
        follow_ups=("Tell me more?",),
        results=(StoredResult(source="doc.md", score=0.9, text="body"),),
    )

    turn = turn_from_record(record)
    answer = turn["answer"]

    assert turn["question"] == "What is X?"
    assert answer.answer == "X is Y."
    assert answer.plan.sub_questions == ["What is X exactly?"]
    assert [item.question for item in answer.follow_ups] == ["Tell me more?"]
    assert answer.state.summary == "About X"  # rolling summary seeds continuity
    assert answer.model_used == "main"
    assert [chunk.source for chunk in answer.sources] == ["doc.md"]
    assert answer.sources[0].score == 0.9


def test_turn_from_record_maps_token_usage() -> None:
    record = _record(
        "2026-09-01T10:00:00.000+00:00",
        token_usage=(
            ConversationalStageUsage("answer", "main", 100, 40, 140),
            ConversationalStageUsage("decomposition", "aux", 20, 5, 25),
        ),
    )

    stages = turn_from_record(record)["answer"].token_usage

    # Persisted per-stage tokens rehydrate so a reloaded turn's Inspect shows them.
    assert [(stage.process, stage.model_id, stage.usage.total_tokens) for stage in stages] == [
        ("answer", "main", 140),
        ("decomposition", "aux", 25),
    ]


def test_turn_from_record_maps_prompt_traces() -> None:
    record = _record(
        "2026-09-01T10:00:00.000+00:00",
        prompt_traces=(
            ConversationalPromptTrace(process="decomposition", prompt="P", response="R"),
        ),
    )

    traces = turn_from_record(record)["answer"].prompt_traces

    # Persisted prompt/reply rehydrate so a reloaded turn's Inspect can show them.
    assert [(trace.process, trace.prompt, trace.response) for trace in traces] == [
        ("decomposition", "P", "R")
    ]


def test_conversation_turns_orders_oldest_first_with_sequential_ids() -> None:
    records = [
        _record("2026-09-01T10:02:00.000+00:00", question="second"),
        _record("2026-09-01T10:00:00.000+00:00", question="first"),
        _record("2026-09-01T10:00:00.000+00:00", conversation_id="other", question="skip"),
    ]

    turns = conversation_turns(records, "conv1")

    assert [turn["question"] for turn in turns] == ["first", "second"]
    assert [turn["turn_id"] for turn in turns] == [0, 1]


def test_conversation_summaries_group_newest_first_with_titles() -> None:
    records = [
        _record("2026-09-01T10:00:00.000+00:00", conversation_id="a", question="alpha one"),
        _record(
            "2026-09-01T10:05:00.000+00:00",
            conversation_id="a",
            question="alpha two",
            state_summary="Alpha topic",
        ),
        _record("2026-09-01T09:00:00.000+00:00", conversation_id="b", question="beta only"),
    ]

    summaries = conversation_summaries(records)

    assert [summary.conversation_id for summary in summaries] == ["a", "b"]  # a more recent
    assert summaries[0].turn_count == 2
    assert summaries[0].title == "Alpha topic"  # latest turn's summary wins
    assert summaries[1].title == "beta only"  # falls back to the first question


def test_asked_questions_from_records_folds_dedupes_oldest_first() -> None:
    records = [
        _record("2026-09-01T10:00:00+00:00", sub_questions=("What is CTP?", "Is it costly?")),
        _record("2026-09-01T10:01:00+00:00", sub_questions=("what is ctp?", "How to claim?")),
    ]

    asked = asked_questions_from_records(records, "conv1")

    # Oldest first; "what is ctp?" folds into the earlier "What is CTP?".
    assert asked == ("What is CTP?", "Is it costly?", "How to claim?")


def test_asked_questions_from_records_falls_back_to_raw_question() -> None:
    records = [_record("2026-09-01T10:00:00+00:00", question="Only raw", sub_questions=())]

    assert asked_questions_from_records(records, "conv1") == ("Only raw",)


def test_asked_questions_from_records_ignores_other_conversations() -> None:
    records = [
        _record("2026-09-01T10:00:00+00:00", conversation_id="conv1", sub_questions=("a?",)),
        _record("2026-09-01T10:01:00+00:00", conversation_id="conv2", sub_questions=("b?",)),
    ]

    assert asked_questions_from_records(records, "conv1") == ("a?",)


def test_asked_questions_from_records_caps_history() -> None:
    records = [
        _record(f"2026-09-01T10:{i:02d}:00+00:00", sub_questions=(f"q{i}?",)) for i in range(25)
    ]

    asked = asked_questions_from_records(records, "conv1")

    assert len(asked) == 20
    assert asked[-1] == "q24?"
    assert "q0?" not in asked


def _live_turn(index: int) -> dict:
    chunk = RetrievedChunk(text="t", source="a.md", score=0.9, metadata={})
    answer = ConversationalAnswer(
        answer=f"a{index}",
        sources=[chunk],
        follow_ups=[ValidatedFollowup(question="f?", chunks=[chunk])],
        prompt_traces=[StagePromptTrace(process="reranking", prompt="P", response="R")],
    )
    return {"question": f"q{index}", "answer": answer, "turn_id": index}


def test_trim_old_turn_payloads_frees_old_chunks_keeps_text() -> None:
    turns = [_live_turn(0), _live_turn(1), _live_turn(2)]

    trim_old_turn_payloads(turns, keep_recent=1)

    assert turns[0]["answer"].sources == []
    assert turns[0]["answer"].prompt_traces == []
    assert turns[0]["answer"].follow_ups[0].chunks == []
    assert turns[0]["answer"].answer == "a0"  # transcript text preserved
    assert turns[-1]["answer"].sources  # newest turn kept intact
    assert turns[-1]["answer"].prompt_traces  # newest turn's prompts kept
    assert turns[-1]["answer"].follow_ups[0].chunks


def test_trim_old_turn_payloads_noop_within_cap() -> None:
    turns = [_live_turn(0)]

    trim_old_turn_payloads(turns, keep_recent=30)

    assert turns[0]["answer"].sources  # within cap → untouched
