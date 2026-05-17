"""Tests for URL filtering and link extraction helpers."""

from __future__ import annotations

import pytest

from crawl4md._internal.url_filter import (
    extract_base_domains,
    extract_links,
    normalize_url,
    url_allowed,
    url_in_allowed_domain,
)
from crawl4md.config import CrawlerConfig, CrawlResult


def test_extract_base_domains_strips_www() -> None:
    urls = ["https://www.example.com/start", "https://sub.example.com/path"]

    domains = extract_base_domains(urls)

    assert domains == {"example.com", "sub.example.com"}


def test_normalize_url_forces_https_and_drops_fragment() -> None:
    url = "http://WWW.Example.com/Path?a=1#frag"

    normalized = normalize_url(url)

    assert normalized == "https://example.com/Path?a=1"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.example.com/page", True),
        ("https://example.com/page", True),
        ("https://docs.example.com/page", True),
        ("https://other.com/page", False),
    ],
)
def test_url_in_allowed_domain_matches_base_domain_and_subdomains(url: str, expected: bool) -> None:
    assert url_in_allowed_domain(url, {"example.com"}) is expected


def test_url_allowed_applies_include_and_exclude_patterns() -> None:
    config = CrawlerConfig(
        urls=["https://example.com"],
        include_only_paths=[r"/blog"],
        exclude_paths=[r"/admin"],
    )

    assert url_allowed("https://example.com/blog/post", config, {"example.com"}) is True
    assert url_allowed("https://example.com/about", config, {"example.com"}) is False
    assert url_allowed("https://example.com/blog/admin", config, {"example.com"}) is False


def test_url_allowed_rejects_boilerplate_domain() -> None:
    config = CrawlerConfig(urls=["https://example.com"])

    allowed = url_allowed("https://browsehappy.com/update-browser", config, set())

    assert allowed is False


def test_extract_links_normalizes_relative_links_and_deduplicates() -> None:
    result = CrawlResult(
        url="https://example.com",
        html=('<a href="/page">One</a><a href="http://www.example.com/page#section">Duplicate</a>'),
        success=True,
    )

    links = extract_links(result, "https://example.com")

    assert links == ["https://example.com/page"]


def test_extract_links_skips_static_assets_but_keeps_pdfs() -> None:
    result = CrawlResult(
        url="https://example.com",
        html=(
            '<a href="/style.css">CSS</a>'
            '<a href="/app.js">JS</a>'
            '<a href="/image.png">PNG</a>'
            '<a href="/guide.pdf">PDF</a>'
        ),
        success=True,
    )

    links = extract_links(result, "https://example.com")

    assert links == ["https://example.com/guide.pdf"]


def test_extract_links_skips_template_placeholders() -> None:
    result = CrawlResult(
        url="https://example.com",
        html=(
            '<a href="/real">Real</a>'
            '<a href="/${slug}">Template</a>'
            '<a href="/{{slug}}">Template</a>'
            '<a href="/{% url %}">Template</a>'
        ),
        success=True,
    )

    links = extract_links(result, "https://example.com")

    assert links == ["https://example.com/real"]
