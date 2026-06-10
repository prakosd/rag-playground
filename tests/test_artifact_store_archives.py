from __future__ import annotations

import zipfile
from pathlib import Path

from artifact_store.archives import (
    extract_text_members,
    is_safe_member_name,
    iter_text_members,
)


def _make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def test_is_safe_member_name_accepts_normal_paths() -> None:
    assert is_safe_member_name("notes.md")
    assert is_safe_member_name("sub/dir/notes.txt")


def test_is_safe_member_name_rejects_traversal_and_absolute() -> None:
    assert not is_safe_member_name("../escape.txt")
    assert not is_safe_member_name("/etc/passwd")
    assert not is_safe_member_name("C:/Windows/system.ini")
    assert not is_safe_member_name("dir/")
    assert not is_safe_member_name("")


def test_iter_text_members_keeps_only_supported_text_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    _make_zip(
        zip_path,
        {
            "keep.md": b"# md",
            "nested/keep.txt": b"txt",
            "skip.py": b"print()",
            "skip.json": b"{}",
        },
    )

    members = dict(iter_text_members(zip_path))

    assert set(members) == {"keep.md", "nested/keep.txt"}
    assert members["keep.md"] == b"# md"


def test_iter_text_members_skips_unsafe_members(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(
        zip_path,
        {
            "ok.md": b"ok",
            "../escape.md": b"bad",
        },
    )

    members = dict(iter_text_members(zip_path))

    assert set(members) == {"ok.md"}


def test_extract_text_members_writes_only_supported_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    _make_zip(
        zip_path,
        {
            "a.md": b"a",
            "deep/b.txt": b"b",
            "c.bin": b"binary",
        },
    )
    dest = tmp_path / "out"

    written = extract_text_members(zip_path, dest)

    written_names = sorted(p.name for p in written)
    assert written_names == ["a.md", "b.txt"]
    assert (dest / "a.md").read_bytes() == b"a"
    assert (dest / "deep" / "b.txt").read_bytes() == b"b"
    assert not (dest / "c.bin").exists()


def test_extract_text_members_does_not_escape_destination(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"ok.md": b"ok", "../escape.txt": b"bad"})
    dest = tmp_path / "out"

    written = extract_text_members(zip_path, dest)

    assert [p.name for p in written] == ["ok.md"]
    assert not (tmp_path / "escape.txt").exists()
