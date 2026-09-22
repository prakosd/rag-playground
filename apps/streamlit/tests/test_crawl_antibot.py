"""Tests for the app's anti-bot escalation wiring (proxies)."""

from __future__ import annotations

import pytest

from app_support.crawl.crawl_jobs import build_configs

_VALUES: dict[str, object] = {"urls": "https://example.com"}


def test_build_configs_reads_proxies_from_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWL_PROXIES", "http://p1:8080, http://p2:8080")

    crawler_config, _, _ = build_configs(_VALUES)

    assert crawler_config.proxies == ["http://p1:8080", "http://p2:8080"]


def test_build_configs_defaults_to_no_anti_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWL_PROXIES", raising=False)

    crawler_config, _, _ = build_configs(_VALUES)

    assert crawler_config.proxies == []
