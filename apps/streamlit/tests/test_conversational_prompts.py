"""Tests for the Step 5 editable-prompt resolver (config / session / library)."""

from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.prompts import QA_SYSTEM_PROMPT, STATE_UPDATE_TEMPLATE

from app_support.conversational_rag import conversational_prompts as cp
from app_support.conversational_rag.conversational_prompts import (
    CONVERSATIONAL_PROMPT_KEYS,
    conversational_prompt_is_valid,
    load_saved_conversational_prompt,
    reset_conversational_prompt,
    resolve_conversational_prompt,
    resolve_conversational_prompts,
    save_conversational_prompt,
)


def _point_config_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aim the resolver's config dir at a temp folder and return it (created)."""
    monkeypatch.setattr(cp, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cp._settings, "conv_rag_prompt_template_dir", "cfg")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    return cfg


def test_resolve_returns_config_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _point_config_at(tmp_path, monkeypatch)
    (cfg / "conversational_answer_prompt.txt").write_text("CUSTOM {tone} {context}", "utf-8")

    assert resolve_conversational_prompt("answer") == "CUSTOM {tone} {context}"


def test_resolve_falls_back_to_library_default_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_config_at(tmp_path, monkeypatch)  # no files written

    assert resolve_conversational_prompt("answer") == QA_SYSTEM_PROMPT


def test_resolve_falls_back_when_config_file_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _point_config_at(tmp_path, monkeypatch)
    (cfg / "conversational_state_prompt.txt").write_text("   \n", "utf-8")

    assert resolve_conversational_prompt("state") == STATE_UPDATE_TEMPLATE


def test_resolve_prefers_session_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _point_config_at(tmp_path, monkeypatch)
    (cfg / "conversational_rerank_prompt.txt").write_text("config {query} {passages}", "utf-8")
    save_conversational_prompt(tmp_path, "rerank", "session {query} {passages}")

    assert resolve_conversational_prompt("rerank", tmp_path).startswith("session ")


def test_save_load_reset_round_trip(tmp_path: Path) -> None:
    assert load_saved_conversational_prompt(tmp_path, "followups") is None

    save_conversational_prompt(tmp_path, "followups", "hi {topics} {questions} {count}")
    assert (
        load_saved_conversational_prompt(tmp_path, "followups") == "hi {topics} {questions} {count}"
    )

    reset_conversational_prompt(tmp_path, "followups")
    assert load_saved_conversational_prompt(tmp_path, "followups") is None


def test_conversational_prompt_is_valid_accepts_and_rejects() -> None:
    assert conversational_prompt_is_valid("answer", "sys {tone} {context}") is True
    assert conversational_prompt_is_valid("answer", "sys {tone} {oops}") is False
    assert conversational_prompt_is_valid("rerank", "{query} {passages}") is True
    assert conversational_prompt_is_valid("rerank", "stray { brace") is False


def test_resolve_conversational_prompts_builds_full_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_config_at(tmp_path, monkeypatch)  # no files -> library defaults
    bundle = resolve_conversational_prompts()

    for key in CONVERSATIONAL_PROMPT_KEYS:
        assert getattr(bundle, key)  # every field resolved to a non-empty template


def test_shipped_default_prompt_files_are_valid() -> None:
    # Each shipped config .txt must keep the placeholders its prompt fills.
    for key in CONVERSATIONAL_PROMPT_KEYS:
        assert conversational_prompt_is_valid(key, resolve_conversational_prompt(key))
