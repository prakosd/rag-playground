"""Tests for SiteCrawler anti-bot escalation (proxies, undetected browser, fallback)."""

from __future__ import annotations

import pytest

from crawl4md import messages
from crawl4md.config import CrawlerConfig
from crawl4md.crawler import SiteCrawler


class _FakeProxyConfig:
    """Minimal stand-in for crawl4ai.ProxyConfig used to assert wiring."""

    DIRECT = object()

    def __init__(self, server: str) -> None:
        self.server = server

    @classmethod
    def from_string(cls, value: str) -> _FakeProxyConfig:
        return cls(value)


def _crawler(**config_kwargs: object) -> SiteCrawler:
    return SiteCrawler(CrawlerConfig(urls=["https://example.com"], **config_kwargs))


def test_build_proxy_config_returns_none_without_proxies() -> None:
    assert _crawler()._build_proxy_config() is None


def test_build_proxy_config_is_direct_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p1:8080", "http://p2:8080"])

    result = crawler._build_proxy_config()

    assert result is not None
    assert result[0] is _FakeProxyConfig.DIRECT
    assert [proxy.server for proxy in result[1:]] == ["http://p1:8080", "http://p2:8080"]


def test_build_proxy_config_none_when_proxyconfig_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: None)
    assert _crawler(proxies=["http://p:8080"])._build_proxy_config() is None


def test_apply_anti_bot_run_options_noop_by_default() -> None:
    kwargs: dict = {}
    _crawler()._apply_anti_bot_run_options(kwargs)
    assert kwargs == {}


def test_apply_anti_bot_run_options_adds_proxy_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)

    async def fallback(url: str) -> str:
        return "<html></html>"

    crawler = SiteCrawler(
        CrawlerConfig(urls=["https://example.com"], proxies=["http://p:8080"]),
        fallback_fetch_function=fallback,
    )
    kwargs: dict = {}
    crawler._apply_anti_bot_run_options(kwargs)

    assert kwargs["proxy_config"][0] is _FakeProxyConfig.DIRECT
    assert kwargs["fallback_fetch_function"] is fallback


def test_build_run_config_includes_anti_bot_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p:8080"])
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_run_config(fake_run_config_cls)
    assert "proxy_config" in captured


def test_fallback_fetch_function_is_stored() -> None:
    async def fallback(url: str) -> str:
        return ""

    crawler = SiteCrawler(
        CrawlerConfig(urls=["https://example.com"]), fallback_fetch_function=fallback
    )
    assert crawler._fallback_fetch_function is fallback


def test_build_undetected_strategy_builds_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _FakeAdapter:
        pass

    class _FakeStrategy:
        def __init__(self, *, browser_config: object, browser_adapter: object) -> None:
            captured["browser_config"] = browser_config
            captured["adapter"] = browser_adapter

    monkeypatch.setattr(
        "crawl4md.crawler._load_undetected_classes", lambda: (_FakeStrategy, _FakeAdapter)
    )
    crawler = _crawler(undetected_browser=True)
    browser_cfg = object()

    strategy = crawler._build_undetected_strategy(browser_cfg)

    assert isinstance(strategy, _FakeStrategy)
    assert captured["browser_config"] is browser_cfg
    assert isinstance(captured["adapter"], _FakeAdapter)


def test_build_undetected_strategy_warns_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_undetected_classes", lambda: None)
    crawler = _crawler(undetected_browser=True)
    emitted: list = []
    crawler._emit_crawl_warning = lambda message: emitted.append(message)

    result = crawler._build_undetected_strategy(object())

    assert result is None
    assert emitted[0].code == messages.CODE_UNDETECTED_UNAVAILABLE
