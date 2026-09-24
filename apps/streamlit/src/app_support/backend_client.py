"""Optional HTTP client to the FastAPI backend, used when ``BACKEND_MODE=http``.

The Streamlit app runs the libraries in-process by default. When an operator opts in
with ``BACKEND_MODE=http``, the shared retriever routes retrieval to the backend
service instead of opening the index locally; generation still runs in-process today
(the streaming/conversational endpoints are a later increment — see
docs/CLOUD_DEPLOYMENT.md). A failed request degrades to a structured retrieval error
so the UI shows its natural error reply rather than crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from artifact_store import LibraryMessage
from rag_engine import RagConfig, RetrievalResult, RetrievedChunk
from rag_engine import messages as rag_messages

from app_support.settings import get_settings

__all__ = ["http_search"]

_TIMEOUT_SECONDS = 60.0


def http_search(
    run_dir: Path | str, query: str, config: RagConfig, *, client: Any | None = None
) -> RetrievalResult:
    """Call the backend ``POST /rag/search`` and rebuild a ``RetrievalResult``."""
    base_url = get_settings().backend_url.rstrip("/")
    payload = {
        "run_dir": str(run_dir),
        "query": query,
        "top_k": config.top_k,
        "score_threshold": config.score_threshold,
        "search_type": config.search_type,
        "source_filter": list(config.source_filter),
    }
    poster = client or httpx
    try:
        response = poster.post(f"{base_url}/rag/search", json=payload, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return RetrievalResult(
            chunks=[_chunk(item) for item in data.get("chunks", [])],
            warnings=[_message(item) for item in data.get("warnings", [])],
            errors=[_message(item) for item in data.get("errors", [])],
        )
    except Exception as exc:  # network / HTTP / parse failure → a structured, localizable error
        detail = f"backend request failed: {exc}"
        return RetrievalResult(errors=[rag_messages.retrieval_failed(detail)])


def _chunk(data: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        text=data["text"],
        source=data["source"],
        score=data["score"],
        metadata=data.get("metadata", {}),
        matched_queries=tuple(data.get("matched_queries", ())),
    )


def _message(data: dict[str, Any]) -> LibraryMessage:
    # The backend serializes via LibraryMessage.as_dict(), whose text key is "text".
    return LibraryMessage(
        code=data["code"],
        default_text=data.get("text", ""),
        params=data.get("params", {}),
        severity=data.get("severity", "info"),
    )
