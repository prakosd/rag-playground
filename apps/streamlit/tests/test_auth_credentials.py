"""Tests for credential models and pure auth helpers (app_support.auth.credentials)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_support.auth.credentials import (
    HttpCredential,
    http_authorization_header,
    new_credential_id,
    parse_url_prefixes,
    select_http_credential,
    select_http_secret_headers,
)


def test_new_credential_id_is_unique() -> None:
    assert new_credential_id() != new_credential_id()


def test_parse_url_prefixes_from_string() -> None:
    assert parse_url_prefixes("https://a.com,  https://b.com ,, https://c.com") == [
        "https://a.com",
        "https://b.com",
        "https://c.com",
    ]


def test_parse_url_prefixes_from_list_and_empty() -> None:
    assert parse_url_prefixes(["  x ", "", "y"]) == ["x", "y"]
    assert parse_url_prefixes("") == []
    assert parse_url_prefixes(None) == []


def test_bearer_authorization_header() -> None:
    assert http_authorization_header("bearer", "sk-123") == ("Authorization", "Bearer sk-123")


def test_basic_authorization_header_base64_encodes() -> None:
    # base64("user:pass") == "dXNlcjpwYXNz"
    assert http_authorization_header("basic", "user:pass") == (
        "Authorization",
        "Basic dXNlcjpwYXNz",
    )


def test_http_credential_parses_prefixes_and_defaults_metadata() -> None:
    cred = HttpCredential(name="  Prod ", auth_type="bearer", secret="tok", url_prefixes="a, b")

    assert cred.name == "Prod"
    assert cred.url_prefixes == ["a", "b"]
    assert cred.id
    assert cred.created_at.tzinfo is not None


def test_http_basic_requires_colon() -> None:
    with pytest.raises(ValidationError):
        HttpCredential(name="x", auth_type="basic", secret="no-colon")


def test_http_name_required() -> None:
    with pytest.raises(ValidationError):
        HttpCredential(name="   ", auth_type="bearer", secret="tok")


def test_select_http_credential_prefers_longest_prefix() -> None:
    short = HttpCredential(
        name="short", auth_type="bearer", secret="short-tok", url_prefixes="https://site.com"
    )
    long = HttpCredential(
        name="long",
        auth_type="bearer",
        secret="long-tok",
        url_prefixes="https://site.com/docs",
    )

    best = select_http_credential(["https://site.com/docs/page"], [short, long])

    assert best is long


def test_select_http_credential_returns_none_without_match() -> None:
    cred = HttpCredential(
        name="x", auth_type="bearer", secret="t", url_prefixes="https://other.com"
    )

    assert select_http_credential(["https://site.com/page"], [cred]) is None


def test_select_http_secret_headers_builds_header() -> None:
    cred = HttpCredential(
        name="x", auth_type="bearer", secret="tok", url_prefixes="https://site.com"
    )

    assert select_http_secret_headers(["https://site.com/p"], [cred]) == {
        "Authorization": "Bearer tok"
    }


def test_select_http_secret_headers_empty_without_match() -> None:
    cred = HttpCredential(
        name="x", auth_type="bearer", secret="tok", url_prefixes="https://other.com"
    )

    assert select_http_secret_headers(["https://site.com"], [cred]) == {}
