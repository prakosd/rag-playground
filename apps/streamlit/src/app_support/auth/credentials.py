"""Credential models and pure auth helpers for crawl authentication.

HTTP (Basic/Bearer) credentials are injected into the crawler as an
``Authorization`` header. The model lists its sensitive fields in ``SECRET_FIELDS``
so the store encrypts exactly those at rest and keeps only display metadata (name,
type, created time) in clear text.
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "CREDENTIAL_MODELS",
    "Credential",
    "CredentialKind",
    "HttpAuthType",
    "HttpCredential",
    "http_authorization_header",
    "new_credential_id",
    "parse_url_prefixes",
    "select_http_credential",
    "select_http_secret_headers",
]

CredentialKind = Literal["http"]
HttpAuthType = Literal["basic", "bearer"]

_AUTHORIZATION_HEADER = "Authorization"


def new_credential_id() -> str:
    """Return a short random identifier for a stored credential row."""
    return secrets.token_hex(8)


def parse_url_prefixes(value: Any) -> list[str]:
    """Return cleaned URL prefixes from a comma-separated string or a list."""
    items = value.split(",") if isinstance(value, str) else list(value or [])
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require(value: str, message: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped


class _BaseCredential(BaseModel):
    """Fields shared by every credential kind."""

    SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset()

    id: str = Field(default_factory=new_credential_id)
    name: str
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _require(v, "Credential name is required.")


class HttpCredential(_BaseCredential):
    """Basic or Bearer HTTP auth applied to the crawler as an Authorization header."""

    SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset({"secret", "url_prefixes"})

    kind: CredentialKind = "http"
    auth_type: HttpAuthType
    secret: str
    url_prefixes: list[str] = Field(default_factory=list)

    @field_validator("url_prefixes", mode="before")
    @classmethod
    def _parse_prefixes(cls, v: Any) -> list[str]:
        return parse_url_prefixes(v)

    @field_validator("secret")
    @classmethod
    def _validate_secret(cls, v: str) -> str:
        return _require(v, "A token or username:password is required.")

    @model_validator(mode="after")
    def _validate_basic_format(self) -> HttpCredential:
        if self.auth_type == "basic" and ":" not in self.secret:
            raise ValueError("Basic credentials must be in 'username:password' form.")
        return self


Credential = HttpCredential

CREDENTIAL_MODELS: dict[str, type[_BaseCredential]] = {"http": HttpCredential}


def http_authorization_header(auth_type: str, secret: str) -> tuple[str, str]:
    """Return the ``(name, value)`` Authorization header for an HTTP credential.

    Bearer uses the secret verbatim; Basic base64-encodes the ``username:password``
    secret, matching what a browser sends.
    """
    if auth_type == "bearer":
        return (_AUTHORIZATION_HEADER, f"Bearer {secret}")
    encoded = base64.b64encode(secret.encode()).decode("ascii")
    return (_AUTHORIZATION_HEADER, f"Basic {encoded}")


def select_http_credential(
    urls: Iterable[str], credentials: Iterable[Credential]
) -> HttpCredential | None:
    """Return the HTTP credential whose longest URL prefix matches any seed URL.

    A credential matches when one of its prefixes is a prefix of a seed URL; among
    all matches the one with the longest prefix wins (most specific). Returns None
    when nothing matches. Non-HTTP credentials are ignored.
    """
    url_list = list(urls)
    best: HttpCredential | None = None
    best_length = -1
    for credential in credentials:
        if not isinstance(credential, HttpCredential):
            continue
        for prefix in credential.url_prefixes:
            if len(prefix) > best_length and any(url.startswith(prefix) for url in url_list):
                best = credential
                best_length = len(prefix)
    return best


def select_http_secret_headers(
    urls: Iterable[str], credentials: Iterable[Credential]
) -> dict[str, str]:
    """Return the Authorization header dict for the best-matching HTTP credential.

    Returns an empty dict when no stored HTTP credential matches the seed URLs.
    """
    credential = select_http_credential(urls, credentials)
    if credential is None:
        return {}
    name, value = http_authorization_header(credential.auth_type, credential.secret)
    return {name: value}
