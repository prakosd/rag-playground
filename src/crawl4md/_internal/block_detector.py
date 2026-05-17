"""WAF and bot-protection block detection helpers."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

__all__ = [
    "content_length_without_chrome",
    "is_blocked",
]

_BLOCK_SIGNATURES = (
    "incapsula incident",
    "access denied</title>",
    "attention required! | cloudflare",
    "please turn javascript on and reload the page",
    "checking your browser before accessing",
    "javascript is required",
)
_BLOCK_SIGNATURES_RE = re.compile(
    "|".join(re.escape(signature) for signature in _BLOCK_SIGNATURES),
    re.IGNORECASE,
)
_BLOCK_MAX_CONTENT_LENGTH = 500
_CHROME_STRIP_TAGS = ["nav", "script", "style", "form", "header", "footer", "noscript"]


def is_blocked(html: str) -> bool:
    """Return True if the HTML looks like a WAF/bot-protection block page."""
    if not html:
        return False
    return _BLOCK_SIGNATURES_RE.search(html) is not None


def content_length_without_chrome(html: str) -> int:
    """Return visible-text length after stripping boilerplate page chrome."""
    if not html:
        return 0
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_CHROME_STRIP_TAGS):
        tag.decompose()
    return len(soup.get_text(separator=" ", strip=True))
