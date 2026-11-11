"""Persist the live Step 5 (Conversational RAG) settings + prompts as ``snapshot.json``.

Mirrors a build's ``build.json``, but is rewritten each turn (and on every prompt
Save/Reset) so reloading a session — or importing an exported one into a fresh
session or browser — restores the last-used options and edited prompt templates,
not just the chat transcript (that lives in ``transactions.jsonl``). Stored inside
the session's ``conversational_rag/`` folder next to the transactions log.

Pure I/O over a plain JSON dict (no Streamlit, and no ``build_manager`` import), so
the prompt module can persist edits here without pulling UI/build weight. The UI
layer maps the dict to/from a :class:`BuildSnapshot` when it needs the typed shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from app_support.conversational_rag.conversational_rag_history import (
    conversational_rag_history_dir,
)

__all__ = [
    "SESSION_SNAPSHOT_FILENAME",
    "read_session_snapshot",
    "remove_snapshot_prompt",
    "session_snapshot_path",
    "set_snapshot_prompt",
    "snapshot_prompt",
    "snapshot_prompts",
    "write_session_snapshot",
]

SESSION_SNAPSHOT_FILENAME = "snapshot.json"
_PROMPTS_KEY = "prompts"


def session_snapshot_path(session_root: Path | str) -> Path:
    """Return the per-session ``conversational_rag/snapshot.json`` path."""
    return conversational_rag_history_dir(session_root) / SESSION_SNAPSHOT_FILENAME


def read_session_snapshot(session_root: Path | str) -> dict:
    """Return the parsed snapshot dict, or ``{}`` when absent, unreadable, or invalid."""
    try:
        text = session_snapshot_path(session_root).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_session_snapshot(session_root: Path | str, data: dict) -> None:
    """Write *data* as the session snapshot, creating the folder when needed."""
    directory = conversational_rag_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SESSION_SNAPSHOT_FILENAME).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def snapshot_prompt(session_root: Path | str, key: str) -> str | None:
    """Return the session's saved *key* prompt from the snapshot, or None when unset/blank."""
    prompts = read_session_snapshot(session_root).get(_PROMPTS_KEY)
    if not isinstance(prompts, dict):
        return None
    text = prompts.get(key)
    return text if isinstance(text, str) and text.strip() else None


def snapshot_prompts(session_root: Path | str) -> dict[str, str]:
    """Return a copy of the session's saved prompt edits (key → text), or ``{}`` when none."""
    prompts = read_session_snapshot(session_root).get(_PROMPTS_KEY)
    if not isinstance(prompts, dict):
        return {}
    return {str(key): str(value) for key, value in prompts.items()}


def set_snapshot_prompt(session_root: Path | str, key: str, template: str) -> None:
    """Persist *template* as the session's *key* prompt, preserving the rest of the snapshot."""
    data = read_session_snapshot(session_root)
    prompts = data.get(_PROMPTS_KEY)
    if not isinstance(prompts, dict):
        prompts = {}
    prompts[key] = template
    data[_PROMPTS_KEY] = prompts
    write_session_snapshot(session_root, data)


def remove_snapshot_prompt(session_root: Path | str, key: str) -> None:
    """Drop the session's saved *key* prompt (revert to default), preserving the rest."""
    data = read_session_snapshot(session_root)
    prompts = data.get(_PROMPTS_KEY)
    if isinstance(prompts, dict) and key in prompts:
        del prompts[key]
        data[_PROMPTS_KEY] = prompts
        write_session_snapshot(session_root, data)
