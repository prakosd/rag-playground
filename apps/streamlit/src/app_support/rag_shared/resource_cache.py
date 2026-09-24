"""App-layer caching of the heavy RAG clients (chat/aux models + vector searcher).

The pure libraries build a fresh client on every call by design — that keeps them
stateless and offline-testable. Here, in the app, we memoize the resolved clients
with ``st.cache_resource`` and feed them back through ``rag_engine``'s existing
injection hooks (``chat_resolver=`` / ``aux_resolver=`` / ``retriever=``). A long
chat session then reuses one client per (model, index) instead of rebuilding a
chat model and re-opening the Chroma store on every turn, while the library keeps
its UI-agnostic, no-cache contract untouched.

Cache scope is the process (shared across sessions); the cached clients are
read-only network/DB handles, and credentials live in process-level environment
variables, so sharing them across sessions is safe. Model/index changes key a new
entry (a rebuilt index gets a new timestamped ``run_dir``); ``.env`` credential
changes need an app restart, which already clears these caches.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import streamlit as st
from rag_engine import (
    VectorSearcher,
    open_searcher,
    resolve_auxiliary_model,
    resolve_chat_model,
    retrieve,
)
from rag_engine.retrieval import load_index_embeddings

from app_support.backend_client import http_search
from app_support.settings import get_settings

if TYPE_CHECKING:
    from artifact_store import LibraryMessage
    from rag_engine import ResolvedChatModel
    from rag_engine.retrieval import RetrievalResult

__all__ = ["cached_aux_resolver", "cached_chat_resolver", "cached_retriever"]


@st.cache_resource(show_spinner=False)
def _cached_resolved_chat(
    model_id: str, temperature: float, max_tokens: int
) -> tuple[ResolvedChatModel, list[LibraryMessage]]:
    """Resolve (and cache) one chat model per (model, temperature, max_tokens)."""
    return resolve_chat_model(model_id, temperature=temperature, max_tokens=max_tokens)


def cached_chat_resolver(
    model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024
) -> tuple[ResolvedChatModel, list[LibraryMessage]]:
    """A ``chat_resolver`` that reuses cached clients (echo fallback + warnings intact)."""
    return _cached_resolved_chat(model_id, temperature, max_tokens)


def cached_aux_resolver(config: Any) -> tuple[ResolvedChatModel, list[LibraryMessage]]:
    """An ``aux_resolver`` whose selected helper model is served from the shared cache."""
    return resolve_auxiliary_model(config, resolver=cached_chat_resolver)


@st.cache_resource(show_spinner=False)
def _open_cached_searcher(run_dir_str: str) -> VectorSearcher:
    """Open and warm one searcher per index directory; reused across turns/queries."""
    resolved_emb, _warnings = load_index_embeddings(run_dir_str)
    searcher = open_searcher(Path(run_dir_str), resolved_emb.embeddings)
    searcher.ensure_ready()
    return searcher


def cached_retriever(
    run_dir: Path | str, query: str, config: Any, **kwargs: Any
) -> RetrievalResult:
    """``retrieve`` reusing a cached searcher; on failure the library rebuilds + reports.

    When ``BACKEND_MODE=http`` the retrieval is offloaded to the FastAPI backend
    instead of opening the index locally; the in-process default is unchanged.
    """
    if get_settings().backend_mode == "http":
        return http_search(run_dir, query, config)
    if kwargs.get("searcher") is None:
        try:
            kwargs["searcher"] = _open_cached_searcher(str(run_dir))
        except Exception:  # noqa: BLE001 - missing manifest/provider → retrieve re-reports
            kwargs["searcher"] = None
    return retrieve(run_dir, query, config, **kwargs)
