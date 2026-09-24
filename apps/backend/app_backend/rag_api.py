"""HTTP routes for the RAG read APIs (semantic search + grounded answers).

Each handler resolves the request ``run_dir`` under the configured artifacts root
(rejecting path traversal), builds a ``RagConfig`` from the optional overrides, calls
the matching ``rag_engine`` function, and serializes the dataclass result — including
``LibraryMessage`` warnings/errors via ``as_dict()`` so any client can localize by
``code``. The library reports failures in ``.errors`` rather than raising, so those
become a normal 200 payload; only a bad request path is a 4xx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from artifact_store import ensure_within_root
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from rag_engine import RagConfig, RetrievedChunk, answer_question, retrieve

from app_backend.config import get_backend_settings

router = APIRouter(prefix="/rag", tags=["rag"])


class SearchRequest(BaseModel):
    run_dir: str
    query: str
    top_k: int | None = None
    score_threshold: float | None = None
    search_type: Literal["similarity", "mmr"] | None = None
    source_filter: list[str] = []


class AnswerRequest(BaseModel):
    run_dir: str
    question: str
    llm_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_k: int | None = None


def _resolve_run_dir(run_dir: str) -> Path:
    root = Path(get_backend_settings().artifacts_root).resolve()
    try:
        return ensure_within_root(root, root / run_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _config(**overrides: Any) -> RagConfig:
    return RagConfig(**{key: value for key, value in overrides.items() if value is not None})


def _chunk_dict(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "text": chunk.text,
        "source": chunk.source,
        "score": chunk.score,
        "metadata": chunk.metadata,
        "matched_queries": list(chunk.matched_queries),
    }


def _messages(items: Any) -> list[dict[str, Any]]:
    return [message.as_dict() for message in items]


@router.post("/search")
def search(request: SearchRequest) -> dict[str, Any]:
    run_path = _resolve_run_dir(request.run_dir)
    config = _config(
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        search_type=request.search_type,
        source_filter=tuple(request.source_filter) or None,
    )
    result = retrieve(run_path, request.query, config)
    return {
        "chunks": [_chunk_dict(chunk) for chunk in result.chunks],
        "warnings": _messages(result.warnings),
        "errors": _messages(result.errors),
    }


@router.post("/answer")
def answer(request: AnswerRequest) -> dict[str, Any]:
    run_path = _resolve_run_dir(request.run_dir)
    config = _config(
        llm_model=request.llm_model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_k=request.top_k,
    )
    result = answer_question(run_path, request.question, config)
    return {
        "answer": result.answer,
        "model_used": result.model_used,
        "sources": [_chunk_dict(chunk) for chunk in result.sources],
        "warnings": _messages(result.warnings),
        "errors": _messages(result.errors),
    }
