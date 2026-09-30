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
