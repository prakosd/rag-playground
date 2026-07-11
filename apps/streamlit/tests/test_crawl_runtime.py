from __future__ import annotations

import pytest

from app_support.crawl import crawl_runtime


# Risk: the browser bootstrap must stay a no-op off Streamlit Cloud so local/CI runs
# never shell out to `playwright install`. Type: unit.
def test_ensure_playwright_browser_skips_off_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(crawl_runtime, "_browser_ready", False)
    monkeypatch.setattr(crawl_runtime, "_on_streamlit_cloud", lambda: False)
    monkeypatch.setattr(crawl_runtime, "_run_install", lambda: calls.append("install"))

    crawl_runtime.ensure_playwright_browser()

    assert calls == []


# Risk: on Streamlit Cloud the browser must be installed exactly once per process.
# Type: unit.
def test_ensure_playwright_browser_installs_once_on_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(crawl_runtime, "_browser_ready", False)
    monkeypatch.setattr(crawl_runtime, "_on_streamlit_cloud", lambda: True)
    monkeypatch.setattr(crawl_runtime, "_run_install", lambda: calls.append("install"))

    crawl_runtime.ensure_playwright_browser()
    crawl_runtime.ensure_playwright_browser()

    assert calls == ["install"]
