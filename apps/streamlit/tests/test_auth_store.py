"""Tests for encrypted credential persistence (app_support.auth.store)."""

from __future__ import annotations

import json
from pathlib import Path

from app_support.auth.credentials import HttpCredential
from app_support.auth.crypto import CredentialCipher
from app_support.auth.store import (
    add_credential,
    credentials_file,
    delete_credentials,
    list_credential_rows,
    load_credentials,
    resolve_http_secret_headers,
)

_SECRET = "signing-secret"
_SESSION = "cedar_river"


def _cipher(session: str = _SESSION) -> CredentialCipher:
    return CredentialCipher(_SECRET, session)


def test_load_and_list_empty_when_no_file(tmp_path: Path) -> None:
    assert list_credential_rows(tmp_path) == []
    assert load_credentials(tmp_path, _cipher()) == []


def test_add_then_list_shows_metadata(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="Prod API", auth_type="bearer", secret="tok", url_prefixes="https://api.site.com"
    )

    add_credential(tmp_path, cred, _cipher())
    rows = list_credential_rows(tmp_path)

    assert len(rows) == 1
    assert rows[0].name == "Prod API"
    assert rows[0].kind == "http"
    assert rows[0].auth_type == "bearer"
    assert rows[0].created_at is not None


def test_add_then_load_round_trips_secret(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="Prod", auth_type="basic", secret="user:pass", url_prefixes="https://site.com"
    )

    add_credential(tmp_path, cred, _cipher())
    loaded = load_credentials(tmp_path, _cipher())

    assert len(loaded) == 1
    assert isinstance(loaded[0], HttpCredential)
    assert loaded[0].secret == "user:pass"
    assert loaded[0].url_prefixes == ["https://site.com"]


def test_stored_file_hides_plaintext_secret(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="Prod", auth_type="bearer", secret="super-secret-token", url_prefixes="https://s.com"
    )

    add_credential(tmp_path, cred, _cipher())
    raw = credentials_file(tmp_path).read_text(encoding="utf-8")

    assert "super-secret-token" not in raw
    assert "https://s.com" not in raw  # url_prefixes are inside the encrypted payload
    assert "payload" in raw
    assert "Prod" in raw  # display metadata stays readable


def test_delete_removes_by_id(tmp_path: Path) -> None:
    cred = HttpCredential(name="A", auth_type="bearer", secret="t", url_prefixes="https://a.com")
    add_credential(tmp_path, cred, _cipher())

    assert delete_credentials(tmp_path, [cred.id]) == 1
    assert list_credential_rows(tmp_path) == []


def test_delete_multiple_by_ids(tmp_path: Path) -> None:
    first = HttpCredential(name="A", auth_type="bearer", secret="t", url_prefixes="https://a.com")
    second = HttpCredential(name="B", auth_type="bearer", secret="t", url_prefixes="https://b.com")
    third = HttpCredential(name="C", auth_type="bearer", secret="t", url_prefixes="https://c.com")
    for cred in (first, second, third):
        add_credential(tmp_path, cred, _cipher())

    assert delete_credentials(tmp_path, [first.id, third.id]) == 2
    remaining = list_credential_rows(tmp_path)
    assert [row.name for row in remaining] == ["B"]


def test_delete_unknown_id_removes_nothing(tmp_path: Path) -> None:
    cred = HttpCredential(name="A", auth_type="bearer", secret="t", url_prefixes="https://a.com")
    add_credential(tmp_path, cred, _cipher())

    assert delete_credentials(tmp_path, ["does-not-exist"]) == 0
    assert delete_credentials(tmp_path, []) == 0
    assert len(list_credential_rows(tmp_path)) == 1


def test_load_skips_entries_from_other_session(tmp_path: Path) -> None:
    cred = HttpCredential(name="A", auth_type="bearer", secret="t", url_prefixes="https://a.com")
    add_credential(tmp_path, cred, _cipher("session_one"))

    # A different session derives a different key and cannot decrypt the payload.
    assert load_credentials(tmp_path, _cipher("session_two")) == []
    # But the display row still lists it (metadata is not encrypted).
    assert len(list_credential_rows(tmp_path)) == 1


def test_corrupt_file_is_treated_as_empty(tmp_path: Path) -> None:
    path = credentials_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")

    assert list_credential_rows(tmp_path) == []
    assert load_credentials(tmp_path, _cipher()) == []


def test_stored_document_has_expected_shape(tmp_path: Path) -> None:
    cred = HttpCredential(name="A", auth_type="bearer", secret="t", url_prefixes="https://a.com")
    add_credential(tmp_path, cred, _cipher())

    document = json.loads(credentials_file(tmp_path).read_text(encoding="utf-8"))

    assert document["version"] == 1
    entry = document["credentials"][0]
    assert entry["kind"] == "http"
    assert entry["auth_type"] == "bearer"
    assert "secret" not in entry  # the token field never lands in clear text
    assert entry["payload"]


def test_resolve_http_secret_headers_matches_seed_url(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="A", auth_type="bearer", secret="tok", url_prefixes="https://site.com"
    )
    add_credential(tmp_path, cred, _cipher())

    headers = resolve_http_secret_headers(tmp_path, _SECRET, _SESSION, ["https://site.com/page"])

    assert headers == {"Authorization": "Bearer tok"}


def test_resolve_http_secret_headers_empty_without_match(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="A", auth_type="bearer", secret="tok", url_prefixes="https://other.com"
    )
    add_credential(tmp_path, cred, _cipher())

    assert resolve_http_secret_headers(tmp_path, _SECRET, _SESSION, ["https://site.com"]) == {}


def test_resolve_http_secret_headers_empty_when_no_credentials(tmp_path: Path) -> None:
    assert resolve_http_secret_headers(tmp_path, _SECRET, _SESSION, ["https://site.com"]) == {}


def test_resolve_http_secret_headers_ignores_wrong_session_secret(tmp_path: Path) -> None:
    cred = HttpCredential(
        name="A", auth_type="bearer", secret="tok", url_prefixes="https://site.com"
    )
    add_credential(tmp_path, cred, _cipher())

    # A different signing secret cannot decrypt the payload, so nothing is applied.
    assert (
        resolve_http_secret_headers(tmp_path, "other-secret", _SESSION, ["https://site.com"]) == {}
    )
