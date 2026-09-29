"""Symmetric encryption for session-scoped credential secrets.

Credentials a user adds on the Crawl page (HTTP Basic/Bearer auth)
are persisted under the browser session's folder and surface in the Output Files
tree. Their sensitive values are encrypted at rest with Fernet so previewing or
downloading that file never reveals a raw secret. The key is derived from the
deployment's zip-signing secret joined with the session ID, so each session's
credentials are encrypted under a distinct key and a file lifted into another
session cannot be decrypted.

This is at-rest protection against casual exposure through the file UI, not a
guarantee against someone who already holds the server secret and the session ID.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

__all__ = [
    "CredentialCipher",
    "derive_credential_key",
]


def derive_credential_key(signing_secret: str, session_id: str) -> bytes:
    """Return a Fernet key derived from *signing_secret* joined with *session_id*.

    SHA-256 over ``"{signing_secret}:{session_id}"`` yields 32 bytes, which
    urlsafe-base64 encodes to a valid Fernet key. Deterministic per pair, so a
    session always reproduces the key that encrypted its own credentials.
    """
    digest = hashlib.sha256(f"{signing_secret}:{session_id}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


class CredentialCipher:
    """Encrypt and decrypt credential secret strings for one browser session."""

    def __init__(self, signing_secret: str, session_id: str) -> None:
        self._fernet = Fernet(derive_credential_key(signing_secret, session_id))

    def encrypt(self, plaintext: str) -> str:
        """Return a URL-safe ciphertext token for *plaintext*."""
        return self._fernet.encrypt(plaintext.encode()).decode("ascii")

    def decrypt(self, token: str) -> str | None:
        """Return the plaintext for *token*, or None when it cannot be decrypted.

        Returns None for a token produced under a different key/session or for a
        tampered or malformed value, so a corrupt on-disk file degrades to "no
        readable secret" instead of raising.
        """
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except (InvalidToken, ValueError):
            return None
