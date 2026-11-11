"""Resolve, validate, and persist the editable Step 5 prompt templates.

The six conversational prompts (answer, decompose, rerank, followups,
answerability, state) each resolve with the same precedence as Step 4's single
template: a per-session saved edit (stored in ``conversational_rag/snapshot.json``)
→ the shipped config ``.txt`` (so an operator can reword a default without a code
change) → the built-in ``rag_engine`` constant. A missing/empty source falls through
to the next, so a cleared edit never breaks a turn. Pure I/O + resolution (no
Streamlit), so it stays unit-testable and the page module stays thin.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from pathlib import Path

from rag_engine import CONVERSATIONAL_PROMPT_FIELDS, ConversationalPrompts, template_has_fields
from rag_engine.prompts import (
    ANSWERABILITY_TEMPLATE,
    PLAN_QUERIES_TEMPLATE,
    QA_SYSTEM_PROMPT,
    RERANK_TEMPLATE,
    STATE_UPDATE_TEMPLATE,
    SUGGEST_FOLLOWUPS_TEMPLATE,
)

from app_support.conversational_rag.session_snapshot import (
    remove_snapshot_prompt,
    set_snapshot_prompt,
    snapshot_prompt,
)
from app_support.settings import get_settings

__all__ = [
    "APP_MESSAGE_PROMPT_KEYS",
    "CONVERSATIONAL_PROMPT_KEYS",
    "ERROR_REPLY_PROMPT_KEY",
    "FOLLOWUP_INTRO_PROMPT_KEY",
    "NO_FOLLOWUPS_PROMPT_KEY",
    "WELCOME_PROMPT_KEY",
    "conversational_prompt_is_valid",
    "editor_prompt_text",
    "load_saved_conversational_prompt",
    "pick_random_line",
    "reset_conversational_prompt",
    "resolve_app_message",
    "resolve_conversational_prompt",
    "resolve_conversational_prompts",
    "resolve_welcome_message",
    "save_conversational_prompt",
]

_settings = get_settings()

# UI tab order and iteration order for the resolved bundle.
CONVERSATIONAL_PROMPT_KEYS: tuple[str, ...] = (
    "answer",
    "decompose",
    "rerank",
    "followups",
    "answerability",
    "state",
)

# App-only display messages (no placeholders / library default), so they live
# outside CONVERSATIONAL_PROMPT_KEYS: the fresh-conversation greeting, the natural
# reply shown when a turn fails, the intro above suggested follow-ups, and the nudge
# shown when a turn has none. Each holds one alternate per non-empty line; the UI
# shows a random line (see pick_random_line).
WELCOME_PROMPT_KEY = "welcome"
ERROR_REPLY_PROMPT_KEY = "error_reply"
FOLLOWUP_INTRO_PROMPT_KEY = "followup_intro"
NO_FOLLOWUPS_PROMPT_KEY = "no_followups"
APP_MESSAGE_PROMPT_KEYS: tuple[str, ...] = (
    WELCOME_PROMPT_KEY,
    ERROR_REPLY_PROMPT_KEY,
    FOLLOWUP_INTRO_PROMPT_KEY,
    NO_FOLLOWUPS_PROMPT_KEY,
)

_PROMPT_FILENAMES = {
    "answer": "conversational_answer_prompt.txt",
    "decompose": "conversational_decompose_prompt.txt",
    "rerank": "conversational_rerank_prompt.txt",
    "followups": "conversational_followups_prompt.txt",
    "answerability": "conversational_answerability_prompt.txt",
    "state": "conversational_state_prompt.txt",
}

_LIBRARY_DEFAULTS = {
    "answer": QA_SYSTEM_PROMPT,
    "decompose": PLAN_QUERIES_TEMPLATE,
    "rerank": RERANK_TEMPLATE,
    "followups": SUGGEST_FOLLOWUPS_TEMPLATE,
    "answerability": ANSWERABILITY_TEMPLATE,
    "state": STATE_UPDATE_TEMPLATE,
}

# This module lives at apps/streamlit/src/app_support/conversational_rag/; the repo
# root is five parents up and the config dir resolves against it.
_REPO_ROOT = Path(__file__).resolve().parents[5]


def conversational_prompt_is_valid(key: str, template: str) -> bool:
    """Return True when *template* keeps the placeholders the *key* prompt fills."""
    return template_has_fields(template, CONVERSATIONAL_PROMPT_FIELDS[key])


def _config_path(key: str) -> Path:
    return _REPO_ROOT / _settings.conv_rag_prompt_template_dir / _PROMPT_FILENAMES[key]


def load_saved_conversational_prompt(session_root: Path | str, key: str) -> str | None:
    """Return the session's saved *key* prompt (from ``snapshot.json``), or None when unset."""
    return snapshot_prompt(session_root, key)


