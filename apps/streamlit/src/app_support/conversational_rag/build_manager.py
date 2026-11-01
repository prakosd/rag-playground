"""Create, name, list, and sign Step 5 (Conversational RAG) build snapshots.

A "build" freezes the current Step 5 settings into a self-contained folder at the
session root (``rag_build_<NN>_<word>``, mirroring ``crawl_``/``vector_``) so it can
be launched as a read-only showcase, exported, or reloaded. This module owns the
build naming, the :class:`BuildSnapshot` on-disk model (``build.json``), discovery
and deletion, and the HMAC-signed showcase-link token. It is pure (no Streamlit) so
it stays unit-testable; the UI adapter maps it to/from the live controls.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from artifact_store.naming import (
    RAG_BUILD_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    parse_folder_sequence,
    sequence_sort_key,
)
from artifact_store.paths import ensure_within_root

from app_support.conversational_rag.conversational_prompts import save_conversational_prompt
from app_support.generated_files import delete_generated_folder
from app_support.session_manager import _generate_readable_crawl_suffix

__all__ = [
    "BUILD_MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "BuildSnapshot",
    "allocate_build_name",
    "build_dir",
    "create_build",
    "delete_build",
    "format_built_at",
    "is_build_name",
    "list_builds",
    "load_build",
    "make_showcase_token",
    "parse_showcase_token",
]

BUILD_MANIFEST_FILENAME = "build.json"
SCHEMA_VERSION = 1

# "30 October 2026 07:48 UTC" — the caption shown on each build row.
_BUILT_AT_FORMAT = "%d %B %Y %H:%M UTC"
# Signed showcase token = urlsafe-b64("<session>:<build>") + "." + HMAC-SHA256 hex.
_PAYLOAD_SEPARATOR = ":"
_TOKEN_SEPARATOR = "."
# Domain-separates the showcase HMAC from other uses of the shared signing secret.
_HMAC_DOMAIN = b"rag-playground.showcase.v1:"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class BuildSnapshot:
    """The frozen Step 5 settings + index reference persisted as ``build.json``."""

    schema_version: int
    created_at_utc: str
    name: str
    language: str
    answer_model: str
    top_k: int
    tone: str
    reranker: str
    aux_model_id: str
    decomposition_limit: int
    followup_show_count: int
    inspect: bool
    followup_drop: float
    followup_keep: float
    followup_probe_k: int
    answerability_chunks: int
    state_summary_start_turn: int
    state_summary_max_words: int
    answer_recent_turns: int
    plan_recent_turns: int
    index_vector_folder: str
    index_run_name: str
    embedding_model: str

    def to_json(self) -> str:
        """Serialize the snapshot as pretty JSON for ``build.json``."""
        return json.dumps(dataclasses.asdict(self), indent=2)

    @staticmethod
    def from_json(text: str) -> BuildSnapshot | None:
        """Parse a ``build.json`` payload, or None when it is invalid/incomplete."""
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        known = {field.name for field in dataclasses.fields(BuildSnapshot)}
        try:
            return BuildSnapshot(**{key: data[key] for key in known if key in data})
        except TypeError:
            return None


def _next_build_sequence(session_root: Path) -> int:
    """Return the next free ``rag_build_`` sequence number under *session_root*."""
    if not session_root.is_dir():
        return 1
    sequences = [
        sequence
        for child in session_root.iterdir()
        if child.is_dir()
        for sequence in [parse_folder_sequence(child.name, prefix=RAG_BUILD_FOLDER_PREFIX)]
        if sequence is not None
    ]
    return max(sequences) + 1 if sequences else 1


def allocate_build_name(session_root: Path | str) -> str:
    """Return the next build folder name, e.g. ``rag_build_01_garden``."""
    sequence = _next_build_sequence(Path(session_root))
    artifact_id = format_sequence_id(sequence, _generate_readable_crawl_suffix())
    return folder_name(RAG_BUILD_FOLDER_PREFIX, artifact_id)


def is_build_name(name: str) -> bool:
    """Return True when *name* is a ``rag_build_<NN>_<word>`` folder name."""
    return name.startswith(RAG_BUILD_FOLDER_PREFIX) and (
        parse_folder_sequence(name, prefix=RAG_BUILD_FOLDER_PREFIX) is not None
    )


def build_dir(session_root: Path | str, name: str) -> Path:
    """Return the contained path of build *name* under *session_root*."""
    root = Path(session_root).resolve()
    return ensure_within_root(root, root / name)


def create_build(
    session_root: Path | str,
    snapshot: BuildSnapshot,
    source_index_dir: Path | str,
    prompt_texts: Mapping[str, str],
) -> Path:
    """Materialize a self-contained build folder and return its path.

    Copies the selected index into ``<build>/<vector_folder>/<run_name>`` (so the
    showcase rediscovers it via ``list_session_indexes``), freezes each effective
    prompt as ``conversational_rag_history/prompt_<key>.txt`` (read back when the
    build root is used as the effective session root), and writes ``build.json``.
    """
    target = build_dir(session_root, snapshot.name)
    target.mkdir(parents=True, exist_ok=True)
    index_target = ensure_within_root(
        target, target / snapshot.index_vector_folder / snapshot.index_run_name
    )
    shutil.copytree(source_index_dir, index_target)
    for key, text in prompt_texts.items():
        save_conversational_prompt(target, key, text)
    (target / BUILD_MANIFEST_FILENAME).write_text(snapshot.to_json(), encoding="utf-8")
    return target


def load_build(build_root: Path | str) -> BuildSnapshot | None:
    """Return the snapshot stored in *build_root*/``build.json``, or None."""
    try:
        text = (Path(build_root) / BUILD_MANIFEST_FILENAME).read_text(encoding="utf-8")
    except OSError:
        return None
    return BuildSnapshot.from_json(text)


def list_builds(session_root: Path | str) -> list[BuildSnapshot]:
    """Return the session's builds, newest first, skipping any unreadable one."""
    root = Path(session_root)
    if not root.is_dir():
        return []
    snapshots = [
        snapshot
        for child in root.iterdir()
        if child.is_dir() and is_build_name(child.name)
        for snapshot in [load_build(child)]
        if snapshot is not None
    ]
    snapshots.sort(
        key=lambda snapshot: sequence_sort_key(snapshot.name, prefix=RAG_BUILD_FOLDER_PREFIX)
    )
    return snapshots


