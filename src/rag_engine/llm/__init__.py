"""Chat model registry and resolution policy.

``build_chat_model`` maps a catalogued model id to a concrete LangChain
``BaseChatModel`` via ``init_chat_model`` (the umbrella ``langchain`` package),
gating on the provider package and credentials *before* construction so the
offline path never touches the network. ``resolve_chat_model`` applies a
universal echo fallback so the offline path still produces output.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artifact_store import LibraryMessage
from rag_engine import messages
from rag_engine.catalog import ECHO_MODEL, ECHO_PROVIDER, get_chat_model_info
from rag_engine.llm.echo import build_echo_chat_model

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "ChatModelUnavailable",
    "ResolvedChatModel",
    "build_chat_model",
    "build_echo_chat_model",
    "resolve_chat_model",
]

_BEDROCK_PROVIDER = "bedrock_converse"
_OPENAI_PROVIDER = "openai"


class ChatModelUnavailable(RuntimeError):
    """Raised when a requested chat model cannot be used.

    Typical causes are a missing provider package (langchain-aws / langchain-openai)
    or absent credentials. Callers decide whether to fail or fall back to echo.
    """


@dataclass(frozen=True)
class ResolvedChatModel:
    """A ready LangChain chat model paired with its resolved identity."""

    model: BaseChatModel
    model_id: str


def _has_aws_credentials() -> bool:
    if os.environ.get("AWS_PROFILE"):
        return True
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))


def build_chat_model(
    model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024
) -> BaseChatModel:
    """Return a chat model for *model_id*, or raise ``ChatModelUnavailable``."""
    info = get_chat_model_info(model_id)
    if info is None:
        raise ChatModelUnavailable(f"Unknown chat model {model_id!r}.")
    if info.provider == ECHO_PROVIDER:
        return build_echo_chat_model()
    if info.provider == _BEDROCK_PROVIDER:
        if importlib.util.find_spec("langchain_aws") is None:
            raise ChatModelUnavailable(
                "langchain-aws is required for Bedrock chat models; install the [bedrock] extra."
            )
        if not _has_aws_credentials():
            raise ChatModelUnavailable(
                "AWS credentials are not configured for Bedrock chat models."
            )
    elif info.provider == _OPENAI_PROVIDER:
        if importlib.util.find_spec("langchain_openai") is None:
            raise ChatModelUnavailable(
                "langchain-openai is required for OpenAI chat models; install the [openai] extra."
            )
        if not os.environ.get("OPENAI_API_KEY"):
            raise ChatModelUnavailable("OPENAI_API_KEY is not configured for OpenAI chat models.")
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise ChatModelUnavailable(
            "langchain is required for chat models; install the [rag] extra."
        ) from exc
    return init_chat_model(
        info.model_id,
        model_provider=info.provider,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def resolve_chat_model(
    model_id: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    build: Callable[..., BaseChatModel] = build_chat_model,
    echo_build: Callable[[], BaseChatModel] = build_echo_chat_model,
) -> tuple[ResolvedChatModel, list[LibraryMessage]]:
    """Resolve a chat model, falling back to the offline echo model.

    When the requested model is unavailable (missing provider package or
    credentials), this falls back to echo and returns a warning so the request
    still produces output. It raises ``ChatModelUnavailable`` only when echo
    itself was requested and is unavailable.
    """
    warnings: list[LibraryMessage] = []
    try:
        model = build(model_id, temperature=temperature, max_tokens=max_tokens)
    except ChatModelUnavailable as exc:
        if model_id.strip() == ECHO_MODEL:
            raise
        model = echo_build()
        warnings.append(
            messages.model_fallback_echo(requested_model=model_id.strip(), detail=str(exc))
        )
        return ResolvedChatModel(model=model, model_id=ECHO_MODEL), warnings
    return ResolvedChatModel(model=model, model_id=model_id.strip()), warnings
