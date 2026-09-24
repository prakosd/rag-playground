"""Tests for the storage-backend factory and its wiring into session cleanup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from artifact_store import LocalStorageBackend

from app_support import storage
from app_support.session_manager import cleanup_old_sessions


def _settings(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "storage_backend": "local",
        "storage_s3_bucket": "",
        "storage_s3_prefix": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_resolve_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "get_settings", _settings)
    assert isinstance(storage.resolve_storage_backend(), LocalStorageBackend)


def test_resolve_s3_requires_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "get_settings", lambda: _settings(storage_backend="s3"))
    with pytest.raises(ValueError, match="STORAGE_S3_BUCKET"):
        storage.resolve_storage_backend()


def test_resolve_s3_builds_the_s3_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import artifact_store_s3.s3_backend as s3_backend

    monkeypatch.setattr(s3_backend, "_default_client", lambda: object())  # no boto3 needed
    monkeypatch.setattr(
        storage, "get_settings", lambda: _settings(storage_backend="s3", storage_s3_bucket="bkt")
    )

    from artifact_store_s3 import S3StorageBackend

    assert isinstance(storage.resolve_storage_backend(), S3StorageBackend)


def test_resolve_rejects_an_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "get_settings", lambda: _settings(storage_backend="gcs"))
    with pytest.raises(ValueError, match="Unknown STORAGE_BACKEND"):
        storage.resolve_storage_backend()


class _SpyBackend:
    """Records which paths cleanup consults, so injection is provably honored."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, Path]] = []

    def exists(self, path: Path) -> bool:
        self.seen.append(("exists", Path(path)))
        return True

    def is_dir(self, path: Path) -> bool:
        return True

    def read_bytes(self, path: Path) -> bytes:
        raise NotImplementedError

    def write_bytes(self, path: Path, data: bytes) -> None:
        raise NotImplementedError

    def iterdir(self, path: Path) -> list[Path]:
        self.seen.append(("iterdir", Path(path)))
        return []

    def mtime(self, path: Path) -> float:
        return 0.0

    def remove_tree(self, path: Path) -> None:
        raise NotImplementedError


def test_cleanup_consults_the_injected_backend(tmp_path: Path) -> None:
    spy = _SpyBackend()

    removed = cleanup_old_sessions(tmp_path, backend=spy)

    assert removed == []  # the spy lists no sessions
    assert ("exists", tmp_path) in spy.seen  # gated on the backend, not Path.exists()
    assert ("iterdir", tmp_path) in spy.seen
