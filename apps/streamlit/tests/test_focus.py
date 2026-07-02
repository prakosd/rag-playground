from __future__ import annotations

import crawl4md_streamlit.focus as focus_module
from crawl4md_streamlit.focus import focus_widget


def test_focus_widget_targets_keyed_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_html(html: str, **kwargs: object) -> None:
        captured["html"] = html
        captured["kwargs"] = kwargs

    monkeypatch.setattr(focus_module.components, "html", fake_html)

    focus_widget("semantic_search_query")

    assert ".st-key-semantic_search_query input" in captured["html"]
    assert ".st-key-semantic_search_query textarea" in captured["html"]
    assert captured["kwargs"]["height"] == 0
