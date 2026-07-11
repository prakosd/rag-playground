"""Static catalog of the chat models offered for answering questions.

Like the embedding catalog in ``vector_indexer``, this lets a UI discover the
available chat models — their provider, whether they run offline, and whether
they need credentials — without constructing a model or touching the network.
``provider`` is the ``model_provider`` value passed to ``init_chat_model``
(``"echo"`` is the offline built-in handled separately).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CHAT_MODEL_OPTIONS",
    "DEFAULT_CHAT_MODEL",
    "ECHO_MODEL",
    "ECHO_PROVIDER",
    "ChatModelInfo",
    "get_chat_model_info",
]

ModelKind = Literal["local", "cloud"]
ModelSize = Literal["small", "medium", "large"]

# The offline built-in. It generates no real answer; it echoes the question so
# the workflow runs end-to-end without credentials and serves as the universal
# fallback when a requested cloud model is unavailable.
ECHO_MODEL = "echo"
ECHO_PROVIDER = "echo"


@dataclass(frozen=True)
class ChatModelInfo:
    """Describes a chat model for display and resolution."""

    model_id: str
    provider: str
    label: str
    size: ModelSize
    kind: ModelKind
    requires_api_key: bool


CHAT_MODEL_OPTIONS: tuple[ChatModelInfo, ...] = (
    ChatModelInfo(
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        provider="bedrock_converse",
        label="Claude 3.5 Sonnet (Bedrock)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="amazon.nova-lite-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Lite (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4o-mini",
        provider="openai",
        label="GPT-4o mini (OpenAI)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4o",
        provider="openai",
        label="GPT-4o (OpenAI)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    # ── Curated Bedrock models for ap-southeast-2 (Sydney) ──────────────────────
    # Nova and Claude use the `apac.` cross-Region inference-profile IDs required in
    # that Region; Qwen3 is offered in-Region so it uses the plain model IDs (no geo
    # prefix). Exact IDs and per-account model access must be confirmed on each model
    # card in the AWS console (Model access); the app's *offered* subset and default
    # are chosen in .env.defaults (RAG_LLM_MODELS / RAG_DEFAULT_LLM_MODEL).
    ChatModelInfo(
        model_id="apac.amazon.nova-micro-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Micro (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.amazon.nova-lite-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Lite (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.amazon.nova-pro-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Pro (Bedrock · APAC)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.anthropic.claude-haiku-4-5-20251001-v1:0",
        provider="bedrock_converse",
        label="Claude Haiku 4.5 (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
        provider="bedrock_converse",
        label="Claude Sonnet 4.5 (Bedrock · APAC)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    # Qwen3 (in-Region in ap-southeast-2; plain model IDs, no geo prefix). Reasoning
    # ("thinking") is suppressed via thinking_disabled_model_kwargs in rag_engine.llm.
    ChatModelInfo(
        model_id="qwen.qwen3-32b-v1:0",
        provider="bedrock_converse",
        label="Qwen3 32B (Bedrock)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-next-80b-a3b-v1:0",
        provider="bedrock_converse",
        label="Qwen3 Next 80B A3B (Bedrock)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-235b-a22b-2507-v1:0",
        provider="bedrock_converse",
        label="Qwen3 235B A22B 2507 (Bedrock)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id=ECHO_MODEL,
        provider=ECHO_PROVIDER,
        label="Echo (offline, no answer generation)",
        size="small",
        kind="local",
        requires_api_key=False,
    ),
)

# Default targets AWS Bedrock (matching the default Titan embeddings); without
# credentials, resolution falls back to the offline echo model with a warning.
DEFAULT_CHAT_MODEL = CHAT_MODEL_OPTIONS[0].model_id

_INFO_BY_ID = {info.model_id: info for info in CHAT_MODEL_OPTIONS}


def get_chat_model_info(model_id: str) -> ChatModelInfo | None:
    """Return metadata for *model_id*, or ``None`` when it is not catalogued."""
    return _INFO_BY_ID.get(model_id.strip())
