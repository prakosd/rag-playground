from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_engine.catalog import DEFAULT_CHAT_MODEL
from rag_engine.config import RagConfig


def test_defaults_are_valid() -> None:
    config = RagConfig()

    assert config.llm_model == DEFAULT_CHAT_MODEL
    assert config.top_k >= 1
    assert config.max_tokens >= 1
    assert 0.0 <= config.temperature <= 2.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"top_k": 0},
        {"max_tokens": 0},
    ],
)
def test_invalid_values_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        RagConfig(**overrides)


def test_accepts_custom_values() -> None:
    config = RagConfig(llm_model="gpt-4o", temperature=0.7, max_tokens=256, top_k=6)

    assert config.llm_model == "gpt-4o"
    assert config.temperature == 0.7
    assert config.max_tokens == 256
    assert config.top_k == 6
