"""Tests for the S3 storage backend using an in-memory fake client (no network)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from artifact_store import StorageBackend
from artifact_store_s3 import S3StorageBackend


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _NotFound(Exception):
    """Stands in for boto3's ClientError(404) on a missing key."""

    response = {"Error": {"Code": "404"}}


class FakeS3Client:
    """A tiny in-memory stand-in for a boto3 S3 client."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[bytes, datetime]] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.store[Key] = (Body, datetime.now(timezone.utc))
        return {}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        data, _ = self.store[Key]
        return {"Body": _FakeBody(data)}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.store:
            raise _NotFound(Key)
        data, when = self.store[Key]
        return {"LastModified": when, "ContentLength": len(data)}

    def list_objects_v2(
        self,
        Bucket: str,
        Prefix: str = "",
        Delimiter: str | None = None,
        MaxKeys: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        common: set[str] = set()
        for key in sorted(k for k in self.store if k.startswith(Prefix)):
            rest = key[len(Prefix) :]
            if Delimiter and Delimiter in rest:
                common.add(Prefix + rest.split(Delimiter, 1)[0] + Delimiter)
            else:
                contents.append({"Key": key, "LastModified": self.store[key][1]})
        if MaxKeys is not None:
            contents = contents[:MaxKeys]
        resp: dict[str, Any] = {
            "KeyCount": len(contents) + len(common),
            "Contents": contents,
            "IsTruncated": False,
        }
        if common:
            resp["CommonPrefixes"] = [{"Prefix": p} for p in sorted(common)]
        return resp

    def delete_objects(self, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:
        for obj in Delete["Objects"]:
            self.store.pop(obj["Key"], None)
        return {}


def test_s3_backend_satisfies_the_protocol() -> None:
    assert isinstance(S3StorageBackend("bkt", client=FakeS3Client()), StorageBackend)


def test_s3_backend_round_trips_and_prefixes_keys() -> None:
    client = FakeS3Client()
    backend = S3StorageBackend("bkt", prefix="app/", client=client)

    backend.write_bytes(Path("sessions/s1/a.md"), b"hello")

    assert "app/sessions/s1/a.md" in client.store  # POSIX key under the prefix
    assert backend.read_bytes(Path("sessions/s1/a.md")) == b"hello"
    assert backend.exists(Path("sessions/s1/a.md"))
    assert not backend.exists(Path("sessions/s1/missing.md"))


def test_s3_backend_lists_immediate_children() -> None:
    client = FakeS3Client()
    backend = S3StorageBackend("bkt", client=client)
    backend.write_bytes(Path("root/a.md"), b"a")
    backend.write_bytes(Path("root/sub/b.md"), b"b")
    backend.write_bytes(Path("root/c.md"), b"c")

    children = backend.iterdir(Path("root"))

    assert [p.name for p in children] == ["a.md", "c.md", "sub"]  # files + subdir folded
    assert backend.is_dir(Path("root"))
    assert backend.is_dir(Path("root/sub"))
    assert not backend.is_dir(Path("root/a.md"))


def test_s3_backend_mtime_falls_back_to_prefix_for_a_dir() -> None:
    client = FakeS3Client()
    backend = S3StorageBackend("bkt", client=client)
    backend.write_bytes(Path("root/a.md"), b"a")

    assert backend.mtime(Path("root/a.md")) > 0  # the object's own LastModified
    assert backend.mtime(Path("root")) > 0  # a dir key → newest child


def test_s3_backend_remove_tree_deletes_the_prefix() -> None:
    client = FakeS3Client()
    backend = S3StorageBackend("bkt", client=client)
    backend.write_bytes(Path("root/a.md"), b"a")
    backend.write_bytes(Path("root/sub/b.md"), b"b")

    backend.remove_tree(Path("root"))

    assert client.store == {}
    assert not backend.exists(Path("root"))


def test_s3_backend_reraises_non_not_found_head_errors() -> None:
    class _AccessDenied(Exception):
        response = {"Error": {"Code": "403"}}

    client = FakeS3Client()

    def _deny(Bucket: str, Key: str) -> dict[str, Any]:
        raise _AccessDenied

    client.head_object = _deny  # type: ignore[method-assign]
    backend = S3StorageBackend("bkt", client=client)

    with pytest.raises(_AccessDenied):
        backend.exists(Path("root/a.md"))  # a 403 must not be swallowed as 'absent'
