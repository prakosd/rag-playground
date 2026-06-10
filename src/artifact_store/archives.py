"""Safe extraction of text members from user-supplied zip archives.

Downstream tools accept ``.zip`` uploads that may contain arbitrary members. The
helpers here enforce a strict allow-list (``.md``/``.txt`` only) and reject any
member name that could escape the destination directory (zip-slip protection).
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from artifact_store.paths import ensure_within_root

__all__ = [
    "TEXT_MEMBER_SUFFIXES",
    "extract_text_members",
    "is_safe_member_name",
    "iter_text_members",
]

TEXT_MEMBER_SUFFIXES = frozenset({".md", ".txt"})


def is_safe_member_name(name: str) -> bool:
    """Return True when a zip member name is safe to extract.

    Rejects empty names, directory entries, absolute paths, Windows drive
    prefixes, and any parent-directory traversal so extraction cannot escape the
    destination directory.
    """
    if not name or name.endswith("/"):
        return False
    normalized = name.replace("\\", "/")
    first_segment = normalized.split("/", 1)[0]
    if normalized.startswith("/") or ":" in first_segment:
        return False
    return ".." not in PurePosixPath(normalized).parts


def _is_text_member(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in TEXT_MEMBER_SUFFIXES


def iter_text_members(zip_path: Path | str) -> Iterator[tuple[str, bytes]]:
    """Yield ``(member_name, data)`` for safe ``.md``/``.txt`` members of a zip.

    Unsafe member names and unsupported file types are skipped silently; the
    caller decides how to surface skipped counts.
    """
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not is_safe_member_name(name) or not _is_text_member(name):
                continue
            with archive.open(info) as member:
                yield name, member.read()


def extract_text_members(zip_path: Path | str, dest_dir: Path | str) -> list[Path]:
    """Extract safe ``.md``/``.txt`` members of *zip_path* into *dest_dir*.

    Returns the list of written file paths. Containment is enforced against
    *dest_dir* so no member can be written outside it.
    """
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    resolved_dest = destination.resolve()
    written: list[Path] = []
    for name, data in iter_text_members(zip_path):
        try:
            target = ensure_within_root(resolved_dest, destination / name)
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(target)
    return written
