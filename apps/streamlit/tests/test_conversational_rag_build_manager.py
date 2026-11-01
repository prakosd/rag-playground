"""Tests for the pure Step 5 build snapshot/naming/token helpers."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from vector_indexer.manifest import write_manifest

from app_support.conversational_rag import build_manager
from app_support.conversational_rag.build_manager import (
    BuildSnapshot,
    allocate_build_name,
    create_build,
    delete_build,
    format_built_at,
    is_build_name,
    list_builds,
    load_build,
    make_showcase_token,
    parse_showcase_token,
)
from app_support.rag_shared.index_catalog import list_session_indexes


def _snapshot(name: str = "rag_build_01_garden", **overrides: object) -> BuildSnapshot:
    base: dict[str, object] = {
        "schema_version": 1,
        "created_at_utc": "2026-10-30T07:48:40+00:00",
        "name": name,
        "language": "EN",
        "answer_model": "anthropic.claude",
        "top_k": 5,
        "tone": "Neutral",
        "reranker": "local",
        "aux_model_id": "aux.mini",
        "decomposition_limit": 3,
        "followup_show_count": 3,
        "inspect": False,
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
    }
    base.update(overrides)
    return BuildSnapshot(**base)  # type: ignore[arg-type]


def _write_build(session_root: Path, snapshot: BuildSnapshot) -> Path:
    folder = session_root / snapshot.name
    folder.mkdir(parents=True)
    (folder / "build.json").write_text(snapshot.to_json(), encoding="utf-8")
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


def test_showcase_token_round_trip() -> None:
    token = make_showcase_token("winter_apple", "rag_build_01_garden", "secret")
    assert parse_showcase_token(token, "secret") == ("winter_apple", "rag_build_01_garden")


def test_showcase_token_rejects_wrong_secret() -> None:
    token = make_showcase_token("winter_apple", "rag_build_01_garden", "secret")
    assert parse_showcase_token(token, "other") is None


def test_showcase_token_rejects_tampered_payload() -> None:
    token = make_showcase_token("winter_apple", "rag_build_01_garden", "secret")
    _, _, signature = token.partition(".")
    forged = base64.urlsafe_b64encode(b"other:rag_build_01_garden").decode().rstrip("=")
    assert parse_showcase_token(f"{forged}.{signature}", "secret") is None


def test_showcase_token_rejects_malformed() -> None:
    assert parse_showcase_token("garbage", "secret") is None
    assert parse_showcase_token("", "secret") is None


def test_format_built_at_renders_human_readable_utc() -> None:
    assert format_built_at("2026-10-30T07:48:40+00:00") == "30 October 2026 07:48 UTC"


def test_format_built_at_passes_through_unparseable() -> None:
    assert format_built_at("not-a-date") == "not-a-date"


def _make_source_index(root: Path) -> Path:
    run_dir = root / "vector_01_slate" / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "chroma").mkdir()
    write_manifest(
        run_dir,
        {
            "success": True,
            "indexed_chunk_count": 5,
            "embedding_model_used": "amazon.titan",
            "collection_name": "crawl4md_documents",
        },
    )
    return run_dir


def test_create_build_writes_manifest_index_and_prompts(tmp_path: Path) -> None:
    source_index = _make_source_index(tmp_path / "src")
    snapshot = _snapshot()
    target = create_build(
        tmp_path,
        snapshot,
        source_index,
        {"answer": "ANSWER PROMPT", "welcome": "Hi there"},
    )
    assert load_build(target) == snapshot
    copied = target / "vector_01_slate" / "2026-10-28_10-00-00"
    assert (copied / "chroma").is_dir()
    assert (copied / "manifest.json").is_file()
    prompt_dir = target / "conversational_rag_history"
    assert (prompt_dir / "prompt_answer.txt").read_text(encoding="utf-8") == "ANSWER PROMPT"
    assert (prompt_dir / "prompt_welcome.txt").read_text(encoding="utf-8") == "Hi there"


def test_create_build_index_is_discoverable(tmp_path: Path) -> None:
    source_index = _make_source_index(tmp_path / "src")
    target = create_build(tmp_path, _snapshot(), source_index, {})
    refs = list_session_indexes(target)
    assert [ref.run_name for ref in refs] == ["2026-10-28_10-00-00"]
    assert refs[0].vector_folder == "vector_01_slate"