def delete_build(session_root: Path | str, name: str) -> bool:
    """Delete build *name* from the session; False when it is not a build folder."""
    if not is_build_name(name):
        return False
    return delete_generated_folder(session_root, name)


def format_built_at(created_at_utc: str) -> str:
    """Render an ISO-8601 build timestamp as ``30 October 2026 07:48 UTC``."""
    try:
        parsed = datetime.fromisoformat(created_at_utc)
    except ValueError:
        return created_at_utc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime(_BUILT_AT_FORMAT)


def _is_safe_segment(value: str) -> bool:
    return bool(_SAFE_SEGMENT.match(value)) and ".." not in value


def _restore_padding(encoded: str) -> str:
    return encoded + "=" * (-len(encoded) % 4)


def make_showcase_token(session_id: str, build_name: str, secret: str) -> str:
    """Return a tamper-proof showcase-link token binding *session_id* + *build_name*.

    The token carries ``urlsafe-b64("<session>:<build>")`` plus an HMAC-SHA256
    signature over the same payload, so only this instance's *secret* can mint a
    link and the ids cannot be altered to point at another build.
    """
    raw = f"{session_id}{_PAYLOAD_SEPARATOR}{build_name}".encode()
    signature = hmac.new(secret.encode("utf-8"), _HMAC_DOMAIN + raw, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{encoded}{_TOKEN_SEPARATOR}{signature}"


def parse_showcase_token(token: str, secret: str) -> tuple[str, str] | None:
    """Return ``(session_id, build_name)`` from a valid token, else None.

    Returns None for a malformed token, a bad signature (wrong key or tampered
    payload), or ids that fail the path-safety check — never raises.
    """
    encoded, separator, signature = token.partition(_TOKEN_SEPARATOR)
    if not separator or not encoded or not signature:
        return None
    try:
        raw = base64.urlsafe_b64decode(_restore_padding(encoded))
    except ValueError:
        return None
    expected = hmac.new(secret.encode("utf-8"), _HMAC_DOMAIN + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    session_id, payload_separator, build_name = raw.decode("utf-8", "replace").partition(
        _PAYLOAD_SEPARATOR
    )
    safe = _is_safe_segment(session_id) and _is_safe_segment(build_name)
    if not payload_separator or not safe:
        return None
    return session_id, build_name
