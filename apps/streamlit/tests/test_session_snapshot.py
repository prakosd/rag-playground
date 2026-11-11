"""Tests for the per-session Step 5 ``snapshot.json`` store."""

from __future__ import annotations

import json
from pathlib import Path

from app_support.conversational_rag.conversational_rag_history import CONVERSATIONAL_RAG_DIRNAME
from app_support.conversational_rag.session_snapshot import (
    SESSION_SNAPSHOT_FILENAME,
    read_session_snapshot,
    remove_snapshot_prompt,
    session_snapshot_path,
    set_snapshot_prompt,
    snapshot_prompt,
    snapshot_prompts,
    write_session_snapshot,
)


def test_snapshot_path_is_under_conversational_rag_folder(tmp_path: Path) -> None:
    path = session_snapshot_path(tmp_path)

    assert path == tmp_path / CONVERSATIONAL_RAG_DIRNAME / SESSION_SNAPSHOT_FILENAME
    assert path.name == "snapshot.json"


def test_read_missing_returns_empty_dict(tmp_path: Path) -> None:
    assert read_session_snapshot(tmp_path) == {}


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    write_session_snapshot(tmp_path, {"top_k": 5, "tone": "neutral"})

    assert read_session_snapshot(tmp_path) == {"top_k": 5, "tone": "neutral"}


def test_read_malformed_json_returns_empty_dict(tmp_path: Path) -> None:
    directory = tmp_path / CONVERSATIONAL_RAG_DIRNAME
    directory.mkdir(parents=True)
    (directory / SESSION_SNAPSHOT_FILENAME).write_text("not json", encoding="utf-8")

    assert read_session_snapshot(tmp_path) == {}


def test_read_non_object_json_returns_empty_dict(tmp_path: Path) -> None:
    directory = tmp_path / CONVERSATIONAL_RAG_DIRNAME
    directory.mkdir(parents=True)
    (directory / SESSION_SNAPSHOT_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")

    assert read_session_snapshot(tmp_path) == {}


def test_set_prompt_creates_and_persists(tmp_path: Path) -> None:
    set_snapshot_prompt(tmp_path, "answer", "MY ANSWER PROMPT")

    assert snapshot_prompt(tmp_path, "answer") == "MY ANSWER PROMPT"
    stored = json.loads(session_snapshot_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["prompts"]["answer"] == "MY ANSWER PROMPT"


def test_snapshot_prompt_unset_or_blank_returns_none(tmp_path: Path) -> None:
    assert snapshot_prompt(tmp_path, "answer") is None

    set_snapshot_prompt(tmp_path, "answer", "   ")

    assert snapshot_prompt(tmp_path, "answer") is None


def test_set_prompt_preserves_other_snapshot_data(tmp_path: Path) -> None:
    write_session_snapshot(tmp_path, {"top_k": 7, "prompts": {"answer": "A"}})

    set_snapshot_prompt(tmp_path, "state", "STATE PROMPT")

    data = read_session_snapshot(tmp_path)
    assert data["top_k"] == 7
    assert data["prompts"] == {"answer": "A", "state": "STATE PROMPT"}


def test_remove_prompt_drops_key_and_keeps_rest(tmp_path: Path) -> None:
    write_session_snapshot(tmp_path, {"top_k": 7, "prompts": {"answer": "A", "state": "S"}})

    remove_snapshot_prompt(tmp_path, "answer")

    data = read_session_snapshot(tmp_path)
    assert data["top_k"] == 7
    assert data["prompts"] == {"state": "S"}
    assert snapshot_prompt(tmp_path, "answer") is None


def test_remove_prompt_absent_is_safe(tmp_path: Path) -> None:
    write_session_snapshot(tmp_path, {"top_k": 7})

    remove_snapshot_prompt(tmp_path, "answer")

    assert read_session_snapshot(tmp_path) == {"top_k": 7}


def test_snapshot_prompts_returns_edits_or_empty(tmp_path: Path) -> None:
    assert snapshot_prompts(tmp_path) == {}

    set_snapshot_prompt(tmp_path, "answer", "A")
    set_snapshot_prompt(tmp_path, "state", "S")

    assert snapshot_prompts(tmp_path) == {"answer": "A", "state": "S"}


def test_snapshot_prompts_returns_a_copy(tmp_path: Path) -> None:
    set_snapshot_prompt(tmp_path, "answer", "A")

    snapshot_prompts(tmp_path)["answer"] = "mutated"

    assert snapshot_prompt(tmp_path, "answer") == "A"
