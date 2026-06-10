"""Path-containment helpers shared across artifact producers and consumers."""

from __future__ import annotations

from pathlib import Path

__all__ = ["ensure_within_root"]


def ensure_within_root(root: Path | str, path: Path | str) -> Path:
    """Resolve *path* and reject it if it escapes *root*.

    Returns the resolved path when it is *root* itself or a descendant of it.
    Raises ``ValueError`` otherwise, which callers use as a directory-traversal
    guard before reading or writing files.
    """
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError("Path is outside the allowed root folder.")
    return resolved_path
