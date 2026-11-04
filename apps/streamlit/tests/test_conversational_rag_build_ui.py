"""Tests for the Step 5 build-management UI's pure mapping/build helpers."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest
from vector_indexer import IndexManifest
from vector_indexer.manifest import write_manifest

import app_support.conversational_rag.conversational_rag_build_ui as build_ui
from app_support.conversational_rag.build_manager import (
    BuildSnapshot,
    build_run_dir,
    create_build,
    list_builds,
)
from app_support.conversational_rag.conversational_prompts import (
    CONVERSATIONAL_PROMPT_KEYS,
    WELCOME_PROMPT_KEY,
    load_saved_conversational_prompt,
    save_conversational_prompt,
)
from app_support.conversational_rag.conversational_rag_build_ui import (
    control_widget_values,
    frozen_prompt_texts,
    load_build_as_controls,
    snapshot_from_controls,
)
from app_support.conversational_rag.conversational_rag_form_ui import ConversationalControls
from app_support.i18n import STRINGS_EN
from app_support.rag_shared.index_catalog import IndexRef, list_session_indexes

_APP_MESSAGE_KEYS = {"welcome", "error_reply", "followup_intro", "no_followups"}


def _manifest() -> IndexManifest:
    return IndexManifest(
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


def _controls(**overrides: object) -> ConversationalControls:
    values: dict[str, object] = {
        "index": IndexRef(
            run_dir=Path("/tmp/idx"),
            vector_folder="vector_01_slate",
            run_name="2026-10-28_10-00-00",
            manifest=_manifest(),
        ),
        "answer_model": "gpt-4o",
        "top_k": 6,
        "tone": "Formal",
        "reranker": "llm",
        "aux_model_id": "echo",
        "decomposition_limit": 3,
        "followup_show_count": 4,
        "inspect": True,
        "followup_drop": 0.3,
        "followup_keep": 0.7,
        "followup_probe_k": 3,
        "answerability_chunks": 2,
        "state_summary_start_turn": 4,
        "state_summary_max_words": 150,
        "answer_recent_turns": 5,
        "plan_recent_turns": 2,
    }
    values.update(overrides)
    return ConversationalControls(**values)  # type: ignore[arg-type]


def _real_index(root: Path) -> IndexRef:
    run_dir = root / "vector_01_slate" / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "chroma").mkdir()
    write_manifest(
        run_dir,
        {
            "success": True,
            "indexed_chunk_count": 5,
            "embedding_model_used": "titan",
            "collection_name": "c",
        },
    )
    return IndexRef(
        run_dir=run_dir,
        vector_folder="vector_01_slate",
        run_name="2026-10-28_10-00-00",
        manifest=_manifest(),
    )


def test_snapshot_from_controls_maps_fields() -> None:
    snapshot = snapshot_from_controls(
        _controls(), language="EN", name="rag_build_01_garden", slug="a_b_c_d_e", prompts={}
    )
    assert snapshot.name == "rag_build_01_garden"
    assert snapshot.slug == "a_b_c_d_e"
    assert snapshot.language == "EN"
    assert snapshot.answer_model == "gpt-4o"
    assert snapshot.top_k == 6
    assert snapshot.reranker == "llm"
    assert snapshot.decomposition_limit == 3
    assert snapshot.index_vector_folder == "vector_01_slate"
    assert snapshot.index_run_name == "2026-10-28_10-00-00"
    assert snapshot.embedding_model == "titan"
    assert snapshot.created_at_utc  # an ISO timestamp was recorded


def test_snapshot_round_trips_through_json() -> None:
    snapshot = snapshot_from_controls(
        _controls(), language="ID", name="rag_build_02_river", slug="a_b_c_d_e", prompts={}
    )
    assert BuildSnapshot.from_json(snapshot.to_json()) == snapshot


def test_frozen_prompt_texts_covers_all_ten_prompts(tmp_path: Path) -> None:
    texts = frozen_prompt_texts(STRINGS_EN, tmp_path)
    assert set(texts) == set(CONVERSATIONAL_PROMPT_KEYS) | _APP_MESSAGE_KEYS
    assert all(text.strip() for text in texts.values())


def test_frozen_prompt_texts_prefers_saved_edit(tmp_path: Path) -> None:
    save_conversational_prompt(tmp_path, WELCOME_PROMPT_KEY, "Custom welcome")
    texts = frozen_prompt_texts(STRINGS_EN, tmp_path)
    assert texts[WELCOME_PROMPT_KEY] == "Custom welcome"


def test_build_now_creates_build_referencing_index(tmp_path: Path) -> None:
    controls = _controls(index=_real_index(tmp_path / "src"))
    name = build_ui._build_now(STRINGS_EN, controls, tmp_path, "EN")
    assert name.startswith("rag_build_01_")
    builds = list_builds(tmp_path)
    assert [snapshot.name for snapshot in builds] == [name]
    assert builds[0].index_vector_folder == "vector_01_slate"
    run_dir = build_run_dir(tmp_path / name)
    assert run_dir is not None
    # The index is referenced, not copied into the build.
    assert list_session_indexes(run_dir) == []


def _launch_button_script(session_dir: str, build_name: str, change_top_k: bool) -> None:
    # Self-contained for AppTest.from_function (isolated namespace).
    from dataclasses import replace
    from pathlib import Path as _Path

    from app_support.conversational_rag.conversational_rag_build_ui import (
        load_build_as_controls,
        render_build_launch_button,
    )
    from app_support.i18n import STRINGS_EN as _STRINGS_EN

    session_root = _Path(session_dir)
    controls = load_build_as_controls(session_root / build_name)
    assert controls is not None
    if change_top_k:
        controls = replace(controls, top_k=controls.top_k + 1)
    render_build_launch_button(_STRINGS_EN, controls, session_root, "EN")


def test_launch_button_shows_relaunch_when_config_matches_latest_build(tmp_path: Path) -> None:
    controls = _controls(index=_real_index(tmp_path))
    name = build_ui._build_now(STRINGS_EN, controls, tmp_path, "EN")
    at = AppTest.from_function(
        _launch_button_script,
        kwargs={"session_dir": str(tmp_path), "build_name": name, "change_top_k": False},
    ).run()
    assert not at.exception
    assert at.button[0].label == STRINGS_EN["CONV_BUILD_RELAUNCH_BUTTON"]


def test_launch_button_reverts_to_build_when_config_changes(tmp_path: Path) -> None:
    controls = _controls(index=_real_index(tmp_path))
    name = build_ui._build_now(STRINGS_EN, controls, tmp_path, "EN")
    at = AppTest.from_function(
        _launch_button_script,
        kwargs={"session_dir": str(tmp_path), "build_name": name, "change_top_k": True},
    ).run()
    assert not at.exception
    assert at.button[0].label == STRINGS_EN["CONV_BUILD_LAUNCH_BUTTON"]


def _apply_load_script(session_dir: str, build_name: str) -> None:
    # Self-contained for AppTest.from_function (isolated namespace).
    from pathlib import Path as _Path

    import streamlit as st

    from app_support.conversational_rag.conversational_rag_build_ui import apply_pending_load
    from app_support.i18n import STRINGS_EN as _STRINGS_EN

    st.session_state["conversational_rag_apply_load"] = build_name
    apply_pending_load(_STRINGS_EN, _Path(session_dir))


def test_control_widget_values_maps_snapshot() -> None:
    snapshot = snapshot_from_controls(
        _controls(top_k=9, answer_model="x-model", inspect=True),
        language="EN",
        name="rag_build_01_garden",
        slug="a_b_c_d_e",
        prompts={},
    )
    values = control_widget_values(snapshot)
    assert values["conversational_rag_top_k"] == 9
    assert values["conversational_rag_llm_model"] == "x-model"
    assert values["conversational_rag_reranker"] == snapshot.reranker
    assert values["conversational_rag_thresholds"] == (
        snapshot.followup_drop,
        snapshot.followup_keep,
    )


def test_matching_index_finds_live_index(tmp_path: Path) -> None:
    _real_index(tmp_path)
    snapshot = snapshot_from_controls(
        _controls(), language="EN", name="rag_build_01_garden", slug="a_b_c_d_e", prompts={}
    )
    ref = build_ui._matching_index(tmp_path, snapshot)
    assert ref is not None
    assert ref.vector_folder == "vector_01_slate"


def test_matching_index_none_when_absent(tmp_path: Path) -> None:
    snapshot = snapshot_from_controls(
        _controls(), language="EN", name="rag_build_01_garden", slug="a_b_c_d_e", prompts={}
    )
    assert build_ui._matching_index(tmp_path, snapshot) is None


def test_apply_pending_load_restores_settings_and_prompts(tmp_path: Path) -> None:
    source = _real_index(tmp_path / "src")
    snapshot = snapshot_from_controls(
        _controls(index=source, top_k=9, answer_model="x-model"),
        language="EN",
        name="rag_build_01_garden",
        slug="a_b_c_d_e",
        prompts={"answer": "FROZEN ANSWER"},
    )
    create_build(tmp_path, snapshot)

    at = AppTest.from_function(
        _apply_load_script,
        kwargs={"session_dir": str(tmp_path), "build_name": "rag_build_01_garden"},
    ).run()

    assert not at.exception
    assert at.session_state["conversational_rag_top_k"] == 9
    assert at.session_state["conversational_rag_llm_model"] == "x-model"
    assert at.session_state["conversational_rag_prompt_answer"] == "FROZEN ANSWER"
    assert load_saved_conversational_prompt(tmp_path, "answer") == "FROZEN ANSWER"


def test_load_build_as_controls_reconstructs(tmp_path: Path) -> None:
    source = _real_index(tmp_path)
    snapshot = snapshot_from_controls(
        _controls(index=source, top_k=7),
        language="EN",
        name="rag_build_01_garden",
        slug="a_b_c_d_e",
        prompts={},
    )
    create_build(tmp_path, snapshot)
    controls = load_build_as_controls(tmp_path / "rag_build_01_garden")
    assert controls is not None
    assert controls.top_k == 7
    assert controls.index is not None
    assert controls.index.vector_folder == "vector_01_slate"


def test_load_build_as_controls_none_when_missing(tmp_path: Path) -> None:
    assert load_build_as_controls(tmp_path / "nope") is None


def test_resolve_build_index_falls_back_to_copied_index(tmp_path: Path) -> None:
    # Older self-contained build: the index is copied under the build's run dir and the
    # owner session has no matching index, so resolution uses the copied one.
    build_root = tmp_path / "rag_build_01_garden"
    run_dir = build_root / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    copied = _real_index(run_dir)
    snapshot = snapshot_from_controls(
        _controls(index=copied),
        language="EN",
        name="rag_build_01_garden",
        slug="a_b_c_d_e",
        prompts={},
    )
    (run_dir / "build.json").write_text(snapshot.to_json(), encoding="utf-8")

    ref = build_ui.resolve_build_index(build_root, snapshot)
    assert ref is not None
    assert ref.run_dir == copied.run_dir


def _build_actions_script(session_dir: str, name: str) -> None:
    from pathlib import Path as _Path

    from app_support.conversational_rag.conversational_rag_build_ui import render_build_tree_actions
    from app_support.i18n import STRINGS_EN as _STRINGS_EN

    render_build_tree_actions(_STRINGS_EN, _Path(session_dir), name)


def test_render_build_tree_actions_renders_action_row(tmp_path: Path) -> None:
    source = _real_index(tmp_path / "src")
    snapshot = snapshot_from_controls(
        _controls(index=source),
        language="EN",
        name="rag_build_01_garden",
        slug="alpha_beta_gamma_delta_epsilon",
        prompts={},
    )
    create_build(tmp_path, snapshot)

    at = AppTest.from_function(
        _build_actions_script,
        kwargs={"session_dir": str(tmp_path), "name": "rag_build_01_garden"},
    ).run()

    assert not at.exception
    # The redundant slug caption was removed (the tree already lists build.json).
    assert not any("alpha_beta_gamma_delta_epsilon" in caption.value for caption in at.caption)
    labels = [button.label for button in at.button]
    assert any("Export" in label for label in labels)
    assert any("Delete this build" in label for label in labels)
