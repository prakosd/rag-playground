"""Tests for the app-layer RAG resource cache (searcher + chat/aux resolvers).

The ``st.cache_resource`` seams (``_open_cached_searcher`` / ``_cached_resolved_chat``)
are monkeypatched so these exercise the wrapper logic — injection, graceful
fallback, and resolver threading — without a Streamlit runtime or any network.
"""

from __future__ import annotations

import pytest

from app_support.rag_shared import resource_cache as rc


class _Sentinel:
    pass


def test_cached_retriever_injects_cached_searcher(monkeypatch: pytest.MonkeyPatch) -> None:
    searcher = _Sentinel()
    monkeypatch.setattr(rc, "_open_cached_searcher", lambda run_dir_str: searcher)
    captured: dict = {}

    def fake_retrieve(run_dir, query, config, **kwargs):
        captured.update(run_dir=run_dir, query=query, kwargs=kwargs)
        return "RESULT"

    monkeypatch.setattr(rc, "retrieve", fake_retrieve)

    assert rc.cached_retriever("/idx", "q", "cfg") == "RESULT"
    assert captured["kwargs"]["searcher"] is searcher


def test_cached_retriever_falls_back_when_searcher_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(run_dir_str: str):
        raise RuntimeError("no manifest")

    monkeypatch.setattr(rc, "_open_cached_searcher", boom)
    captured: dict = {}
    monkeypatch.setattr(
        rc, "retrieve", lambda run_dir, query, config, **kwargs: captured.update(kwargs=kwargs)
    )

    rc.cached_retriever("/idx", "q", "cfg")
    # searcher=None makes the library rebuild it and re-report the real error.
    assert captured["kwargs"]["searcher"] is None


def test_cached_retriever_respects_explicit_searcher(monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = _Sentinel()
    opened = {"called": False}
    monkeypatch.setattr(rc, "_open_cached_searcher", lambda s: opened.__setitem__("called", True))
    monkeypatch.setattr(rc, "retrieve", lambda run_dir, query, config, **kwargs: kwargs)

    out = rc.cached_retriever("/idx", "q", "cfg", searcher=explicit)
    assert out["searcher"] is explicit
    assert opened["called"] is False  # an explicit searcher is never overridden


def test_cached_chat_resolver_delegates_to_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "_cached_resolved_chat", lambda m, t, mx: (f"{m}:{t}:{mx}", []))
    resolved, warnings = rc.cached_chat_resolver("gpt", temperature=0.5, max_tokens=42)
    assert resolved == "gpt:0.5:42"
    assert warnings == []


def test_cached_aux_resolver_threads_cached_chat_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_aux(config, *, resolver):
        captured.update(config=config, resolver=resolver)
        return ("aux", [])

    monkeypatch.setattr(rc, "resolve_auxiliary_model", fake_aux)

    assert rc.cached_aux_resolver("CFG") == ("aux", [])
    assert captured["config"] == "CFG"
    assert captured["resolver"] is rc.cached_chat_resolver


def test_cached_retriever_offloads_to_backend_when_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(rc, "get_settings", lambda: SimpleNamespace(backend_mode="http"))
    seen: dict = {}

    def fake_http(run_dir, query, config):
        seen.update(run_dir=run_dir, query=query)
        return "HTTP_RESULT"

    monkeypatch.setattr(rc, "http_search", fake_http)

    def no_local(*args, **kwargs):
        raise AssertionError("local retrieve must not run in http mode")

    monkeypatch.setattr(rc, "retrieve", no_local)

    assert rc.cached_retriever("/idx", "q", "cfg") == "HTTP_RESULT"
    assert seen["query"] == "q"  # request offloaded to the backend client
