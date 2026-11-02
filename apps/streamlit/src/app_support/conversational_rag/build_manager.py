"""Create, name, list, and resolve Step 5 (Conversational RAG) build snapshots.

A "build" freezes the current Step 5 settings and all 10 prompts into a single
``build.json`` under a timestamped run subdir (``rag_build_<NN>_<word>/<timestamp>/``,
mirroring ``crawl_``/``vector_``), referencing the owner session's chosen index
rather than copying it, so it can be launched as a read-only showcase, exported, or
reloaded. This module owns the build
naming, the :class:`BuildSnapshot` on-disk model, discovery/deletion, and the readable
5-word showcase slug (allocated unique, resolved by scanning builds — no signing). It
is pure (no Streamlit) so it stays unit-testable; the UI adapter maps it to/from the
live controls.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from artifact_store.naming import (
    RAG_BUILD_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    format_utc_timestamp_slug,
    parse_folder_sequence,
    parse_utc_timestamp_slug,
    sequence_sort_key,
)
from artifact_store.paths import ensure_within_root

from app_support.generated_files import delete_generated_folder
from app_support.session_manager import _generate_readable_crawl_suffix, generate_showcase_slug

__all__ = [
    "BUILD_MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "BuildSnapshot",
    "allocate_build_name",
    "allocate_showcase_slug",
    "build_config_signature",
    "build_dir",
    "build_run_dir",
    "builds_referencing_folder",
    "create_build",
    "delete_build",
    "is_build_name",
    "list_builds",
    "load_build",
    "newest_build",
    "resolve_slug",
]

BUILD_MANIFEST_FILENAME = "build.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BuildSnapshot:
    """The frozen Step 5 settings + index reference persisted as ``build.json``."""

    schema_version: int
    created_at_utc: str
    name: str
    slug: str
    language: str
    answer_model: str
    top_k: int
    tone: str
    reranker: str
    aux_model_id: str
    decomposition_limit: int
    followup_show_count: int
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
    prompts: dict[str, str]

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


def create_build(session_root: Path | str, snapshot: BuildSnapshot) -> Path:
    """Materialize a build folder and return it (``rag_build_<NN>_<word>``).

    The build is a single ``build.json`` under a timestamped run subdir
    (``<build>/<timestamp>/build.json``, mirroring ``crawl_``/``vector_``), carrying
    the frozen prompts inline. It does **not** copy the vector index: ``build.json``
    records the index reference (``index_vector_folder``/``index_run_name``) and the
    showcase resolves the shared index from the owner session (see
    ``resolve_build_index``). Export re-bundles a copy on demand so an exported build
    stays portable.
    """
    target = build_dir(session_root, snapshot.name)
    run_dir = ensure_within_root(target, target / format_utc_timestamp_slug())
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / BUILD_MANIFEST_FILENAME).write_text(snapshot.to_json(), encoding="utf-8")
    return target


def build_run_dir(build_root: Path | str) -> Path | None:
    """Return the build's single timestamped run subdir (holds build.json + index)."""
    root = Path(build_root)
    if not root.is_dir():
        return None
    for child in sorted(root.iterdir()):
        if child.is_dir() and parse_utc_timestamp_slug(child.name) is not None:
            return child
    return None


def load_build(build_root: Path | str) -> BuildSnapshot | None:
    """Return the snapshot in *build_root*'s run dir ``build.json``, or None."""
    run_dir = build_run_dir(build_root)
    if run_dir is None:
        return None
    try:
        text = (run_dir / BUILD_MANIFEST_FILENAME).read_text(encoding="utf-8")
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


def newest_build(session_root: Path | str) -> BuildSnapshot | None:
    """Return the session's most recent build, or None when there are none."""
    builds = list_builds(session_root)
    return builds[0] if builds else None


def build_config_signature(snapshot: BuildSnapshot) -> tuple[object, ...]:
    """Return a build's configuration identity, for change detection.

    Covers every setting, the index reference, and the frozen prompts, but excludes
    the volatile name/slug/timestamp/schema so two builds with identical settings
    compare equal. The Step 5 control uses it to offer 'Launch' (re-open the latest
    build) instead of silently creating a duplicate when nothing has changed.
    """
    data = dataclasses.asdict(snapshot)
    for volatile in ("schema_version", "created_at_utc", "name", "slug"):
        data.pop(volatile, None)
    prompts = data.pop("prompts", {})
    return (tuple(sorted(data.items())), tuple(sorted(prompts.items())))


def builds_referencing_folder(session_root: Path | str, vector_folder: str) -> list[BuildSnapshot]:
    """Return the session's builds that reference the vector-index *vector_folder*.

    Derived by scanning each build's recorded index reference, so it is always
    accurate: deleting a build simply drops it from the scan, with no reference file
    to keep in sync. The delete flow uses it to block removing an index that builds
    still point at.
    """
    return [
        snapshot
        for snapshot in list_builds(session_root)
        if snapshot.index_vector_folder == vector_folder
    ]


def delete_build(session_root: Path | str, name: str) -> bool:
    """Delete build *name* from the session; False when it is not a build folder."""
    if not is_build_name(name):
        return False
    return delete_generated_folder(session_root, name)


def _iter_builds(sessions_root: Path) -> Iterator[tuple[Path, BuildSnapshot]]:
    """Yield (build_root, snapshot) for every readable build under *sessions_root*."""
    if not sessions_root.is_dir():
        return
    for session in sorted(sessions_root.iterdir()):
        if session.is_dir():
            for snapshot in list_builds(session):
                yield build_dir(session, snapshot.name), snapshot


def allocate_showcase_slug(sessions_root: Path | str) -> str:
    """Return a fresh showcase-link slug not already claimed by any build."""
    existing = {snapshot.slug for _, snapshot in _iter_builds(Path(sessions_root))}
    slug = generate_showcase_slug()
    while slug in existing:
        slug = generate_showcase_slug()
    return slug


def resolve_slug(sessions_root: Path | str, slug: str) -> Path | None:
    """Return the build folder whose ``build.json`` stores *slug*, or None.

    Slugs are unique at creation, so the first match is the only one. Returns None
    for an empty or unknown slug, and never builds a path from the slug itself (it
    only compares), so a crafted slug cannot escape the sessions root.
    """
    if not slug:
        return None
    for build_root, snapshot in _iter_builds(Path(sessions_root)):
        if snapshot.slug == slug:
            return build_root
    return None