def save_conversational_prompt(session_root: Path | str, key: str, template: str) -> None:
    """Persist *template* as this session's *key* prompt in ``snapshot.json``."""
    set_snapshot_prompt(session_root, key, template)


def reset_conversational_prompt(session_root: Path | str, key: str) -> None:
    """Remove the session's saved *key* prompt, reverting to the default."""
    remove_snapshot_prompt(session_root, key)


def resolve_conversational_prompt(
    key: str,
    session_root: Path | str | None = None,
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Return the effective *key* prompt: override → session edit → config → library default.

    *overrides* (a build's frozen prompts on the showcase) wins over everything so a
    launched build reproduces its exact behavior without writing prompt files.
    """
    if overrides is not None:
        override = overrides.get(key)
        if override and override.strip():
            return override
    if session_root is not None:
        saved = load_saved_conversational_prompt(session_root, key)
        if saved is not None:
            return saved
    try:
        text = _config_path(key).read_text(encoding="utf-8")
    except OSError:
        return _LIBRARY_DEFAULTS[key]
    return text if text.strip() else _LIBRARY_DEFAULTS[key]


def editor_prompt_text(
    current: str | None, key: str, session_root: Path | str | None = None
) -> str:
    """Return the editor text for *key*: a real edit is kept, a blank one self-heals.

    The prompt editor seeds its text area from session state; should a blank value
    ever persist there, the editor would show empty. Falling back to the resolved
    prompt whenever *current* is blank keeps the editor from ever emptying.
    """
    if current and current.strip():
        return current
    return resolve_conversational_prompt(key, session_root)


def resolve_conversational_prompts(
    session_root: Path | str | None = None,
    overrides: Mapping[str, str] | None = None,
) -> ConversationalPrompts:
    """Resolve all six prompts into a bundle for ``conversational_answer``."""
    return ConversationalPrompts(
        **{
            key: resolve_conversational_prompt(key, session_root, overrides)
            for key in CONVERSATIONAL_PROMPT_KEYS
        }
    )


def resolve_app_message(
    session_root: Path | str | None,
    key: str,
    default: str,
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Return the session's saved app-only message for *key*, or *default*.

    App-only display text (welcome greeting, follow-up intro, no-suggestions nudge)
    resolves from a frozen-build *override*, then the session's saved edit, falling
    back to the caller-supplied localized *default* (keeping this module UI-agnostic).
    A blank saved file falls through to *default*.
    """
    if overrides is not None:
        override = overrides.get(key)
        if override and override.strip():
            return override
    if session_root is not None:
        saved = load_saved_conversational_prompt(session_root, key)
        if saved is not None:
            return saved
    return default


def resolve_welcome_message(
    session_root: Path | str | None, default: str, overrides: Mapping[str, str] | None = None
) -> str:
    """Return the session's saved welcome greeting, or the localized *default*."""
    return resolve_app_message(session_root, WELCOME_PROMPT_KEY, default, overrides)


def pick_random_line(text: str, seed: object) -> str:
    """Return one non-empty line of *text*, chosen deterministically by *seed*.

    App-only messages hold one alternate per line; the same *seed* (a turn id or
    conversation id) yields the same choice across reruns but varies between turns,
    so the wording rotates without flickering mid-turn.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return (text or "").strip()
    return lines[zlib.crc32(str(seed).encode("utf-8")) % len(lines)]
