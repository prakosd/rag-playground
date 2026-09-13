"""Tests for the Step 5 Token usage panel aggregation over per-turn stage usage."""

from __future__ import annotations

import re

import pytest

from app_support.conversational_rag import conversational_token_ui as ctu
from app_support.conversational_rag.conversational_rag_history import (
    ConversationalStageUsage,
    ConversationalTurnRecord,
)
from app_support.conversational_rag.conversational_token_ui import (
    conversational_token_panel_data,
)
from app_support.i18n import STRINGS_EN


def _record(timestamp: str, *stages: ConversationalStageUsage) -> ConversationalTurnRecord:
    return ConversationalTurnRecord(
        timestamp_utc=timestamp,
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="main",
        aux_model="aux",
        reranker="off",
        raw_question="q",
        sub_questions=(),
        answer="a",
        token_usage=stages,
    )


def _no_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ctu, "estimate_cost", lambda model, _in, _out: None)
    monkeypatch.setattr(ctu, "get_model_price", lambda model: None)


def test_panel_data_aggregates_tokens_across_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_pricing(monkeypatch)
    records = [
        _record(
            "2026-09-01T10:00:00+00:00",
            ConversationalStageUsage("answer", "main", 10, 20, 30),
            ConversationalStageUsage("decomposition", "aux", 1, 2, 3),
        )
    ]

    data = conversational_token_panel_data(STRINGS_EN, records)

    assert data.input_tokens == 11
    assert data.output_tokens == 22
    assert data.total_tokens == 33
    assert len(data.rows) == 2  # one row per process


def test_panel_data_rows_use_localized_process_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_pricing(monkeypatch)
    records = [
        _record("2026-09-01T10:00:00+00:00", ConversationalStageUsage("answer", "main", 5, 5, 10))
    ]

    data = conversational_token_panel_data(STRINGS_EN, records)

    assert data.rows[0][STRINGS_EN["BASIC_QA_TXN_COL_PROCESS"]] == STRINGS_EN["CONV_PROCESS_ANSWER"]


def test_panel_data_empty_without_records() -> None:
    data = conversational_token_panel_data(STRINGS_EN, [])

    assert data.total_tokens == 0
    assert data.rows == []


def test_panel_data_sums_costs_when_priced(monkeypatch: pytest.MonkeyPatch) -> None:
    # A direction-aware fake: 1e-6 per input token, 2e-6 per output token.
    monkeypatch.setattr(
        ctu, "estimate_cost", lambda model, _in, _out: (_in or 0) * 1e-6 + (_out or 0) * 2e-6
    )
    monkeypatch.setattr(ctu, "get_model_price", lambda model: None)
    records = [
        _record(
            "2026-09-01T10:00:00+00:00",
            ConversationalStageUsage("answer", "main", 1000, 500, 1500),
        )
    ]

    data = conversational_token_panel_data(STRINGS_EN, records)

    assert data.input_cost == pytest.approx(1000 * 1e-6)
    assert data.output_cost == pytest.approx(500 * 2e-6)
    assert data.total_cost == pytest.approx(1000 * 1e-6 + 500 * 2e-6)


def test_panel_data_merges_repeated_same_process_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    # The answerability probe runs once per sub-question, so a turn can report
    # several identical (process, model) stages; they must collapse to one row.
    _no_pricing(monkeypatch)
    records = [
        _record(
            "2026-09-01T10:00:00.000+00:00",
            ConversationalStageUsage("answerability", "aux", 10, 1, 11),
            ConversationalStageUsage("answerability", "aux", 20, 2, 22),
            ConversationalStageUsage("answerability", "aux", 30, 3, 33),
            ConversationalStageUsage("answer", "main", 100, 50, 150),
        )
    ]

    data = conversational_token_panel_data(STRINGS_EN, records)

    process_col = STRINGS_EN["BASIC_QA_TXN_COL_PROCESS"]
    assert len(data.rows) == 2  # three probes merge; answer stays separate
    merged = next(row for row in data.rows if str(row[process_col]).startswith("3×"))
    assert merged[process_col] == STRINGS_EN["CONV_PROCESS_MULTI"].format(
        count=3, process=STRINGS_EN["CONV_PROCESS_ANSWERABILITY"]
    )
    assert merged[STRINGS_EN["BASIC_QA_SUMMARY_INPUT_LABEL"]] == 60  # 10 + 20 + 30
    assert merged[STRINGS_EN["BASIC_QA_SUMMARY_OUTPUT_LABEL"]] == 6  # 1 + 2 + 3
    assert merged[STRINGS_EN["BASIC_QA_SUMMARY_TOTAL_LABEL"]] == 66  # 11 + 22 + 33
    assert data.input_tokens == 160  # merging leaves totals unchanged
    assert data.output_tokens == 56


def test_panel_data_transaction_time_shows_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    # ms precision distinguishes turns that share a wall-clock minute.
    _no_pricing(monkeypatch)
    records = [
        _record(
            "2026-09-01T10:00:05.482+00:00",
            ConversationalStageUsage("answer", "main", 5, 5, 10),
        )
    ]

    data = conversational_token_panel_data(STRINGS_EN, records)

    time_label = str(data.rows[0][STRINGS_EN["BASIC_QA_TXN_COL_TIME"]])
    assert re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", time_label)  # HH:MM:SS.mmm
    assert ".482" in time_label  # sub-second survives the local-time conversion


def test_panel_data_rows_include_conversation_and_transaction_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_pricing(monkeypatch)
    record = ConversationalTurnRecord(
        timestamp_utc="2026-09-01T10:00:00.000+00:00",
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="main",
        aux_model="aux",
        reranker="off",
        raw_question="q",
        sub_questions=(),
        answer="a",
        token_usage=(ConversationalStageUsage("answer", "main", 5, 5, 10),),
        conversation_id="conv7",
        transaction_id="txn3",
    )

    data = conversational_token_panel_data(STRINGS_EN, [record])

    row = data.rows[0]
    assert row[STRINGS_EN["CONV_TXN_COL_CONVERSATION"]] == "conv7"  # traces the chat
    assert row[STRINGS_EN["CONV_TXN_COL_TRANSACTION"]] == "txn3"  # traces the turn
