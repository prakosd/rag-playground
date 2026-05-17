"""URL normalization, filtering, and link extraction helpers."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

from crawl4md.config import CrawlerConfig, CrawlResult

__all__ = [
    "extract_base_domains",
    "extract_links",
    "normalize_url",
    "url_allowed",
    "url_in_allowed_domain",
]

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']')
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\$\{|%7B%7B|\{\{|\{%")
_URL_SCHEMES = ("http://", "https://")

_STATIC_ASSET_EXTENSIONS = frozenset(
    (
        ".css",
        ".js",
        ".ico",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".bmp",
        ".tiff",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".webm",
        ".ogg",
        ".zip",
        ".gz",
        ".tar",
        ".rar",
        ".7z",
        ".xml",
        ".json",
        ".rss",
        ".atom",
        ".axd",
        ".ashx",
        ".asmx",
    )
)

_BOILERPLATE_DOMAINS = frozenset(
    (
        "browsehappy.com",
        "google.com",
    )
)


def url_in_allowed_domain(url: str, allowed_domains: set[str]) -> bool:
    """Check whether a URL belongs to the configured crawl domain(s)."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    bare_netloc = netloc[4:] if netloc.startswith("www.") else netloc

    return not allowed_domains or any(
        bare_netloc == bare_domain or bare_netloc.endswith("." + bare_domain)
        for domain in allowed_domains
        for bare_domain in (domain[4:] if domain.startswith("www.") else domain,)
    )


def url_allowed(url: str, config: CrawlerConfig, allowed_domains: set[str]) -> bool:
    """Check whether a URL passes domain and path filters."""
    if not url_in_allowed_domain(url, allowed_domains):
        return False

    parsed = urlparse(url)
    netloc_path = parsed.netloc + parsed.path
    if any(
        netloc_path.startswith(domain) or netloc_path.startswith("www." + domain)
        for domain in _BOILERPLATE_DOMAINS
    ):
        return False

    if config.compiled_include_only_paths and not any(
        pattern.search(url) for pattern in config.compiled_include_only_paths
    ):
        return False

    return not (
        config.compiled_exclude_paths
        and any(pattern.search(url) for pattern in config.compiled_exclude_paths)
    )


def normalize_url(url: str, *, strip_www: bool = True) -> str:
    """Normalize a URL to reduce duplicate crawling."""
    parsed = urlparse(url)
    scheme = "https"
    netloc = parsed.netloc.lower()
    if strip_www and netloc.startswith("www."):
        netloc = netloc[4:]
    return urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))


def extract_base_domains(urls: list[str], *, strip_www: bool = True) -> set[str]:
    """Derive base domains from seed URLs."""
    domains: set[str] = set()
    for url in urls:
        netloc = urlparse(url).netloc.lower()
        if strip_www and netloc.startswith("www."):
            netloc = netloc[4:]
        domains.add(netloc)
    return domains


def extract_links(result: CrawlResult, base_url: str, *, strip_www: bool = True) -> list[str]:
    """Extract absolute http(s) links from crawled HTML."""
    links: list[str] = []
    for match in _HREF_RE.finditer(result.html):
        href = match.group(1)
        if _TEMPLATE_PLACEHOLDER_RE.search(href):
            continue
        absolute = urljoin(base_url, href)
        if absolute.startswith(_URL_SCHEMES):
            absolute = absolute.split("#")[0]
            parsed = urlparse(absolute)
            netloc_path = parsed.netloc + parsed.path
            if any(
                netloc_path.startswith(domain) or netloc_path.startswith("www." + domain)
                for domain in _BOILERPLATE_DOMAINS
            ):
                continue
            path = parsed.path.lower()
            if any(path.endswith(extension) for extension in _STATIC_ASSET_EXTENSIONS):
                continue
            if absolute not in links:
                links.append(absolute)

    seen: set[str] = set()
    normalized: list[str] = []
    for link in links:
        normalized_link = normalize_url(link, strip_www=strip_www)
        if normalized_link not in seen:
            seen.add(normalized_link)
            normalized.append(normalized_link)
    return normalized
