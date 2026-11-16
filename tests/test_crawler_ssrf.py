"""Tests for the opt-in SSRF guard (block_private_networks) — mocked DNS, no network."""

from __future__ import annotations

import asyncio
import socket

import pytest

from crawl4md import CrawlerConfig
from crawl4md._internal import ssrf
from crawl4md._internal.ssrf import BlockedNetworkError
from crawl4md.crawler import SiteCrawler


def _resolves_to(ip: str):
    return lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0", "::1"],
)
def test_blocks_internal_addresses(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _resolves_to(ip))
    assert ssrf.url_targets_blocked_network("http://internal.test/") is True


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1"])
def test_allows_public_addresses(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _resolves_to(ip))
    assert ssrf.url_targets_blocked_network("http://public.test/") is False


def test_resolution_failure_is_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(host: str, port: object) -> list:
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", boom)
    # Unresolvable host → not blocked; the normal fetch will fail and report it.
    assert ssrf.url_targets_blocked_network("http://nope.test/") is False


def test_missing_host_is_not_blocked() -> None:
    assert ssrf.url_targets_blocked_network("not-a-url") is False


class _UnreachableCrawler:
    async def arun(self, url: str, config: object) -> str:  # pragma: no cover - must not run
        raise AssertionError("arun must not be called for a blocked target")


def test_fetch_html_url_raises_when_guard_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"], block_private_networks=True))
    monkeypatch.setattr("crawl4md.crawler.url_targets_blocked_network", lambda url: True)

    with pytest.raises(BlockedNetworkError):
        asyncio.run(
            crawler._fetch_html_url(
                url="http://169.254.169.254/latest/meta-data/",
                crawler=_UnreachableCrawler(),
                run_cfg=None,
            )
        )


def test_fetch_html_url_proceeds_when_guard_off() -> None:
    # Default config (guard off) never resolves and fetches normally — behaviour unchanged.
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"]))
    seen: dict[str, str] = {}

    class _Crawler:
        async def arun(self, url: str, config: object) -> str:
            seen["url"] = url
            return "ok"

    result = asyncio.run(
        crawler._fetch_html_url(url="http://10.0.0.1/", crawler=_Crawler(), run_cfg=None)
    )

    assert result == "ok"
    assert seen["url"] == "http://10.0.0.1/"


def test_download_pdf_blocked_returns_failed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"], block_private_networks=True))
    monkeypatch.setattr("crawl4md.crawler.url_targets_blocked_network", lambda url: True)

    result = asyncio.run(crawler._download_pdf("http://127.0.0.1/secret.pdf"))

    assert result.success is False
    assert "private or internal" in (result.error or "")


def test_download_docx_blocked_returns_failed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"], block_private_networks=True))
    monkeypatch.setattr("crawl4md.crawler.url_targets_blocked_network", lambda url: True)

    result = asyncio.run(crawler._download_docx("http://10.0.0.9/secret.docx"))

    assert result.success is False
    assert "private or internal" in (result.error or "")
