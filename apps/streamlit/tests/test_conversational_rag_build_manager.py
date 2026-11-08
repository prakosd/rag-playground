"""Tests for the pure Step 5 build snapshot/naming/slug helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app_support.conversational_rag import build_manager
from app_support.conversational_rag.build_manager import (
    BuildSnapshot,
    allocate_build_name,
    allocate_showcase_slug,
    build_run_dir,
    create_build,
    delete_build,
    is_build_name,
    list_builds,
    load_build,
    rename_build,
    resolve_slug,
)


def _snapshot(name: str = "rag_build_01_garden", **overrides: object) -> BuildSnapshot:
    base: dict[str, object] = {
        "schema_version": 1,
        "created_at_utc": "2026-10-30T07:48:40+00:00",
        "name": name,
        "slug": "garden_river_stone_oak_cedar",
        "language": "EN",
        "answer_model": "anthropic.claude",
        "top_k": 5,
        "tone": "Neutral",
        "reranker": "local",
        "aux_model_id": "aux.mini",
        "decomposition_limit": 3,
        "followup_show_count": 3,
        "followup_drop": 0.3,
        "followup_keep": 0.6,
        "followup_probe_k": 3,
        "answerability_chunks": 2,
        "state_summary_start_turn": 4,
        "state_summary_max_words": 150,
        "answer_recent_turns": 5,
        "plan_recent_turns": 2,
        "index_vector_folder": "vector_01_slate",
        "index_run_name": "2026-10-28_10-00-00",
        "embedding_model": "amazon.titan",
        "prompts": {"answer": "frozen answer prompt", "welcome": "hello"},
    }
    base.update(overrides)
    return BuildSnapshot(**base)  # type: ignore[arg-type]


def _write_build(session_root: Path, snapshot: BuildSnapshot) -> Path:
    folder = session_root / snapshot.name
    run_dir = folder / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "build.json").write_text(snapshot.to_json(), encoding="utf-8")
    return folder


def test_snapshot_json_round_trip() -> None:
    snapshot = _snapshot()
    assert BuildSnapshot.from_json(snapshot.to_json()) == snapshot


def test_from_json_returns_none_on_malformed() -> None:
    assert BuildSnapshot.from_json("not json") is None


def test_from_json_returns_none_when_fields_missing() -> None:
    assert BuildSnapshot.from_json(json.dumps({"name": "rag_build_01_x"})) is None


def test_allocate_build_name_uses_next_sequence_and_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "rag_build_01_garden").mkdir()
    (tmp_path / "rag_build_02_river").mkdir()
    monkeypatch.setattr(build_manager, "_generate_readable_crawl_suffix", lambda: "cedar")
    assert allocate_build_name(tmp_path) == "rag_build_03_cedar"


def test_allocate_build_name_starts_at_one_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_manager, "_generate_readable_crawl_suffix", lambda: "cedar")
    assert allocate_build_name(tmp_path) == "rag_build_01_cedar"


def test_is_build_name() -> None:
    assert is_build_name("rag_build_01_garden")
    assert not is_build_name("vector_01_slate")
    assert not is_build_name("rag_build_garden")  # no sequence number


def test_list_builds_newest_first_and_skips_invalid(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))
    _write_build(tmp_path, _snapshot(name="rag_build_02_river"))
    broken = tmp_path / "rag_build_03_broken"
    broken.mkdir()
    (broken / "build.json").write_text("nope", encoding="utf-8")
    names = [snapshot.name for snapshot in list_builds(tmp_path)]
    assert names == ["rag_build_02_river", "rag_build_01_garden"]


def test_newest_build_returns_most_recent(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))
    _write_build(tmp_path, _snapshot(name="rag_build_02_river"))
    newest = build_manager.newest_build(tmp_path)
    assert newest is not None
    assert newest.name == "rag_build_02_river"


def test_newest_build_none_when_empty(tmp_path: Path) -> None:
    assert build_manager.newest_build(tmp_path) is None


def test_build_config_signature_ignores_name_slug_and_timestamp() -> None:
    first = _snapshot(
        name="rag_build_01_garden",
        slug="a_b_c_d_e",
        created_at_utc="2026-01-01T00:00:00+00:00",
    )
    second = _snapshot(
        name="rag_build_09_river",
        slug="v_w_x_y_z",
        created_at_utc="2026-12-31T23:59:59+00:00",
    )
    assert build_manager.build_config_signature(first) == build_manager.build_config_signature(
        second
    )


def test_build_config_signature_differs_on_setting_change() -> None:
    assert build_manager.build_config_signature(
        _snapshot()
    ) != build_manager.build_config_signature(_snapshot(top_k=99))


def test_build_config_signature_differs_on_index_change() -> None:
    assert build_manager.build_config_signature(
        _snapshot()
    ) != build_manager.build_config_signature(_snapshot(index_vector_folder="vector_02_other"))


def test_build_config_signature_differs_on_prompt_change() -> None:
    assert build_manager.build_config_signature(
        _snapshot()
    ) != build_manager.build_config_signature(
        _snapshot(prompts={"answer": "DIFFERENT", "welcome": "hello"})
    )


def test_load_build_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_build(tmp_path / "nope") is None


def test_delete_build_removes_folder(tmp_path: Path) -> None:
    folder = _write_build(tmp_path, _snapshot())
    assert delete_build(tmp_path, "rag_build_01_garden") is True
    assert not folder.exists()


def test_delete_build_refuses_non_build_folder(tmp_path: Path) -> None:
    (tmp_path / "vector_01_slate").mkdir()
    assert delete_build(tmp_path, "vector_01_slate") is False
    assert (tmp_path / "vector_01_slate").is_dir()


def test_rename_build_renames_folder_and_syncs_manifest_name(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))

    new_name = rename_build(tmp_path, "rag_build_01_garden", "charter")

    assert new_name == "rag_build_01_charter"
    assert not (tmp_path / "rag_build_01_garden").exists()
    assert (tmp_path / "rag_build_01_charter").is_dir()
    # build.json's name field is rewritten so BuildSnapshot.name == folder name.
    snapshot = load_build(tmp_path / "rag_build_01_charter")
    assert snapshot is not None
    assert snapshot.name == "rag_build_01_charter"
    assert snapshot.slug == "garden_river_stone_oak_cedar"  # slug untouched


def test_rename_build_allows_dash_label(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))

    new_name = rename_build(tmp_path, "rag_build_01_garden", "charter-v2")

    assert new_name == "rag_build_01_charter-v2"
    assert (tmp_path / "rag_build_01_charter-v2").is_dir()
    snapshot = load_build(tmp_path / "rag_build_01_charter-v2")
    assert snapshot is not None
    assert snapshot.name == "rag_build_01_charter-v2"


def test_rename_build_noop_leaves_manifest_unchanged(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))

    assert rename_build(tmp_path, "rag_build_01_garden", "garden") == "rag_build_01_garden"
    snapshot = load_build(tmp_path / "rag_build_01_garden")
    assert snapshot is not None
    assert snapshot.name == "rag_build_01_garden"


def test_rename_build_rejects_invalid_label(tmp_path: Path) -> None:
    _write_build(tmp_path, _snapshot(name="rag_build_01_garden"))

    with pytest.raises(ValueError):
        rename_build(tmp_path, "rag_build_01_garden", "with space")
    assert (tmp_path / "rag_build_01_garden").is_dir()  # untouched


def test_allocate_showcase_slug_avoids_existing_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_build(tmp_path / "session_a", _snapshot(slug="alpha_beta_gamma_delta_epsilon"))
    slugs = iter(["alpha_beta_gamma_delta_epsilon", "one_two_three_four_five"])
    monkeypatch.setattr(build_manager, "generate_showcase_slug", lambda: next(slugs))
    # The first candidate collides with the existing build, so it retries.
    assert allocate_showcase_slug(tmp_path) == "one_two_three_four_five"


def test_resolve_slug_finds_owning_build(tmp_path: Path) -> None:
    session = tmp_path / "session_a"
    _write_build(session, _snapshot(slug="alpha_beta_gamma_delta_epsilon"))
    resolved = resolve_slug(tmp_path, "alpha_beta_gamma_delta_epsilon")
    assert resolved is not None
    assert resolved.name == "rag_build_01_garden"
    assert resolved.is_dir()


def test_resolve_slug_unknown_or_empty_is_none(tmp_path: Path) -> None:
    _write_build(tmp_path / "session_a", _snapshot(slug="alpha_beta_gamma_delta_epsilon"))
    assert resolve_slug(tmp_path, "nope_nope_nope_nope_nope") is None
    assert resolve_slug(tmp_path, "") is None


def test_create_build_writes_manifest_with_inline_prompts(tmp_path: Path) -> None:
    snapshot = _snapshot(prompts={"answer": "ANSWER PROMPT", "welcome": "Hi there"})
    target = create_build(tmp_path, snapshot)
    loaded = load_build(target)
    assert loaded is not None
    assert loaded == snapshot
    assert loaded.prompts == {"answer": "ANSWER PROMPT", "welcome": "Hi there"}
    run_dir = build_run_dir(target)
    assert run_dir is not None
    # The index is referenced, not copied: only build.json lives under the run dir.
    assert (run_dir / "build.json").is_file()
    assert not (run_dir / "vector_01_slate").exists()


def test_builds_referencing_folder_lists_only_matching_builds(tmp_path: Path) -> None:
    create_build(
        tmp_path, _snapshot(name="rag_build_01_garden", index_vector_folder="vector_01_slate")
    )
    create_build(
        tmp_path, _snapshot(name="rag_build_02_river", index_vector_folder="vector_02_other")
    )
    names = [s.name for s in build_manager.builds_referencing_folder(tmp_path, "vector_01_slate")]
    assert names == ["rag_build_01_garden"]


def test_builds_referencing_folder_empty_when_none_match(tmp_path: Path) -> None:
    create_build(tmp_path, _snapshot(index_vector_folder="vector_01_slate"))
    assert build_manager.builds_referencing_folder(tmp_path, "vector_99_none") == []


def test_build_run_dir_none_without_timestamp_child(tmp_path: Path) -> None:
    (tmp_path / "rag_build_01_garden").mkdir()
    assert build_run_dir(tmp_path / "rag_build_01_garden") is None
    assert build_run_dir(tmp_path / "missing") is None
