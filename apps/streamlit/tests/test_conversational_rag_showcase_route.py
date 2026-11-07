"""Tests for the showcase route: slug-based build resolution and the ?showcase branch."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app_support.conversational_rag import showcase_route as route
from app_support.conversational_rag.build_manager import BuildSnapshot
from app_support.conversational_rag.showcase_route import resolve_build_root
from app_support.session_manager import session_dir

_APP_DIR = Path(__file__).resolve().parents[1]


def _snapshot(slug: str, name: str = "rag_build_01_garden") -> BuildSnapshot:
    return BuildSnapshot(
        schema_version=1,
        created_at_utc="2026-10-30T07:48:40+00:00",
        name=name,
        slug=slug,
        language="EN",
        answer_model="echo",
        top_k=5,
        tone="Neutral",
        reranker="off",
        aux_model_id="echo",
        decomposition_limit=1,
        followup_show_count=0,
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
        prompts={"welcome": "Frozen greeting"},
    )


def _seed_build(sessions_root: Path, session_id: str, build_name: str, slug: str) -> Path:
    run_dir = session_dir(sessions_root, session_id) / build_name / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "build.json").write_text(
        _snapshot(slug, name=build_name).to_json(), encoding="utf-8"
    )
    return run_dir.parent


def test_resolve_build_root_finds_slug(tmp_path: Path) -> None:
    _seed_build(tmp_path, "winter_apple", "rag_build_01_garden", "alpha_beta_gamma_delta_epsilon")
    root = resolve_build_root("alpha_beta_gamma_delta_epsilon", tmp_path)
    assert root is not None
    assert root.name == "rag_build_01_garden"


def test_resolve_build_root_unknown_slug_is_none(tmp_path: Path) -> None:
    _seed_build(tmp_path, "winter_apple", "rag_build_01_garden", "alpha_beta_gamma_delta_epsilon")
    assert resolve_build_root("nope_nope_nope_nope_nope", tmp_path) is None


def test_resolve_build_root_empty_is_none(tmp_path: Path) -> None:
    assert resolve_build_root("", tmp_path) is None


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
    # The normal app must not be hijacked when there is no ?showcase token.
    app = AppTest.from_function(_route_script).run()
    assert not app.exception
    assert app.session_state["_rendered"] is False


def test_maybe_render_showcase_invalid_token_shows_unavailable() -> None:
    # An invalid link renders the chrome-less "unavailable" page (nav hidden).
    app = AppTest.from_function(_route_script)
    app.query_params["showcase"] = "garbage"
    app.run()
    assert not app.exception
    assert app.session_state["_rendered"] is True
    assert app.title  # the unavailable notice rendered


def test_showcase_page_served_at_root() -> None:
    # The showcase must register as the default page with an empty url_path so
    # Streamlit routes the "/?showcase=…" link to it. Any token reaches st.Page, so a
    # garbage one suffices to capture the kwargs.
    app = AppTest.from_function(_page_kwargs_script)
    app.query_params["showcase"] = "garbage"
    app.run()
    assert not app.exception
    assert app.session_state["_page_kwargs"]["url_path"] == ""
    assert app.session_state["_page_kwargs"]["default"] is True


def _seed_full_build(tmp_path: Path) -> str:
    """Seed a build referencing a session index under *tmp_path*; return its slug."""
    from vector_indexer.manifest import write_manifest

    from app_support.conversational_rag.build_manager import create_build

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
    snapshot = _snapshot("garden_river_stone_oak_cedar")
    create_build(session_root, snapshot)
    return snapshot.slug


def test_maybe_render_showcase_valid_slug_renders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A valid slug link renders the chat-only showcase (no page heading).
    monkeypatch.syspath_prepend(str(_APP_DIR))
    monkeypatch.setattr(route, "_SESSIONS_ROOT", tmp_path)
    slug = _seed_full_build(tmp_path)

    app = AppTest.from_function(_route_script)
    app.query_params["showcase"] = slug
    app.run(timeout=10)

    assert not app.exception
    assert app.session_state["_rendered"] is True
    assert app.chat_input  # the showcase chat (not the unavailable page) rendered
    assert not any("Converse with your knowledge" in sub.value for sub in app.subheader)
    # The build's frozen welcome prompt is injected from build.json (no prompt files).
    assert any("Frozen greeting" in md.value for md in app.markdown)


def test_showcase_inspect_and_token_opt_in_via_query_params(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Inspect + the Token usage panel are off by default on the showcase and turn
    # on only via ?inspect / ?showToken.
    from app_support.conversational_rag.conversational_rag_form_ui import ConversationalControls

    monkeypatch.syspath_prepend(str(_APP_DIR))
    monkeypatch.setattr(route, "_SESSIONS_ROOT", tmp_path)
    slug = _seed_full_build(tmp_path)

    import app_pages.conversational_rag as page_module

    captured: dict[str, object] = {}

    def _spy(
        _context: object,
        *,
        showcase_controls: ConversationalControls,
        show_token_panel: bool,
        showcase_prompts: object = None,
        showcase_slug: object = None,
    ) -> None:
        captured["inspect"] = showcase_controls.inspect
        captured["show_token_panel"] = show_token_panel
        captured["prompts"] = showcase_prompts

    monkeypatch.setattr(page_module, "render_page", _spy)

    opted_in = AppTest.from_function(_route_script)
    opted_in.query_params["showcase"] = slug
    opted_in.query_params["inspect"] = "1"
    opted_in.query_params["showToken"] = "1"
    opted_in.run(timeout=10)
    assert not opted_in.exception
    assert captured == {
        "inspect": True,
        "show_token_panel": True,
        "prompts": {"welcome": "Frozen greeting"},
    }

    captured.clear()
    default_off = AppTest.from_function(_route_script)
    default_off.query_params["showcase"] = slug
    default_off.run(timeout=10)
    assert not default_off.exception
    assert captured == {
        "inspect": False,
        "show_token_panel": False,
        "prompts": {"welcome": "Frozen greeting"},
    }
