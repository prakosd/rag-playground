"""Optional shared-secret authentication for the backend HTTP routes.

Auth is **opt-in**: when ``BACKEND_AUTH_TOKEN`` is unset (the default) every request passes,
preserving local / in-process use. When it is set, every non-health route requires a matching
``X-Backend-Token`` header (compared in constant time), so a networked deployment is not left
open. The frontend attaches the same header when the token is configured.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app_backend.config import get_backend_settings

BACKEND_TOKEN_HEADER = "X-Backend-Token"


def require_backend_auth(
    x_backend_token: str = Header(default="", alias=BACKEND_TOKEN_HEADER),
) -> None:
    """Reject the request unless it carries the configured backend token (when one is set)."""
    expected = get_backend_settings().backend_auth_token
    if not expected:
        return  # auth disabled — preserve the default open, local behaviour
    # Compare UTF-8 bytes so a non-ASCII header yields a clean 401 (not a compare_digest 500).
    if not hmac.compare_digest(x_backend_token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid or missing backend token")
