"""Amazon Titan text embeddings via Amazon Bedrock (langchain-aws).

Credentials are read from the standard AWS environment variables (for example
``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, ``AWS_REGION``). When
langchain-aws is not installed or credentials are absent, the builder raises
``EmbeddingProviderUnavailable`` so callers can fall back gracefully.
"""

from __future__ import annotations

import importlib.util
import os

from vector_indexer.embeddings.base import EmbeddingProviderUnavailable, ResolvedEmbedding

__all__ = [
    "DEFAULT_DIMENSION",
    "SUPPORTED_DIMENSIONS",
    "TITAN_MODEL",
    "build_titan_embeddings",
]

TITAN_MODEL = "amazon.titan-embed-text-v2:0"
SUPPORTED_DIMENSIONS = (256, 512, 1024)
DEFAULT_DIMENSION = 512


def _has_aws_credentials() -> bool:
    if os.environ.get("AWS_PROFILE"):
        return True
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))


def build_titan_embeddings(
    *, dimension: int | None = None, region: str | None = None
) -> ResolvedEmbedding:
    """Return Amazon Titan v2 embeddings, or raise ``EmbeddingProviderUnavailable``."""
    if importlib.util.find_spec("langchain_aws") is None:
        raise EmbeddingProviderUnavailable(
            "langchain-aws is required for Amazon Titan embeddings; install the [bedrock] extra."
        )
    if not _has_aws_credentials():
        raise EmbeddingProviderUnavailable(
            "AWS credentials are not configured for Amazon Titan embeddings."
        )
    resolved_dimension = dimension if dimension in SUPPORTED_DIMENSIONS else DEFAULT_DIMENSION
    resolved_region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    from langchain_aws import BedrockEmbeddings

    embeddings = BedrockEmbeddings(
        model_id=TITAN_MODEL,
        region_name=resolved_region,
        normalize=True,
        dimensions=resolved_dimension,
    )
    return ResolvedEmbedding(
        embeddings=embeddings, model_id=TITAN_MODEL, dimension=resolved_dimension
    )
