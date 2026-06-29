"""Tests for the app's anti-bot escalation wiring (proxies, undetected, fallback)."""

from __future__ import annotations

import asyncio

import pytest

from crawl4md_streamlit.crawl_jobs import _build_fallback_fetch_function, build_configs

_VALUES: dict[str, object] = {"urls": "https://example.com"}


def test_build_configs_reads_proxies_from_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWL_PROXIES", "http://p1:8080, http://p2:8080")

    crawler_config, _, _ = build_configs(_VALUES)

    assert crawler_config.proxies == ["http://p1:8080", "http://p2:8080"]


def test_build_configs_defaults_to_no_anti_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWL_PROXIES", raising=False)

    crawler_config, _, _ = build_configs(_VALUES)

    assert crawler_config.proxies == []


def test_fallback_fetch_function_is_none_without_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWL_FALLBACK_API_URL", raising=False)

    assert _build_fallback_fetch_function() is None


def test_fallback_fetch_function_calls_scraping_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWL_FALLBACK_API_URL", "https://scrape.example/api")
    monkeypatch.setenv("CRAWL_FALLBACK_API_TOKEN", "secret-token")
    captured: dict[str, object] = {}

    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(
            self, url: str, params: object = None, headers: object = None
        ) -> _FakeResponse:
            captured.update(url=url, params=params, headers=headers)
            return _FakeResponse()

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.httpx.AsyncClient", _FakeClient)

    fetch = _build_fallback_fetch_function()
    assert fetch is not None
    html = asyncio.run(fetch("https://blocked.example/page"))

    assert html == "<html>ok</html>"
    assert captured["params"] == {"url": "https://blocked.example/page"}
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}
