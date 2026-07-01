"""Tests for SiteCrawler anti-bot escalation (proxies, undetected browser, fallback)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from crawl4md import messages
from crawl4md.config import CrawlerConfig
from crawl4md.crawler import SiteCrawler
from tests.conftest import _make_mock_result


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
    crawler._apply_anti_bot_run_options(kwargs, use_proxy=True, use_fallback_api=True)

    assert kwargs["proxy_config"][0] is _FakeProxyConfig.DIRECT
    assert kwargs["fallback_fetch_function"] is fallback


def test_apply_anti_bot_run_options_skips_proxy_but_keeps_fallback(
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
    crawler._apply_anti_bot_run_options(kwargs, use_proxy=False, use_fallback_api=True)

    assert "proxy_config" not in kwargs
    assert kwargs["fallback_fetch_function"] is fallback


def test_build_run_config_skips_proxies_on_initial_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p:8080"])
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    # Initial crawl must NOT use paid proxies; retries do.
    crawler._build_run_config(fake_run_config_cls)
    assert "proxy_config" not in captured
    captured.clear()
    crawler._build_fallback_run_config(fake_run_config_cls, 2)
    assert "proxy_config" in captured


def _paid_resource_crawler(
    monkeypatch: pytest.MonkeyPatch, *, proxies: list[str] | None = None, api: bool = False
) -> SiteCrawler:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)

    async def fallback(url: str) -> str:
        return "<html></html>"

    return SiteCrawler(
        CrawlerConfig(urls=["https://example.com"], proxies=proxies or []),
        fallback_fetch_function=fallback if api else None,
    )


def _captured_fallback_run_config(crawler: SiteCrawler, round_num: int) -> dict:
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_fallback_run_config(fake_run_config_cls, round_num)
    return captured


def test_paid_resource_rounds_none_when_unset() -> None:
    assert _crawler()._paid_resource_rounds() == (None, None)


def test_paid_resource_rounds_proxy_only(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, proxies=["http://p:8080"])
    assert crawler._paid_resource_rounds() == (2, None)


def test_paid_resource_rounds_api_only(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, api=True)
    assert crawler._paid_resource_rounds() == (None, 2)


def test_paid_resource_rounds_both(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, proxies=["http://p:8080"], api=True)
    assert crawler._paid_resource_rounds() == (2, 3)


def test_retry_rounds_use_proxy_then_api_when_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, proxies=["http://p:8080"], api=True)

    round2 = _captured_fallback_run_config(crawler, 2)
    assert "proxy_config" in round2
    assert "fallback_fetch_function" not in round2

    round3 = _captured_fallback_run_config(crawler, 3)
    assert "proxy_config" not in round3
    assert "fallback_fetch_function" in round3

    round4 = _captured_fallback_run_config(crawler, 4)
    assert "proxy_config" not in round4
    assert "fallback_fetch_function" not in round4


def test_retry_uses_api_on_first_retry_when_only_api(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, api=True)

    round2 = _captured_fallback_run_config(crawler, 2)
    assert "fallback_fetch_function" in round2
    assert "proxy_config" not in round2

    assert "fallback_fetch_function" not in _captured_fallback_run_config(crawler, 3)


def test_initial_crawl_uses_no_fallback_api(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _paid_resource_crawler(monkeypatch, proxies=["http://p:8080"], api=True)
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_run_config(fake_run_config_cls)
    assert "proxy_config" not in captured
    assert "fallback_fetch_function" not in captured


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
    crawler = _crawler()
    browser_cfg = object()

    strategy = crawler._build_undetected_strategy(browser_cfg)

    assert isinstance(strategy, _FakeStrategy)
    assert captured["browser_config"] is browser_cfg
    assert isinstance(captured["adapter"], _FakeAdapter)


def test_build_undetected_strategy_warns_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_undetected_classes", lambda: None)
    crawler = _crawler()
    emitted: list = []
    crawler._emit_crawl_warning = lambda message: emitted.append(message)

    result = crawler._build_undetected_strategy(object())

    assert result is None
    assert emitted[0].code == messages.CODE_UNDETECTED_UNAVAILABLE


def test_round_one_standard_then_retries_use_undetected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Round 1 opens a standard browser; retry rounds escalate to undetected."""
    blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 1</body></html>"
    blocked = _make_mock_result("https://example.com/p", blocked_html, "blocked")
    fixed = _make_mock_result("https://example.com/p", "<p>ok</p>", "ok")
    calls = {"n": 0}

    async def mock_arun(url, config):
        calls["n"] += 1
        return blocked if calls["n"] == 1 else fixed

    mock_instance = AsyncMock()
    mock_instance.arun = mock_arun
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    crawler_kwargs: list[dict] = []

    def factory(**kwargs):
        crawler_kwargs.append(kwargs)
        return mock_instance

    sentinel = object()
    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", factory)
    monkeypatch.setattr(SiteCrawler, "_build_undetected_strategy", lambda self, cfg: sentinel)

    crawler = SiteCrawler(
        CrawlerConfig(urls=["https://example.com/p"], limit=10, max_retries=1),
        output_base=tmp_path,
    )
    crawler.crawl()

    assert len(crawler_kwargs) == 2
    assert "crawler_strategy" not in crawler_kwargs[0]
    assert crawler_kwargs[1]["crawler_strategy"] is sentinel
