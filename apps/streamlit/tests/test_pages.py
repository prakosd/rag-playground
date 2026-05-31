from __future__ import annotations

import importlib
from pathlib import Path

from pytest import MonkeyPatch

from crawl4md_streamlit.i18n import STRINGS_EN, STRINGS_ID
from crawl4md_streamlit.pages import (
    APP_PAGE_SPECS,
    DEFAULT_PAGE_ID,
    default_page_spec,
    page_spec_by_id,
    page_spec_by_nav_label,
)

_APP_DIR = Path(__file__).resolve().parents[1]


# Risk: navigation breaks if page metadata loses ordering, ids, or placeholder links.
# Type: unit.
def test_app_page_specs_define_five_ordered_steps() -> None:
    assert [page_spec.page_id for page_spec in APP_PAGE_SPECS] == [
        "crawl",
        "vector_index",
        "semantic_search",
        "rag_qa",
        "conversational_rag",
    ]
    assert default_page_spec().page_id == DEFAULT_PAGE_ID == "crawl"


# Risk: placeholder pages can render blank content if metadata points at missing strings.
# Type: unit.
def test_placeholder_pages_have_placeholder_keys() -> None:
    placeholder_specs = [page_spec for page_spec in APP_PAGE_SPECS if page_spec.page_id != "crawl"]

    assert all(page_spec.placeholder_key for page_spec in placeholder_specs)
    for page_spec in placeholder_specs:
        assert page_spec.placeholder_key in STRINGS_EN
        assert page_spec.placeholder_key in STRINGS_ID


# Risk: navigation metadata can drift away from the actual page modules.
# Type: unit.
def test_app_page_specs_point_to_importable_modules(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(_APP_DIR))
    for page_spec in APP_PAGE_SPECS:
        module = importlib.import_module(page_spec.module_name)
        assert callable(module.render_page)


# Risk: the shared shell identifies the selected page from translated nav labels.
# Type: unit.
def test_page_spec_by_nav_label_supports_all_locales() -> None:
    for strings in (STRINGS_EN, STRINGS_ID):
        for page_spec in APP_PAGE_SPECS:
            label = strings[page_spec.nav_label_key]
            assert page_spec_by_nav_label(label, strings) == page_spec


# Risk: translated duplicate labels make selected-page lookup ambiguous.
# Type: unit.
def test_page_spec_nav_labels_are_unique_per_locale() -> None:
    for strings in (STRINGS_EN, STRINGS_ID):
        labels = [strings[page_spec.nav_label_key] for page_spec in APP_PAGE_SPECS]
        assert len(labels) == len(set(labels))


# Risk: unknown page ids or labels should not crash the app during reruns.
# Type: unit.
def test_page_spec_lookup_falls_back_to_crawl() -> None:
    assert page_spec_by_id("missing") == default_page_spec()
    assert page_spec_by_nav_label("Missing", STRINGS_EN) == default_page_spec()
