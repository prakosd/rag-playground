"""Embedding resolution value object and shared error type.

The embedding interface itself is LangChain's ``Embeddings``; concrete builders
live in sibling modules and import their heavy or credentialed dependencies
lazily so that importing this package never requires ChromaDB, langchain-aws,
langchain-openai, or network access. This module only defines the lightweight
value object that pairs a ready embeddings client with its resolved identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["EmbeddingProviderUnavailable", "ResolvedEmbedding"]


class EmbeddingProviderUnavailable(RuntimeError):
    """Raised when a requested embedding model cannot be used.

    Typical causes are a missing optional dependency (for example langchain-aws
    for Amazon Titan) or absent credentials/configuration. Callers decide whether
    to fail or fall back to an offline default.
    """


@dataclass(frozen=True)
class ResolvedEmbedding:
    """A ready LangChain embeddings client paired with its resolved identity.

    ``embeddings`` is the object handed to the vector store; ``model_id`` and
    ``dimension`` describe what was actually resolved (after any fallback) so the
    indexer can record them in the run manifest and the retrieval layer can
    reopen the matching index.
    """

    embeddings: Embeddings
    model_id: str
    dimension: int
