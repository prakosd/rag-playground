"""Tests for WAF/block detection helpers."""

from __future__ import annotations

import pytest

from crawl4md._internal.block_detector import (
    _BLOCK_SIGNATURES,
    content_length_without_chrome,
    is_blocked,
)


@pytest.mark.parametrize("signature", _BLOCK_SIGNATURES)
def test_is_blocked_detects_known_signatures(signature: str) -> None:
    html = f"<html><body>{signature.upper()}</body></html>"

    assert is_blocked(html) is True


def test_is_blocked_returns_false_for_regular_html() -> None:
    html = "<html><body><main>Real page content</main></body></html>"

    assert is_blocked(html) is False


def test_is_blocked_returns_false_for_empty_html() -> None:
    assert is_blocked("") is False


def test_content_length_without_chrome_counts_main_content_only() -> None:
    html = (
        "<html><body>"
        "<nav>Menu Home About Contact Support</nav>"
        "<header>Site Header</header>"
        "<main><p>Real content here</p></main>"
        "<footer>Footer links</footer>"
        "</body></html>"
    )

    length = content_length_without_chrome(html)

    assert length == len("Real content here")


def test_content_length_without_chrome_returns_zero_for_empty_html() -> None:
    assert content_length_without_chrome("") == 0
