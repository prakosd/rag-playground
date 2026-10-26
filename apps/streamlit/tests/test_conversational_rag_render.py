"""AppTest coverage for the Step 5 conversational RAG page's fresh render.

The page only calls the heavy ``conversational_answer_stream`` when a turn is
submitting, so a fresh (empty-conversation) render exercises the controls, welcome
bubble, conversation picker, chat input, token panel, and downloads with no stream
mock — complementing the pure-helper tests in ``test_conversational_rag_page.py``.
"""

from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from streamlit.testing.v1 import AppTest

_APP_DIR = Path(__file__).resolve().parents[1]


def _render_conversational(session_dir: str) -> None:
    # Self-contained render for AppTest.from_function (isolated namespace).
    from pathlib import Path as _Path

    import app_pages.conversational_rag as page
    from vector_indexer import IndexManifest

    from app_support.rag_shared.index_catalog import IndexRef
    from app_support.rag_shared.rag_ui import RagPageContext

    root = _Path(session_dir)
    manifest = IndexManifest(
        embedding_model_requested="titan",
        embedding_model_used="titan",
        embedding_dimension=512,
        collection_name="c",
        chunk_size=600,
        chunk_overlap=100,
        language="english",
        success=True,
        indexed_file_count=1,
        indexed_chunk_count=3,
        skipped_file_count=0,
        indexed_sources=("a.md",),
    )
    ref = IndexRef(
        run_dir=root / "idx",
        vector_folder="vector_01_x",
        run_name="2026-07-01_09-00-00",
        manifest=manifest,
    )
    context = RagPageContext(
        default_language="EN",
        list_indexes=lambda: [ref],
        render_downloads=lambda: None,
        session_root=lambda: root,
    )
    page.render_page(context)


# Risk: the conversational RAG page's fresh render (controls, welcome, picker, chat
# input, token panel) is untested. Type: unit (AppTest).
def test_conversational_rag_renders_fresh_conversation(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))
    app = AppTest.from_function(_render_conversational, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)

    assert not app.exception
    assert app.chat_input  # the docked chat composer renders
    # A fresh conversation seeds a new short id into session state.
    assert app.session_state["conversational_rag_current_id"]
    assert app.session_state["conversational_rag_turns"] == []


def _render_with_followups(session_dir: str) -> None:
    # Seed one saved turn carrying a follow-up, then render the page (isolated namespace).
    from pathlib import Path as _Path

    import app_pages.conversational_rag as page

    from app_support.conversational_rag.conversational_rag_history import (
        ConversationalTurnRecord,
        append_conversational_rag_record,
    )
    from app_support.rag_shared.rag_ui import RagPageContext

    root = _Path(session_dir)
    append_conversational_rag_record(
        root,
        ConversationalTurnRecord(
            timestamp_utc="2026-09-01T10:00:00.000+00:00",
            index_folder="vector_01_x",
            index_run="2026-07-01_09-00-00",
            embedding_model="titan",
            llm_model="main",
            aux_model="aux",
            reranker="off",
            raw_question="What is X?",
            sub_questions=(),
            answer="X is a thing.",
            follow_ups_shown=("Tell me more about X?",),
            conversation_id="c1",
        ),
    )
    context = RagPageContext(
        default_language="EN",
        list_indexes=lambda: [],
        render_downloads=lambda: None,
        session_root=lambda: root,
    )
    page.render_page(context)


# Smoke test: a conversation with a saved follow-up exercises the restructured render
# path (follow-ups + the deferred Inspect render inside the `st.empty` slot the next turn
# clears) and must load + render without raising. Type: unit (AppTest).
def test_conversational_rag_renders_turn_with_followups(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))
    app = AppTest.from_function(_render_with_followups, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)

    assert not app.exception  # the follow-ups-present render path renders cleanly
    assert len(app.session_state["conversational_rag_turns"]) == 1  # the saved turn loaded


def _render_inspect_controls(session_dir: str) -> None:
    # Render only the advanced controls with a valid index, stashing the Inspect result.
    from pathlib import Path as _Path

    import streamlit as st
    from vector_indexer import IndexManifest

    from app_support.conversational_rag.conversational_rag_form_ui import render_advanced_controls
    from app_support.i18n import STRINGS_EN
    from app_support.rag_shared.index_catalog import IndexRef

    root = _Path(session_dir)
    manifest = IndexManifest(
        embedding_model_requested="titan",
        embedding_model_used="titan",
        embedding_dimension=512,
        collection_name="c",
        chunk_size=600,
        chunk_overlap=100,
        language="english",
        success=True,
        indexed_file_count=1,
        indexed_chunk_count=3,
        skipped_file_count=0,
        indexed_sources=("a.md",),
    )
    ref = IndexRef(
        run_dir=root / "idx",
        vector_folder="vector_01_x",
        run_name="2026-07-01_09-00-00",
        manifest=manifest,
    )
    controls = render_advanced_controls(STRINGS_EN, "conversational_rag", [ref], root)
    st.session_state["_inspect_result"] = controls.inspect


# The Inspect toggle is off by default on a fresh render. Type: unit (AppTest).
def test_inspect_off_by_default(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))
    app = AppTest.from_function(_render_inspect_controls, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)

    assert not app.exception
    assert app.session_state["_inspect_result"] is False
    assert app.session_state["conversational_rag_inspect_on"] is False  # the mirrored preference


# Regression: enabling Inspect then switching browser sessions dropped the toggle's own
# widget state on the page-less reruns, so Inspect read off while the toggle still showed
# on (the per-turn Inspect expander vanished until the user toggled off+on). The
# preference now lives in a plain key that survives the switch and re-seeds the toggle, so
# a switched-to session with the preference set (but no toggle widget state) still reads
# on and shows the toggle on. Type: unit (AppTest).
def test_inspect_reads_persisted_preference_after_switch(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))
    app = AppTest.from_function(_render_inspect_controls, kwargs={"session_dir": str(tmp_path)})
    # The switched-to session kept the plain preference but not the toggle's widget state.
    app.session_state["conversational_rag_inspect_on"] = True
    app.run(timeout=10)

    assert not app.exception
    assert app.session_state["_inspect_result"] is True  # Inspect still reads on (was off)
    assert app.session_state["conversational_rag_inspect"] is True  # the toggle re-seeds on
    assert app.session_state["conversational_rag_inspect_on"] is True  # the preference is kept
