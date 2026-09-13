from __future__ import annotations

from pathlib import Path

from app_support.conversational_rag.conversational_rag_history import (
    CONVERSATIONAL_RAG_HISTORY_DIRNAME,
    ConversationalStageUsage,
    ConversationalTurnRecord,
    append_conversational_rag_record,
    load_conversational_rag_history,
    set_conversational_rag_pinned,
)
from app_support.rag_shared.result_snapshot import StoredResult


def _record(
    timestamp: str = "2026-09-01T00:00:00Z", raw_question: str = "q", pinned: bool = False
) -> ConversationalTurnRecord:
    return ConversationalTurnRecord(
        timestamp_utc=timestamp,
        index_folder="vector_01_x",
        index_run="2026",
        embedding_model="titan",
        llm_model="nova",
        aux_model="nova-micro",
        reranker="off",
        raw_question=raw_question,
        sub_questions=("q",),
        answer="A",
        results=(StoredResult(source="a.md", score=0.9, text="c"),),
        follow_ups_shown=("f1",),
        follow_ups_dropped=("f2",),
        pinned=pinned,
    )


def test_append_and_load_round_trip_newest_first(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record(timestamp="t1", raw_question="first"))
    append_conversational_rag_record(tmp_path, _record(timestamp="t2", raw_question="second"))

    records = load_conversational_rag_history(tmp_path)

    assert [record.raw_question for record in records] == ["second", "first"]
    csv_path = tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME / "conversational_rag_history.csv"
    assert csv_path.is_file()


def test_results_and_followups_persist(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record())

    record = load_conversational_rag_history(tmp_path)[0]

    assert record.sub_questions == ("q",)
    assert record.results[0].text == "c"
    assert record.follow_ups_shown == ("f1",)
    assert record.follow_ups_dropped == ("f2",)


def test_conversation_and_transaction_ids_round_trip(tmp_path: Path) -> None:
    record = ConversationalTurnRecord(
        timestamp_utc="t1",
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="nova",
        aux_model="micro",
        reranker="off",
        raw_question="q",
        sub_questions=(),
        answer="A",
        conversation_id="conv42",
        transaction_id="txn99",
        state_summary="rolling summary",
    )
    append_conversational_rag_record(tmp_path, record)

    loaded = load_conversational_rag_history(tmp_path)[0]

    assert loaded.conversation_id == "conv42"
    assert loaded.transaction_id == "txn99"
    assert loaded.state_summary == "rolling summary"
    csv_text = (
        tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME / "conversational_rag_history.csv"
    ).read_text(encoding="utf-8")
    assert "conv42" in csv_text and "txn99" in csv_text  # exported for download


def test_legacy_records_without_ids_default_to_empty(tmp_path: Path) -> None:
    directory = tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME
    directory.mkdir(parents=True)
    # A pre-feature line lacking conversation_id / transaction_id / state_summary.
    (directory / "conversational_rag_history.jsonl").write_text(
        '{"timestamp_utc": "t1", "raw_question": "q", "answer": "A"}\n', encoding="utf-8"
    )

    loaded = load_conversational_rag_history(tmp_path)[0]

    assert loaded.conversation_id == ""
    assert loaded.transaction_id == ""
    assert loaded.state_summary == ""


def test_token_usage_round_trips(tmp_path: Path) -> None:
    record = ConversationalTurnRecord(
        timestamp_utc="t1",
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="nova",
        aux_model="micro",
        reranker="off",
        raw_question="q",
        sub_questions=(),
        answer="A",
        token_usage=(
            ConversationalStageUsage("answer", "nova", 10, 20, 30),
            ConversationalStageUsage("decomposition", "micro", None, None, None),
        ),
    )
    append_conversational_rag_record(tmp_path, record)

    loaded = load_conversational_rag_history(tmp_path)[0]

    assert loaded.token_usage == record.token_usage


def test_pinned_records_sort_first(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record(timestamp="t1", raw_question="old"))
    append_conversational_rag_record(tmp_path, _record(timestamp="t2", raw_question="new"))

    set_conversational_rag_pinned(tmp_path, "t1", True)
    records = load_conversational_rag_history(tmp_path)

    assert records[0].raw_question == "old"  # pinned sorts first
    assert records[0].pinned is True


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    directory = tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME
    directory.mkdir(parents=True)
    (directory / "conversational_rag_history.jsonl").write_text("not json\n", encoding="utf-8")

    assert load_conversational_rag_history(tmp_path) == []
