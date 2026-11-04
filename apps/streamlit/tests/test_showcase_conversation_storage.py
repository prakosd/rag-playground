"""Tests for the per-showcase conversation-id localStorage bridge."""

from __future__ import annotations

from types import SimpleNamespace

from streamlit.components import v2 as st_components_v2
from streamlit.testing.v1 import AppTest

from app_support.conversational_rag.showcase_conversation_storage import merge_conversation_ids


def test_merge_conversation_ids_dedupes_and_preserves_order() -> None:
    assert merge_conversation_ids(["aaa111", "bbb222"], ["bbb222", "ccc333"]) == [
        "aaa111",
        "bbb222",
        "ccc333",
    ]


def test_merge_conversation_ids_filters_invalid_values() -> None:
    merged = merge_conversation_ids(["ok1", "", "UPPER", 123, "a" * 40], ["valid2"])
    assert merged == ["ok1", "valid2"]


def test_merge_conversation_ids_ignores_non_list_sources() -> None:
    # A bare string must not be iterated character by character.
    assert merge_conversation_ids(None, {"x": 1}) == []
    assert merge_conversation_ids("abc123", None) == []


def _sync_script(slug: str, pending: list[str]) -> None:
    import streamlit as st

    from app_support.conversational_rag.showcase_conversation_storage import (
        sync_showcase_conversation_ids,
    )

    st.session_state["_out"] = sync_showcase_conversation_ids(slug, pending)


def test_sync_returns_pending_before_browser_hydrates() -> None:
    # Headless (no JS) mirrors the first render: the stored list is unknown, so only
    # the pending ids come back. The mount must not raise.
    at = AppTest.from_function(_sync_script, kwargs={"slug": "slug_two", "pending": ["abc123"]})
    at.run()
    assert not at.exception
    assert at.session_state["_out"] == ["abc123"]


def test_sync_merges_hydrated_ids_with_pending(monkeypatch) -> None:
    def _fake_component(*_args: object, **_kwargs: object):
        return lambda **_call: SimpleNamespace(ids=["aaa111", "bbb222"])

    monkeypatch.setattr(st_components_v2, "component", _fake_component)

    at = AppTest.from_function(_sync_script, kwargs={"slug": "slug_one", "pending": ["ccc333"]})
    at.run()
    assert not at.exception
    assert at.session_state["_out"] == ["aaa111", "bbb222", "ccc333"]
