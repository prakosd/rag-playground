"""Tests for the Step 5 editable-prompt resolver (config / session / library)."""

from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.prompts import QA_SYSTEM_PROMPT, STATE_UPDATE_TEMPLATE

from app_support.conversational_rag import conversational_prompts as cp
from app_support.conversational_rag.conversational_prompts import (
    APP_MESSAGE_PROMPT_KEYS,
    CONVERSATIONAL_PROMPT_KEYS,
    ERROR_REPLY_PROMPT_KEY,
    FOLLOWUP_INTRO_PROMPT_KEY,
    NO_FOLLOWUPS_PROMPT_KEY,
    WELCOME_PROMPT_KEY,
    conversational_prompt_is_valid,
    editor_prompt_text,
    load_saved_conversational_prompt,
    pick_random_line,
    reset_conversational_prompt,
    resolve_app_message,
    resolve_conversational_prompt,
    resolve_conversational_prompts,
    resolve_welcome_message,
    save_conversational_prompt,
)


def _point_config_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aim the resolver's config dir at a temp folder and return it (created)."""
    monkeypatch.setattr(cp, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cp._settings, "conv_rag_prompt_template_dir", "cfg")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    return cfg


def test_editor_prompt_text_keeps_edit_but_heals_blank() -> None:
    # A real edit is kept verbatim; a blank/missing value self-heals to the
    # effective prompt so the editor never shows empty.
    default = resolve_conversational_prompt("answer")
    assert editor_prompt_text(None, "answer") == default
    assert editor_prompt_text("   ", "answer") == default
    kept = "my custom {tone} {context} {language}"
    assert editor_prompt_text(kept, "answer") == kept


def test_resolve_welcome_message_prefers_saved_then_default(tmp_path: Path) -> None:
    # No session or nothing saved → the caller's localized default; a saved edit wins.
    assert resolve_welcome_message(None, "hello") == "hello"
    assert resolve_welcome_message(tmp_path, "hello") == "hello"
    save_conversational_prompt(tmp_path, WELCOME_PROMPT_KEY, "Custom greeting")
    assert resolve_welcome_message(tmp_path, "hello") == "Custom greeting"


def test_resolve_app_message_prefers_saved_then_default(tmp_path: Path) -> None:
    # Mirrors the welcome greeting: no session / nothing saved → the localized
    # default; a saved edit wins; a save for one key doesn't affect another.
    assert resolve_app_message(None, FOLLOWUP_INTRO_PROMPT_KEY, "d") == "d"
    assert resolve_app_message(tmp_path, NO_FOLLOWUPS_PROMPT_KEY, "d") == "d"
    save_conversational_prompt(tmp_path, FOLLOWUP_INTRO_PROMPT_KEY, "Custom intro")
    assert resolve_app_message(tmp_path, FOLLOWUP_INTRO_PROMPT_KEY, "d") == "Custom intro"
    assert resolve_app_message(tmp_path, NO_FOLLOWUPS_PROMPT_KEY, "d") == "d"


def test_error_reply_is_an_editable_app_message(tmp_path: Path) -> None:
    # The failed-turn reply follows the welcome / no-suggestions pattern: an app-only
    # message (no placeholders) that a session can override.
    assert ERROR_REPLY_PROMPT_KEY in APP_MESSAGE_PROMPT_KEYS
    assert resolve_app_message(tmp_path, ERROR_REPLY_PROMPT_KEY, "d") == "d"
    save_conversational_prompt(tmp_path, ERROR_REPLY_PROMPT_KEY, "So sorry, try later.")
    assert resolve_app_message(tmp_path, ERROR_REPLY_PROMPT_KEY, "d") == "So sorry, try later."


def test_pick_random_line_is_stable_per_seed_and_varies() -> None:
    # App messages hold one alternate per line; a seed picks one deterministically.
    text = "one\ntwo\nthree"
    first = pick_random_line(text, 0)
    assert first in {"one", "two", "three"}
    assert pick_random_line(text, 0) == first  # stable across reruns (same seed)
    assert pick_random_line("  \n  ", 5) == ""  # blank degrades to empty
    assert pick_random_line("only line", 9) == "only line"
    seen = {pick_random_line(text, seed) for seed in range(20)}
    assert len(seen) > 1  # rotates across turns


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
