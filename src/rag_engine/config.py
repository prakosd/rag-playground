"""Configuration model for a retrieval-augmented generation request.

``RagConfig`` captures the user-tunable knobs for answering a question over an
index: which chat model to use, how many chunks to retrieve, and the generation
parameters. It is UI-independent and validated with Pydantic v2.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from rag_engine.catalog import DEFAULT_CHAT_MODEL

__all__ = ["RagConfig"]

_DEFAULT_TEMPERATURE = 0.0
_MAX_TEMPERATURE = 2.0
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TOP_K = 4


class RagConfig(BaseModel):
    """User-supplied parameters that control retrieval and generation."""

    llm_model: str = DEFAULT_CHAT_MODEL
    temperature: float = _DEFAULT_TEMPERATURE
    max_tokens: int = _DEFAULT_MAX_TOKENS
    top_k: int = _DEFAULT_TOP_K

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= _MAX_TEMPERATURE:
            raise ValueError(f"temperature must be between 0 and {_MAX_TEMPERATURE}.")
        return value

    @field_validator("max_tokens", "top_k")
    @classmethod
    def _require_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be at least 1.")
        return value
