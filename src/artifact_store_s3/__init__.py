"""Amazon S3 storage backend for ``artifact_store`` (opt-in ``[s3]`` extra).

Kept out of the pure ``artifact_store`` foundation so that package never depends on
``boto3``. Import :class:`S3StorageBackend` and pass it wherever an
``artifact_store.StorageBackend`` is expected.
"""

from __future__ import annotations

from artifact_store_s3.s3_backend import S3StorageBackend

__all__ = ["S3StorageBackend"]
