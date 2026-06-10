"""Amazon Titan text embeddings via Amazon Bedrock.

Credentials are read from the standard AWS environment variables (for example
``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, ``AWS_REGION``). When boto3 is
not installed or credentials are absent, construction raises
``EmbeddingProviderUnavailable`` so callers can fall back gracefully.
"""

from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Sequence
from typing import Any

from vector_indexer.embeddings.base import EmbeddingProvider, EmbeddingProviderUnavailable

__all__ = ["TITAN_MODEL", "TitanEmbeddingProvider"]

TITAN_MODEL = "amazon.titan-embed-text-v2:0"
_BEDROCK_SERVICE = "bedrock-runtime"
_SUPPORTED_DIMENSIONS = (256, 512, 1024)
_DEFAULT_DIMENSION = 512


def _has_aws_credentials() -> bool:
    if os.environ.get("AWS_PROFILE"):
        return True
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))


class TitanEmbeddingProvider(EmbeddingProvider):
    """Embeds text with the Amazon Titan v2 model through Bedrock."""

    def __init__(self, *, dimension: int | None = None, region: str | None = None) -> None:
        if importlib.util.find_spec("boto3") is None:
            raise EmbeddingProviderUnavailable(
                "boto3 is required for Amazon Titan embeddings; install the [bedrock] extra."
            )
        if not _has_aws_credentials():
            raise EmbeddingProviderUnavailable(
                "AWS credentials are not configured for Amazon Titan embeddings."
            )
        self._region = (
            region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        )
        self._dimension = dimension if dimension in _SUPPORTED_DIMENSIONS else _DEFAULT_DIMENSION
        self._client: Any = None

    @property
    def model_id(self) -> str:
        return TITAN_MODEL

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._ensure_client()
        vectors: list[list[float]] = []
        for text in texts:
            body = json.dumps({"inputText": text, "dimensions": self._dimension, "normalize": True})
            response = client.invoke_model(
                modelId=TITAN_MODEL,
                body=body,
                accept="application/json",
                contentType="application/json",
            )
            payload = json.loads(response["body"].read())
            vectors.append([float(value) for value in payload["embedding"]])
        return vectors

    def _ensure_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client(_BEDROCK_SERVICE, region_name=self._region)
        return self._client
