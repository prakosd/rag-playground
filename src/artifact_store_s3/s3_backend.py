"""``StorageBackend`` implemented over Amazon S3 (or any S3-compatible store).

Paths are mapped to object keys by their POSIX form (anchor/leading separators
stripped) under an optional prefix, so a local session tree mirrors 1:1 into a
bucket. ``boto3`` is imported lazily, and the S3 client is injectable, so this
module loads (and is testable) without the ``[s3]`` extra installed.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

# S3 DeleteObjects accepts at most 1000 keys per request.
_DELETE_BATCH = 1000
# boto3 raises ClientError with one of these codes when a key/object is absent.
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3StorageBackend:
    """An ``artifact_store.StorageBackend`` backed by an S3 bucket.

    ``client`` is injected for testing; when omitted, a real ``boto3`` S3 client is
    created lazily so importing this module never requires ``boto3`` until used.
    """

    def __init__(self, bucket: str, prefix: str = "", *, client: Any | None = None) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = client if client is not None else _default_client()

    def _key(self, path: Path) -> str:
        parts = PurePosixPath(Path(path).as_posix()).parts
        rel = "/".join(part for part in parts if part != "/")
        return f"{self._prefix}/{rel}" if self._prefix else rel

    def exists(self, path: Path) -> bool:
        return self._object_exists(self._key(path)) or self.is_dir(path)

    def is_dir(self, path: Path) -> bool:
        prefix = self._key(path).rstrip("/") + "/"
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=1)
        return resp.get("KeyCount", 0) > 0

    def read_bytes(self, path: Path) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=self._key(path))
        return resp["Body"].read()

    def write_bytes(self, path: Path, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._key(path), Body=data)

    def iterdir(self, path: Path) -> list[Path]:
        prefix = self._key(path).rstrip("/") + "/"
        base = Path(path)
        names: set[str] = set()
        for page in self._paginate(prefix, delimiter="/"):
            for common in page.get("CommonPrefixes", []):
                names.add(common["Prefix"][len(prefix) :].rstrip("/"))
            for obj in page.get("Contents", []):
                name = obj["Key"][len(prefix) :]
                if name:
                    names.add(name)
        return sorted((base / name for name in names), key=lambda p: p.name)

    def mtime(self, path: Path) -> float:
        key = self._key(path)
        head = self._head(key)
        if head is not None:
            return head["LastModified"].timestamp()
        # A "directory" key: the newest object beneath it (used by session cleanup).
        latest = 0.0
        for page in self._paginate(key.rstrip("/") + "/"):
            for obj in page.get("Contents", []):
                latest = max(latest, obj["LastModified"].timestamp())
        return latest

    def remove_tree(self, path: Path) -> None:
        key = self._key(path)
        keys = [
            obj["Key"]
            for page in self._paginate(key.rstrip("/") + "/")
            for obj in page.get("Contents", [])
        ]
        if self._object_exists(key):
            keys.append(key)
        for start in range(0, len(keys), _DELETE_BATCH):
            batch = keys[start : start + _DELETE_BATCH]
            self._client.delete_objects(
                Bucket=self._bucket, Delete={"Objects": [{"Key": k} for k in batch]}
            )

    def _object_exists(self, key: str) -> bool:
        return self._head(key) is not None

    def _head(self, key: str) -> dict[str, Any] | None:
        # A missing key reads as None; any other error (403, throttling, network) surfaces.
        try:
            return self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise

    def _paginate(self, prefix: str, *, delimiter: str = "") -> list[dict[str, Any]]:
        params: dict[str, Any] = {"Bucket": self._bucket, "Prefix": prefix}
        if delimiter:
            params["Delimiter"] = delimiter
        pages: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            if token:
                params["ContinuationToken"] = token
            resp = self._client.list_objects_v2(**params)
            pages.append(resp)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return pages


def _is_missing(exc: Exception) -> bool:
    """True when *exc* is S3's 'key not found' (boto3 ClientError 404 / NoSuchKey)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code") in _NOT_FOUND_CODES
    return False


def _default_client() -> Any:
    import boto3  # imported lazily so the module loads without the [s3] extra

    return boto3.client("s3")
