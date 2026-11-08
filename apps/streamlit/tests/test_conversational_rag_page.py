"""Tests for the Step 5 page's conversation-activation session-state helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

from pytest import MonkeyPatch
from rag_engine import ConversationalAnswer
from rag_engine import messages as rag_messages

from app_support.conversational_rag.conversation_manager import ConversationSummary
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


def test_newest_user_turn_key_prefers_pending_then_latest(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    prefix = page._USER_TURN_KEY_PREFIX

    # Streaming a new turn: pin the pending question (turn_id == len(turns)).
    assert page._newest_user_turn_key([{"turn_id": 0}], submitting=True) == f"{prefix}1"
    # Idle with history: pin the latest stored turn by its own turn_id.
    assert (
        page._newest_user_turn_key([{"turn_id": 0}, {"turn_id": 1}], submitting=False)
        == f"{prefix}1"
    )
    # Fresh, empty conversation: nothing to scroll to.
    assert page._newest_user_turn_key([], submitting=False) is None


def test_turn_failed_flags_errors_or_empty_answer(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # Errors mean the turn could not be answered → show the natural reply instead.
    failed = ConversationalAnswer(answer="", errors=[rag_messages.retrieval_failed("ssl boom")])
    assert page._turn_failed(failed) is True
    # A replayed failure reloads with no answer and no errors (history drops them).
    assert page._turn_failed(ConversationalAnswer(answer="")) is True
    # A plain answer, or one carrying only warnings, is not a failure.
    assert page._turn_failed(ConversationalAnswer(answer="ok")) is False
    only_warn = ConversationalAnswer(answer="ok", warnings=[rag_messages.no_context()])
    assert page._turn_failed(only_warn) is False


def test_error_reply_picks_an_editable_alternate(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    strings = {"CONV_ERROR_REPLY_DEFAULT": "one\ntwo\nthree"}
    # No session override → one of the built-in alternates, chosen per turn.
    assert page._error_reply(strings, None, 0) in {"one", "two", "three"}


def test_turn_in_flight_detects_queued_question(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # A queued question means a turn is about to stream → inputs lock so a mid-stream
    # widget change can't interrupt the run and drop the just-streamed turn.
    assert page._turn_in_flight({page._PENDING_KEY: "What is CTP?"}) is True
    # No pending, or a blank/None one, leaves the controls live.
    assert page._turn_in_flight({}) is False
    assert page._turn_in_flight({page._PENDING_KEY: "   "}) is False
    assert page._turn_in_flight({page._PENDING_KEY: None}) is False


def test_inspect_deferred_only_for_latest_with_followups(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # The latest turn defers its Inspect panel below the follow-ups only when follow-ups
    # show; deferring regardless of streaming keeps the panel in one stable position so a
    # mid-stream re-render can't leave a duplicate copy behind.
    assert page._inspect_deferred(is_latest=True, followups_enabled=True) is True
    assert page._inspect_deferred(is_latest=True, followups_enabled=False) is False
    assert page._inspect_deferred(is_latest=False, followups_enabled=True) is False
    assert page._inspect_deferred(is_latest=False, followups_enabled=False) is False


def test_showcase_visible_summaries_filters_to_owned(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # A showcase visitor sees only the conversations they started (privacy boundary).
    monkeypatch.setattr(page.st, "session_state", {page._SHOWCASE_CONV_IDS_KEY: {"mine1", "mine2"}})
    summaries = [
        ConversationSummary("mine1", "My first", 2, "2026-09-01T10:00:00+00:00"),
        ConversationSummary("other", "Not mine", 1, "2026-09-01T11:00:00+00:00"),
        ConversationSummary("mine2", "My second", 3, "2026-09-01T12:00:00+00:00"),
    ]

    visible = page._showcase_visible_summaries(summaries)

    assert [summary.conversation_id for summary in visible] == ["mine1", "mine2"]


def test_register_showcase_conversation_marks_active_as_owned(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "abc123"}
    monkeypatch.setattr(page.st, "session_state", state)

    page._register_showcase_conversation()

    assert state[page._SHOWCASE_CONV_IDS_KEY] == {"abc123"}


def test_register_showcase_conversation_ignores_empty_active(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: ""}
    monkeypatch.setattr(page.st, "session_state", state)

    page._register_showcase_conversation()

    assert state[page._SHOWCASE_CONV_IDS_KEY] == set()


def test_sync_showcase_conversations_hydrates_and_persists(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "abc123"}
    monkeypatch.setattr(page.st, "session_state", state)
    captured: dict[str, object] = {}

    def _fake_sync(slug: str, pending: list[str]) -> list[str]:
        captured["slug"] = slug
        captured["pending"] = pending
        return ["stored1", "abc123"]

    monkeypatch.setattr(page, "sync_showcase_conversation_ids", _fake_sync)
    records = [_record("abc123", "2026-09-01T10:00:00.000+00:00", "q")]

    page._sync_showcase_conversations("slug_one", records)

    # The active conversation has a saved turn, so it is offered for persistence,
    assert captured == {"slug": "slug_one", "pending": ["abc123"]}
    # and the stored ids hydrate the visitor's private picker set.
    assert state[page._SHOWCASE_CONV_IDS_KEY] == {"stored1", "abc123"}


def test_sync_showcase_conversations_skips_unsaved_active_id(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "fresh1"}
    monkeypatch.setattr(page.st, "session_state", state)
    captured: dict[str, object] = {}

    def _fake_sync(slug: str, pending: list[str]) -> list[str]:
        captured["pending"] = pending
        return ["stored1"]

    monkeypatch.setattr(page, "sync_showcase_conversation_ids", _fake_sync)

    # No saved turn yet for the active conversation, so it is not persisted.
    page._sync_showcase_conversations("slug_one", [])

    assert captured["pending"] == []
    assert state[page._SHOWCASE_CONV_IDS_KEY] == {"stored1"}


def test_sync_showcase_conversations_noop_without_slug(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {}
    monkeypatch.setattr(page.st, "session_state", state)
    calls: list[object] = []
    monkeypatch.setattr(
        page, "sync_showcase_conversation_ids", lambda *args: calls.append(args) or []
    )

    page._sync_showcase_conversations("", [])
    page._sync_showcase_conversations(None, [])

    # No slug means no bridge call and no storage-key write.
    assert calls == []
    assert page._SHOWCASE_CONV_IDS_KEY not in state


def test_sync_showcase_conversations_returns_hydration_flag(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "abc123"}
    monkeypatch.setattr(page.st, "session_state", state)
    monkeypatch.setattr(page, "sync_showcase_conversation_ids", lambda slug, pending: ["abc123"])
    monkeypatch.setattr(page, "showcase_conversations_hydrated", lambda slug: True)
    records = [_record("abc123", "2026-09-01T10:00:00.000+00:00", "q")]

    assert page._sync_showcase_conversations("slug_one", records) is True
    # Without a slug the bridge never mounts, so it reports not-hydrated.
    assert page._sync_showcase_conversations(None, []) is False


def test_showcase_initial_conversation_selects_latest_once_hydrated(
    monkeypatch: MonkeyPatch,
) -> None:
    page = _page(monkeypatch)
    # First load started an empty conversation; the visitor owns saved ones.
    state: dict[str, object] = {page._CONV_ID_KEY: "empty1", page._TURNS_KEY: []}
    monkeypatch.setattr(page.st, "session_state", state)
    records = [
        _record("old", "2026-09-01T09:00:00.000+00:00", "old q"),
        _record("recent", "2026-09-01T10:00:00.000+00:00", "recent q"),
    ]
    summaries = page.conversation_summaries(records)

    page._ensure_showcase_initial_conversation(records, summaries, hydrated=True)

    assert state[page._CONV_ID_KEY] == "recent"  # newest shown on first load
    assert state[page._SHOWCASE_INIT_KEY] is True


def test_showcase_initial_conversation_waits_for_hydration(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "empty1", page._TURNS_KEY: []}
    monkeypatch.setattr(page.st, "session_state", state)
    records = [_record("recent", "2026-09-01T10:00:00.000+00:00", "q")]
    summaries = page.conversation_summaries(records)

    # Pre-hydration: do nothing and stay un-initialised so a later run can act.
    page._ensure_showcase_initial_conversation(records, summaries, hydrated=False)

    assert state[page._CONV_ID_KEY] == "empty1"
    assert page._SHOWCASE_INIT_KEY not in state


def test_showcase_initial_conversation_new_visitor_stays_fresh(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._CONV_ID_KEY: "empty1", page._TURNS_KEY: []}
    monkeypatch.setattr(page.st, "session_state", state)

    # No saved conversations for this visitor: keep the fresh empty one, mark done.
    page._ensure_showcase_initial_conversation([], [], hydrated=True)

    assert state[page._CONV_ID_KEY] == "empty1"
    assert state[page._SHOWCASE_INIT_KEY] is True


def test_showcase_initial_conversation_runs_once(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # Already initialised and the visitor started a new conversation; don't override it.
    state: dict[str, object] = {
        page._CONV_ID_KEY: "mynew",
        page._TURNS_KEY: [],
        page._SHOWCASE_INIT_KEY: True,
    }
    monkeypatch.setattr(page.st, "session_state", state)
    records = [_record("recent", "2026-09-01T10:00:00.000+00:00", "q")]
    summaries = page.conversation_summaries(records)

    page._ensure_showcase_initial_conversation(records, summaries, hydrated=True)

    assert state[page._CONV_ID_KEY] == "mynew"  # the user's choice is preserved


def test_showcase_initial_conversation_preserves_live_turns(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # The visitor is already mid-conversation (has turns); don't swap it out.
    state: dict[str, object] = {page._CONV_ID_KEY: "live1", page._TURNS_KEY: ["turn"]}
    monkeypatch.setattr(page.st, "session_state", state)
    records = [_record("recent", "2026-09-01T10:00:00.000+00:00", "q")]
    summaries = page.conversation_summaries(records)

    page._ensure_showcase_initial_conversation(records, summaries, hydrated=True)

    assert state[page._CONV_ID_KEY] == "live1"  # not overridden
    assert state[page._SHOWCASE_INIT_KEY] is True


def test_showcase_panel_css_makes_panel_resizable(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    css = page._showcase_panel_css("rgba(0,0,0,0.2)", 460)
    # The showcase panel is a CSS-built, user-resizable scroll box scoped to the panel key.
    assert f".st-key-{page._CHAT_PANEL_KEY}" in css
    assert "resize:vertical" in css
    assert "overflow-y:auto" in css
    assert "height:460px" in css
    assert "min-height" in css
    assert "flex:none" in css  # so the panel's own height applies (not a flex-grow item)
    # Only the top corners are rounded; the bottom two are squared so the panel welds
    # flush to the chat input docked below it (matching Step 5).
    assert "border-top-left-radius:0.5rem" in css
    assert "border-top-right-radius:0.5rem" in css
    assert "border-bottom-left-radius:0" in css
    assert "border-bottom-right-radius:0" in css
    # The old Small/Medium/Large control is gone.
    assert not hasattr(page, "_render_showcase_panel_height")


def test_panel_dock_css_pulls_panel_up_under_controls(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # A negative top margin on the panel key trims the default block gap so the panel
    # sits snug under the New-conversation + picker row (mirrors _INPUT_DOCK_CSS below).
    assert f".st-key-{page._CHAT_PANEL_KEY}" in page._PANEL_DOCK_CSS
    assert "margin-top:-" in page._PANEL_DOCK_CSS
    assert not hasattr(page, "_SHOWCASE_PANEL_HEIGHTS")
