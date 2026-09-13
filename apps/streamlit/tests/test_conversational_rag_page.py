"""Tests for the Step 5 page's conversation-activation session-state helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

from pytest import MonkeyPatch

from app_support.conversational_rag.conversational_rag_history import ConversationalTurnRecord

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.conversational_rag")


def _record(conversation_id: str, timestamp: str, question: str) -> ConversationalTurnRecord:
    return ConversationalTurnRecord(
        timestamp_utc=timestamp,
        index_folder="v",
        index_run="r",
        embedding_model="e",
        llm_model="main",
        aux_model="aux",
        reranker="off",
        raw_question=question,
        sub_questions=(),
        answer=f"answer to {question}",
        conversation_id=conversation_id,
    )


def test_start_new_conversation_resets_working_set(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._TURNS_KEY: [{"question": "old"}], page._PENDING_KEY: "queued"}
    monkeypatch.setattr(page.st, "session_state", state)

    page._start_new_conversation()

    assert state[page._TURNS_KEY] == []
    assert len(str(state[page._CONV_ID_KEY])) == 6  # a fresh short id
    assert page._PENDING_KEY not in state  # a queued follow-up click is dropped


def test_activate_conversation_rebuilds_turns_from_disk(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {}
    monkeypatch.setattr(page.st, "session_state", state)
    records = [
        _record("c1", "2026-09-01T10:00:00.000+00:00", "first"),
        _record("c1", "2026-09-01T10:01:00.000+00:00", "second"),
        _record("c2", "2026-09-01T10:02:00.000+00:00", "other"),
    ]

    page._activate_conversation("c1", records)

    assert state[page._CONV_ID_KEY] == "c1"
    assert [turn["question"] for turn in state[page._TURNS_KEY]] == ["first", "second"]


def test_ensure_active_conversation_defaults_to_newest_summary(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    monkeypatch.setattr(page.st, "session_state", {})
    records = [
        _record("old", "2026-09-01T09:00:00.000+00:00", "old q"),
        _record("recent", "2026-09-01T10:00:00.000+00:00", "recent q"),
    ]

    page._ensure_active_conversation(records, page.conversation_summaries(records))

    assert page.st.session_state[page._CONV_ID_KEY] == "recent"  # most recently active first


def test_ensure_active_conversation_starts_empty_without_history(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    monkeypatch.setattr(page.st, "session_state", {})

    page._ensure_active_conversation([], [])

    assert page.st.session_state[page._TURNS_KEY] == []
    assert page.st.session_state[page._CONV_ID_KEY]  # a fresh conversation id


def test_ensure_active_conversation_preserves_live_turns(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    monkeypatch.setattr(
        page.st,
        "session_state",
        {page._CONV_ID_KEY: "keep", page._TURNS_KEY: ["live"]},
    )

    page._ensure_active_conversation([], [])

    assert page.st.session_state[page._CONV_ID_KEY] == "keep"  # a later rerun is a no-op
    assert page.st.session_state[page._TURNS_KEY] == ["live"]  # full-fidelity turns kept
