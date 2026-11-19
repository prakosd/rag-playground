"""Tests for SiteCrawler anti-bot escalation (proxies, undetected browser)."""

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


def test_apply_anti_bot_run_options_adds_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p:8080"])
    kwargs: dict = {}
    crawler._apply_anti_bot_run_options(kwargs, use_proxy=True)

    assert kwargs["proxy_config"][0] is _FakeProxyConfig.DIRECT


def test_apply_anti_bot_run_options_skips_proxy_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p:8080"])
    kwargs: dict = {}
    crawler._apply_anti_bot_run_options(kwargs, use_proxy=False)

    assert "proxy_config" not in kwargs


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


def _proxy_crawler(
    monkeypatch: pytest.MonkeyPatch,
    *,
    proxies: list[str] | None = None,
    proxy_on_initial: bool = False,
    max_retries: int = 3,
) -> SiteCrawler:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    return SiteCrawler(
        CrawlerConfig(
            urls=["https://example.com"],
            proxies=proxies or [],
            proxy_on_initial=proxy_on_initial,
            max_retries=max_retries,
        )
    )


def _captured_fallback_run_config(crawler: SiteCrawler, round_num: int) -> dict:
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_fallback_run_config(fake_run_config_cls, round_num)
    return captured


def test_paid_resource_rounds_empty_without_proxies() -> None:
    assert _crawler()._paid_resource_rounds() == frozenset()


def test_paid_resource_rounds_covers_every_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _proxy_crawler(monkeypatch, proxies=["http://p:8080"], max_retries=3)
    # The initial crawl (round 1) runs direct; every retry round uses the proxies.
    assert crawler._paid_resource_rounds() == frozenset({2, 3, 4})


def test_paid_resource_rounds_proxy_on_initial(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _proxy_crawler(
        monkeypatch, proxies=["http://p:8080"], proxy_on_initial=True, max_retries=3
    )
    # proxy_on_initial adds the initial crawl (round 1) to the proxied retry rounds.
    assert crawler._paid_resource_rounds() == frozenset({1, 2, 3, 4})


def test_build_run_config_uses_proxy_on_initial_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crawl4md.crawler._load_proxy_config_cls", lambda: _FakeProxyConfig)
    crawler = _crawler(proxies=["http://p:8080"], proxy_on_initial=True)
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_run_config(fake_run_config_cls)
    assert "proxy_config" in captured


def test_every_retry_round_uses_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _proxy_crawler(monkeypatch, proxies=["http://p:8080"], max_retries=3)

    for round_num in (2, 3, 4):
        assert "proxy_config" in _captured_fallback_run_config(crawler, round_num), round_num


def test_initial_crawl_uses_no_proxy_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = _proxy_crawler(monkeypatch, proxies=["http://p:8080"])
    captured: dict = {}

    def fake_run_config_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    crawler._build_run_config(fake_run_config_cls)
    assert "proxy_config" not in captured


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


def test_undetected_launch_failure_falls_back_to_standard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the undetected retry browser can't start, retries use the standard browser."""
    blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 1</body></html>"
    blocked = _make_mock_result("https://example.com/p", blocked_html, "blocked")
    fixed = _make_mock_result("https://example.com/p", "<p>ok</p>", "ok")
    calls = {"n": 0}

    async def mock_arun(url, config):
        calls["n"] += 1
        return blocked if calls["n"] == 1 else fixed

    def make_instance(*, launch_fails: bool) -> AsyncMock:
        inst = AsyncMock()
        inst.arun = mock_arun
        inst.__aexit__ = AsyncMock(return_value=False)
        if launch_fails:
            inst.__aenter__ = AsyncMock(
                side_effect=RuntimeError("BrowserType.launch: Executable doesn't exist")
            )
        else:
            inst.__aenter__ = AsyncMock(return_value=inst)
        return inst

    crawler_kwargs: list[dict] = []

    def factory(**kwargs):
        crawler_kwargs.append(kwargs)
        return make_instance(launch_fails="crawler_strategy" in kwargs)

    sentinel = object()
    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", factory)
    monkeypatch.setattr(SiteCrawler, "_build_undetected_strategy", lambda self, cfg: sentinel)

    crawler = SiteCrawler(
        CrawlerConfig(urls=["https://example.com/p"], limit=10, max_retries=1),
        output_base=tmp_path,
    )
    emitted: list = []
    crawler._emit_crawl_warning = lambda message: emitted.append(message)
    results = crawler.crawl()

    # Three opens: round 1 (standard), retry (undetected, fails), retry fallback (standard).
    assert len(crawler_kwargs) == 3
    assert "crawler_strategy" not in crawler_kwargs[0]
    assert crawler_kwargs[1]["crawler_strategy"] is sentinel
    assert "crawler_strategy" not in crawler_kwargs[2]
    # The retried page recovered on the standard-browser fallback.
    assert any(r.success for r in results)
    # A launch-failure warning was surfaced to the UI.
    assert any(m.code == messages.CODE_UNDETECTED_LAUNCH_FAILED for m in emitted)


def test_undetected_retry_toggle_off_uses_standard_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With undetected_retry=False, retry rounds reuse the standard browser and never build
    the undetected strategy."""
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

    build_calls = {"n": 0}

    def fake_build(self, cfg):
        build_calls["n"] += 1
        return object()

    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", factory)
    monkeypatch.setattr(SiteCrawler, "_build_undetected_strategy", fake_build)

    crawler = SiteCrawler(
        CrawlerConfig(
            urls=["https://example.com/p"], limit=10, max_retries=1, undetected_retry=False
        ),
        output_base=tmp_path,
    )
    crawler.crawl()

    # Both rounds opened the standard browser; the undetected strategy was never built.
    assert len(crawler_kwargs) == 2
    assert all("crawler_strategy" not in kw for kw in crawler_kwargs)
    assert build_calls["n"] == 0


def test_memoization_defers_blocked_domain_and_spares_other_domains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A domain blocked in round 1 has its remaining URLs deferred to the undetected retry
    (never re-fetched with the standard browser); other domains are untouched."""
    blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 1</body></html>"
    standard_urls: list[str] = []
    undetected_urls: list[str] = []

    async def standard_arun(url, config):
        standard_urls.append(url)
        if "other.com" in url:
            return _make_mock_result(url, "<p>fine</p>", "fine content here")
        return _make_mock_result(url, blocked_html, "blocked")

    async def undetected_arun(url, config):
        undetected_urls.append(url)
        return _make_mock_result(url, "<p>ok</p>", "recovered content")

    def make_instance(arun):
        inst = AsyncMock()
        inst.arun = arun
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)
        return inst

    def factory(**kwargs):
        return make_instance(undetected_arun if "crawler_strategy" in kwargs else standard_arun)

    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", factory)
    monkeypatch.setattr(SiteCrawler, "_build_undetected_strategy", lambda self, cfg: object())

    config = CrawlerConfig(
        urls=["https://example.com/a", "https://example.com/b", "https://other.com/c"],
        limit=10,
        max_depth=1,
        max_concurrent=1,
        max_retries=1,
        undetected_retry=True,
    )
    SiteCrawler(config, output_base=tmp_path).crawl()

    # Round 1 (standard): /a fetched + blocked -> example.com flagged; /b deferred (never
    # fetched on the standard browser); /c on another domain still fetched normally.
    assert standard_urls == ["https://example.com/a", "https://other.com/c"]
    # Round 2 (undetected): both example.com URLs retried.
    assert set(undetected_urls) == {"https://example.com/a", "https://example.com/b"}


