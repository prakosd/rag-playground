"""Backend-neutral storage seam for persisted artifacts.

``StorageBackend`` is the small, filesystem-like interface the app uses to read,
list, and remove persisted artifacts, so the same code can run against the local
filesystem today or an object store (e.g. S3) later. ``LocalStorageBackend`` is the
default and preserves current behavior exactly. A cloud backend (e.g. the separate
``artifact_store_s3`` package) implements the same Protocol and stays out of this
pure-foundation package, so ``artifact_store`` keeps its stdlib-only dependency
boundary.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["LocalStorageBackend", "StorageBackend"]


@runtime_checkable
class StorageBackend(Protocol):
    """A minimal, filesystem-like interface over a durable artifact store.

    Paths are the store's keys: a local backend treats them as real filesystem
    paths; an object-store backend maps them to keys (prefixes act as folders).
    Only the operations the app actually needs — read, list, stat, remove — are
    included, so alternative backends stay small and honest.
    """

    def exists(self, path: Path) -> bool: ...

    def is_dir(self, path: Path) -> bool: ...

    def read_bytes(self, path: Path) -> bytes: ...

    def write_bytes(self, path: Path, data: bytes) -> None: ...

    def iterdir(self, path: Path) -> list[Path]: ...

    def mtime(self, path: Path) -> float: ...

    def remove_tree(self, path: Path) -> None: ...


class LocalStorageBackend:
    """``StorageBackend`` over the local filesystem — the default, unchanged behavior."""

    def exists(self, path: Path) -> bool:
        return Path(path).exists()

    def is_dir(self, path: Path) -> bool:
        return Path(path).is_dir()

    def read_bytes(self, path: Path) -> bytes:
        return Path(path).read_bytes()

    def write_bytes(self, path: Path, data: bytes) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def iterdir(self, path: Path) -> list[Path]:
        return sorted(Path(path).iterdir())

    def mtime(self, path: Path) -> float:
        return Path(path).stat().st_mtime

    def remove_tree(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)
