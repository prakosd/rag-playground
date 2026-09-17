from __future__ import annotations

from app_support.conversational_rag.conversational_rag_form_ui import (
    ConversationalControls,
    aux_model_choices,
    build_conversational_config,
)


def _controls(**overrides) -> ConversationalControls:
    values = dict(
        index=None,
        answer_model="gpt-4o",
        top_k=6,
        tone="Formal",
        reranker="llm",
        aux_model_id="echo",
        decomposition=False,
        followups=True,
        inspect=True,
        followup_drop=0.3,
        followup_keep=0.7,
    )
    values.update(overrides)
    return ConversationalControls(**values)


def test_build_config_maps_controls() -> None:
    config = build_conversational_config(_controls())

    assert config.rag.llm_model == "gpt-4o"
    assert config.rag.top_k == 6
    assert config.reranker == "llm"
    assert config.aux_model_id == "echo"
    assert config.plan_enabled is False
    assert config.followups_enabled is True
    assert config.followup_drop_score == 0.3
    assert config.followup_min_score == 0.7
    assert config.tone == "Formal"


def test_build_config_blank_aux_becomes_none() -> None:
    config = build_conversational_config(_controls(aux_model_id=""))

    assert config.aux_model_id is None


def test_build_config_threads_language() -> None:
    assert build_conversational_config(_controls()).language == "English"
    assert build_conversational_config(_controls(), language="Indonesian").language == "Indonesian"


def test_aux_model_choices_offers_only_small_priced_models() -> None:
    # Only genuinely small helper models (micro / mini / lite) are offered as the
    # auxiliary model; larger or unpriced models (e.g. Claude Haiku) are dropped.
    from app_support.model_pricing import get_model_price

    options, default_index = aux_model_choices()

    assert options
    assert 0 <= default_index < len(options)
    for model_id in options:
        price = get_model_price(model_id)
        assert price is not None, model_id  # unpriced models are filtered out
        assert price.size_band in {"XS", "Small"}, (model_id, price.size_band)
    assert "apac.amazon.nova-micro-v1:0" in options  # the pre-selected micro model
    assert "google.gemma-3-4b-it" in options  # a cheap cross-provider (Google) helper
    # Claude Haiku is not a micro/mini/lite model and must not be offered here.
    assert "apac.anthropic.claude-haiku-4-5-20251001-v1:0" not in options


def test_build_config_populates_prompt_overrides() -> None:
    # With no session, the six prompts resolve from the shipped config files.
    config = build_conversational_config(_controls())

    for key in ("answer", "decompose", "rerank", "followups", "answerability", "state"):
        assert getattr(config.prompts, key)