def test_memoization_inactive_when_toggle_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With undetected_retry=False memoization is disabled, so a same-domain block does not
    defer the remaining URLs — every URL still gets its round-1 standard attempt."""
    blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 1</body></html>"
    standard_urls: list[str] = []

    async def standard_arun(url, config):
        standard_urls.append(url)
        return _make_mock_result(url, blocked_html, "blocked")

    inst = AsyncMock()
    inst.arun = standard_arun
    inst.__aenter__ = AsyncMock(return_value=inst)
    inst.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", lambda **kw: inst)

    config = CrawlerConfig(
        urls=["https://example.com/a", "https://example.com/b"],
        limit=10,
        max_depth=1,
        max_concurrent=1,
        undetected_retry=False,
    )
    SiteCrawler(config, output_base=tmp_path).crawl()

    # Round 1 fetched both same-domain URLs; /b was not deferred because memoization is off.
    assert standard_urls[:2] == ["https://example.com/a", "https://example.com/b"]


def test_memoization_deferred_failure_is_recorded_as_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A deferred URL that never recovers surfaces a clean WAF-block (CODE_BLOCKED), not the
    raw ``_DeferToUndetectedError`` name, in the diagnostics."""
    blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 1</body></html>"

    async def always_blocked(url, config):
        return _make_mock_result(url, blocked_html, "blocked")

    inst = AsyncMock()
    inst.arun = always_blocked
    inst.__aenter__ = AsyncMock(return_value=inst)
    inst.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("crawl4md.crawler.AsyncWebCrawler", lambda **kw: inst)
    monkeypatch.setattr(SiteCrawler, "_build_undetected_strategy", lambda self, cfg: object())

    config = CrawlerConfig(
        urls=["https://example.com/a", "https://example.com/b"],
        limit=10,
        max_depth=1,
        max_concurrent=1,
        undetected_retry=True,
    )
    results = SiteCrawler(config, output_base=tmp_path).crawl()

    deferred = next(r for r in results if r.url == "https://example.com/b")
    assert deferred.error_code == messages.CODE_BLOCKED
    assert "_DeferToUndetectedError" not in (deferred.error or "")
