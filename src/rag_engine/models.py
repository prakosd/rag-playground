"""Plain data structures shared across the rag_engine pipeline.

These mirror the lightweight-result philosophy of ``vector_indexer``: a UI can
render an answer, its source chunks, and any structured warnings/errors without
importing LangChain or knowing how generation happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from artifact_store import LibraryMessage

__all__ = [
    "ChatTurn",
    "RagAnswer",
    "RetrievedChunk",
    "TokenUsage",
]


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by similarity search, with its provenance and score."""

    text: str
    source: str
    score: float
    metadata: dict[str, str]


@dataclass(frozen=True)
class ChatTurn:
    """One message in a conversation history (``role`` is ``user``/``assistant``)."""

    role: str
    content: str


@dataclass
class RagAnswer:
    """Structured outcome of a QA or conversational RAG request.

    ``warnings`` and ``errors`` are :class:`~artifact_store.LibraryMessage`
    objects carrying a stable ``code`` plus structured ``params``; ``str()`` of
    each yields its English ``default_text`` for UIs without localization.
    """

    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    model_used: str | None = None
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)


@dataclass(frozen=True)
class TokenUsage:
    """Token counts a chat model reported for one generation, when available.

    Any field may be ``None`` when the provider reports no usage (e.g. the
    offline echo model), so a UI can show "n/a" instead of a fabricated count.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
