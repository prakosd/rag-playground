"""Tests for session-scoped credential encryption (app_support.auth.crypto)."""

from __future__ import annotations

from app_support.auth.crypto import CredentialCipher, derive_credential_key


def test_derive_key_is_deterministic_for_same_inputs() -> None:
    assert derive_credential_key("secret", "session_a") == derive_credential_key(
        "secret", "session_a"
    )


def test_derive_key_differs_per_session() -> None:
    assert derive_credential_key("secret", "session_a") != derive_credential_key(
        "secret", "session_b"
    )


def test_derive_key_differs_per_secret() -> None:
    assert derive_credential_key("secret_one", "session_a") != derive_credential_key(
        "secret_two", "session_a"
    )


def test_encrypt_decrypt_round_trip() -> None:
    cipher = CredentialCipher("secret", "session_a")

    token = cipher.encrypt("Bearer sk-1234")

    assert token != "Bearer sk-1234"
    assert cipher.decrypt(token) == "Bearer sk-1234"


def test_ciphertext_hides_plaintext() -> None:
    cipher = CredentialCipher("secret", "session_a")

    token = cipher.encrypt("super-secret-token")

    assert "super-secret-token" not in token


def test_decrypt_fails_for_other_session_key() -> None:
    token = CredentialCipher("secret", "session_a").encrypt("value")

    # A different session derives a different key and must not decrypt it.
    assert CredentialCipher("secret", "session_b").decrypt(token) is None


def test_decrypt_fails_for_other_secret() -> None:
    token = CredentialCipher("secret_one", "session_a").encrypt("value")

    assert CredentialCipher("secret_two", "session_a").decrypt(token) is None


def test_decrypt_returns_none_for_garbage_token() -> None:
    cipher = CredentialCipher("secret", "session_a")

    assert cipher.decrypt("not-a-valid-token") is None
    assert cipher.decrypt("") is None
