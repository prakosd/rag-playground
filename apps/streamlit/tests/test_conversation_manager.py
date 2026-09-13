"""Tests for grouping, titling, and replaying Step 5 conversations from records."""

from __future__ import annotations

from app_support.conversational_rag.conversation_manager import (
    conversation_summaries,
    conversation_title,
    conversation_turns,
    new_conversation_id,
    new_transaction_id,
    turn_from_record,
)
from app_support.conversational_rag.conversational_rag_history import ConversationalTurnRecord
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
