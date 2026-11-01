"""Tests for the showcase route: signed-token build resolution and the ?show branch."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from app_support.conversational_rag import showcase_route as route
from app_support.conversational_rag.build_manager import make_showcase_token
from app_support.conversational_rag.showcase_route import resolve_build_root
from app_support.session_manager import session_dir

_APP_DIR = Path(__file__).resolve().parents[1]
_SECRET = "showcase-secret"


def _seed_build(sessions_root: Path, session_id: str, build_name: str) -> Path:
    build = session_dir(sessions_root, session_id) / build_name
    build.mkdir(parents=True)
    (build / "build.json").write_text("{}", encoding="utf-8")
    return build


def test_resolve_build_root_valid_token(tmp_path: Path) -> None:
    _seed_build(tmp_path, "winter_apple", "rag_build_01_garden")
    token = make_showcase_token("winter_apple", "rag_build_01_garden", _SECRET)
    root = resolve_build_root(token, tmp_path, _SECRET)
    assert root is not None
    assert root.name == "rag_build_01_garden"


def test_resolve_build_root_rejects_forged_token(tmp_path: Path) -> None:
    _seed_build(tmp_path, "winter_apple", "rag_build_01_garden")
    token = make_showcase_token("winter_apple", "rag_build_01_garden", _SECRET)
    assert resolve_build_root(token, tmp_path, "other-secret") is None


def test_resolve_build_root_none_when_build_missing(tmp_path: Path) -> None:
    token = make_showcase_token("winter_apple", "rag_build_01_garden", _SECRET)
    assert resolve_build_root(token, tmp_path, _SECRET) is None


def test_resolve_build_root_none_for_garbage(tmp_path: Path) -> None:
    assert resolve_build_root("garbage", tmp_path, _SECRET) is None


def _route_script() -> None:
    import streamlit as st

    from app_support.conversational_rag.showcase_route import maybe_render_showcase

    st.session_state["_rendered"] = maybe_render_showcase()


def _page_kwargs_script() -> None:
    import streamlit as st

    from app_support.conversational_rag.showcase_route import maybe_render_showcase

    original = st.Page
    captured: dict[str, object] = {}

    def _spy(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return original(*args, **kwargs)

    st.Page = _spy  # type: ignore[assignment]
    try:
        maybe_render_showcase()
    finally:
        st.Page = original  # type: ignore[assignment]
    st.session_state["_page_kwargs"] = captured


def test_maybe_render_showcase_is_inert_without_token() -> None:
    # The normal app must not be hijacked when there is no ?show token.
    app = AppTest.from_function(_route_script).run()
    assert not app.exception
    assert app.session_state["_rendered"] is False


def test_maybe_render_showcase_invalid_token_shows_unavailable() -> None:
    # An invalid link renders the chrome-less "unavailable" page (nav hidden).
    app = AppTest.from_function(_route_script)
    app.query_params["show"] = "garbage"
    app.run()
    assert not app.exception
    assert app.session_state["_rendered"] is True
    assert app.title  # the unavailable notice rendered


def test_showcase_page_served_at_root() -> None:
    # The showcase must register as the default page with an empty url_path so
    # Streamlit routes the "/?show=…" link to it. Any token reaches st.Page, so a
    # garbage one suffices to capture the kwargs.
    app = AppTest.from_function(_page_kwargs_script)
    app.query_params["show"] = "garbage"
    app.run()
    assert not app.exception
    assert app.session_state["_page_kwargs"]["url_path"] == ""
    assert app.session_state["_page_kwargs"]["default"] is True


def test_maybe_render_showcase_valid_token_renders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A valid link renders the chat-only showcase via st.Page(partial, title=…).
    from vector_indexer.manifest import write_manifest

    from app_support.conversational_rag.build_manager import BuildSnapshot, create_build

    monkeypatch.syspath_prepend(str(_APP_DIR))
    monkeypatch.setattr(route, "_SESSIONS_ROOT", tmp_path)
    monkeypatch.setattr(route, "get_settings", lambda: SimpleNamespace(zip_signing_secret=_SECRET))
    session_root = session_dir(tmp_path, "winter_apple")
    run = session_root / "vector_01_slate" / "2026-10-28_10-00-00"
    run.mkdir(parents=True)
    (run / "chroma").mkdir()
    write_manifest(
        run,
        {
            "success": True,
            "indexed_chunk_count": 5,
            "embedding_model_used": "titan",
            "collection_name": "c",
        },
    )
    snapshot = BuildSnapshot(
        schema_version=1,
        created_at_utc="2026-10-30T07:48:40+00:00",
        name="rag_build_01_garden",
        language="EN",
        answer_model="echo",
        top_k=5,
        tone="Neutral",
        reranker="off",
        aux_model_id="echo",
        decomposition_limit=1,
        followup_show_count=0,
        inspect=False,
        followup_drop=0.3,
        followup_keep=0.6,
        followup_probe_k=3,
        answerability_chunks=2,
        state_summary_start_turn=4,
        state_summary_max_words=150,
        answer_recent_turns=5,
        plan_recent_turns=2,
        index_vector_folder="vector_01_slate",
        index_run_name="2026-10-28_10-00-00",
        embedding_model="titan",
    )
    create_build(session_root, snapshot, run, {})
    token = make_showcase_token("winter_apple", "rag_build_01_garden", _SECRET)

    app = AppTest.from_function(_route_script)
    app.query_params["show"] = token
    app.run(timeout=10)

    assert not app.exception
    assert app.session_state["_rendered"] is True
    assert app.chat_input  # the showcase chat (not the unavailable page) rendered
