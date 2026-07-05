from __future__ import annotations

import crawl4md_streamlit.focus as focus_module
from crawl4md_streamlit.focus import click_widget, focus_widget


def test_focus_widget_targets_keyed_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_iframe(src: str, **kwargs: object) -> None:
        captured["html"] = src
        captured["kwargs"] = kwargs

    monkeypatch.setattr(focus_module.st, "iframe", fake_iframe)

    focus_widget("semantic_search_query")

    assert ".st-key-semantic_search_query input" in captured["html"]
    assert ".st-key-semantic_search_query textarea" in captured["html"]
    assert captured["kwargs"]["height"] == 1


def test_click_widget_targets_keyed_button(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_iframe(src: str, **kwargs: object) -> None:
        captured["html"] = src
        captured["kwargs"] = kwargs

    monkeypatch.setattr(focus_module.st, "iframe", fake_iframe)

    click_widget("export_download_crawl_01_river")

    assert ".st-key-export_download_crawl_01_river button" in captured["html"]
    assert "target.click()" in captured["html"]
    assert captured["kwargs"]["height"] == 1
