"""Select the artifact ``StorageBackend`` from settings (local by default).

Keeps the S3 dependency opt-in: the boto3-backed ``artifact_store_s3`` package is
imported only when ``STORAGE_BACKEND=s3``, so a local deployment never needs the
``[s3]`` extra. See docs/CLOUD_DEPLOYMENT.md.
"""

from __future__ import annotations

from artifact_store import LocalStorageBackend, StorageBackend

from app_support.settings import get_settings

__all__ = ["resolve_storage_backend"]


def resolve_storage_backend() -> StorageBackend:
    """Return the configured storage backend: ``local`` (default) or ``s3``."""
    settings = get_settings()
    choice = settings.storage_backend.strip().lower()
    if choice in ("", "local"):
        return LocalStorageBackend()
    if choice == "s3":
        if not settings.storage_s3_bucket:
            raise ValueError("STORAGE_BACKEND=s3 requires STORAGE_S3_BUCKET to be set.")
        try:
            from artifact_store_s3 import S3StorageBackend
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "STORAGE_BACKEND=s3 needs the [s3] extra: pip install 'rag-playground[s3]'."
            ) from exc
        return S3StorageBackend(settings.storage_s3_bucket, settings.storage_s3_prefix)
    raise ValueError(f"Unknown STORAGE_BACKEND {settings.storage_backend!r} (use 'local' or 's3').")
