"""Encrypted, session-scoped persistence for crawl authentication credentials.

Credentials live under ``<session>/authentication/credentials.json`` so they
surface in the Output Files tree. Only display metadata (id, kind, name, auth
type, created time) is stored in clear text; every sensitive field is encrypted
into an opaque ``payload`` token via :class:`CredentialCipher`. The list and
delete paths never need the cipher — only adding (encrypt) and the crawl-time
load (decrypt) do — so rendering the credential table never decrypts a secret.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifact_store.paths import ensure_within_root
from log4py import get_logger
from pydantic import ValidationError

from app_support.auth.credentials import (
    CREDENTIAL_MODELS,
    Credential,
    select_http_secret_headers,
)
from app_support.auth.crypto import CredentialCipher

__all__ = [
    "AUTH_DIR_NAME",
    "CredentialRow",
    "add_credential",
    "credentials_file",
    "delete_credentials",
    "list_credential_rows",
    "load_credentials",
    "resolve_http_secret_headers",
]

_logger = get_logger(__name__)

AUTH_DIR_NAME = "authentication"
_CREDENTIALS_FILE_NAME = "credentials.json"
_SCHEMA_VERSION = 1
_PAYLOAD_KEY = "payload"
_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class CredentialRow:
    """Display metadata for one stored credential (carries no secret material)."""

    id: str
    kind: str
    name: str
    created_at: datetime | None
    auth_type: str | None = None


def credentials_file(session_root: Path | str) -> Path:
    """Return the session's credential file path, validated for containment."""
    root = Path(session_root)
    return ensure_within_root(root, root / AUTH_DIR_NAME / _CREDENTIALS_FILE_NAME)


def list_credential_rows(session_root: Path | str) -> list[CredentialRow]:
    """Return display rows for stored credentials, newest first (no decryption)."""
    rows = [
        CredentialRow(
            id=str(entry.get("id", "")),
            kind=str(entry.get("kind", "")),
            name=str(entry.get("name", "")),
            created_at=_parse_created_at(entry.get("created_at")),
            auth_type=entry["auth_type"] if isinstance(entry.get("auth_type"), str) else None,
        )
        for entry in _read_entries(session_root)
        if entry.get("id")
    ]
    rows.sort(key=lambda row: (row.created_at or _MIN_UTC, row.name), reverse=True)
    return rows


def add_credential(
    session_root: Path | str, credential: Credential, cipher: CredentialCipher
) -> None:
    """Encrypt *credential*'s sensitive fields and append it to the session store."""
    entries = _read_entries(session_root)
    entries.append(_credential_to_entry(credential, cipher))
    _write_entries(session_root, entries)


def delete_credentials(session_root: Path | str, credential_ids: Iterable[str]) -> int:
    """Remove every credential whose id is in *credential_ids*; return the count removed."""
    id_set = {credential_id for credential_id in credential_ids if credential_id}
    if not id_set:
        return 0
    entries = _read_entries(session_root)
    remaining = [entry for entry in entries if entry.get("id") not in id_set]
    removed = len(entries) - len(remaining)
    if removed:
        _write_entries(session_root, remaining)
    return removed


def load_credentials(session_root: Path | str, cipher: CredentialCipher) -> list[Credential]:
    """Return fully decrypted credentials; entries that fail to decrypt are skipped."""
    credentials: list[Credential] = []
    for entry in _read_entries(session_root):
        credential = _entry_to_credential(entry, cipher)
        if credential is not None:
            credentials.append(credential)
    return credentials


def resolve_http_secret_headers(
    session_root: Path | str,
    signing_secret: str,
    session_id: str,
    urls: Iterable[str],
) -> dict[str, str]:
    """Return the Authorization header for the best-matching stored HTTP credential.

    Decrypts the session's credentials and picks the HTTP credential whose longest
    URL prefix matches a seed URL. Returns an empty dict when none match (or none
    are stored), so the crawl proceeds unauthenticated.
    """
    cipher = CredentialCipher(signing_secret, session_id)
    credentials = load_credentials(session_root, cipher)
    return select_http_secret_headers(urls, credentials)


def _credential_to_entry(credential: Credential, cipher: CredentialCipher) -> dict[str, Any]:
    full = credential.model_dump(mode="json")
    secret_part = {key: full[key] for key in credential.SECRET_FIELDS}
    entry = {key: value for key, value in full.items() if key not in credential.SECRET_FIELDS}
    entry[_PAYLOAD_KEY] = cipher.encrypt(json.dumps(secret_part))
    return entry


def _entry_to_credential(entry: dict[str, Any], cipher: CredentialCipher) -> Credential | None:
    model_cls = CREDENTIAL_MODELS.get(str(entry.get("kind", "")))
    token = entry.get(_PAYLOAD_KEY)
    if model_cls is None or not isinstance(token, str):
        return None
    decrypted = cipher.decrypt(token)
    if decrypted is None:
        return None
    try:
        secret_part = json.loads(decrypted)
    except ValueError:
        return None
    data = {key: value for key, value in entry.items() if key != _PAYLOAD_KEY}
    if isinstance(secret_part, dict):
        data.update(secret_part)
    try:
        return model_cls(**data)
    except ValidationError:
        _logger.debug("Skipping stored credential that failed validation")
        return None


def _read_entries(session_root: Path | str) -> list[dict[str, Any]]:
    path = credentials_file(session_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _logger.warning("Could not read credentials file; treating as empty")
        return []
    entries = data.get("credentials") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _write_entries(session_root: Path | str, entries: list[dict[str, Any]]) -> None:
    path = credentials_file(session_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"version": _SCHEMA_VERSION, "credentials": entries}
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _parse_created_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
