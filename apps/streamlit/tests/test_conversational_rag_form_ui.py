from __future__ import annotations

from unittest.mock import MagicMock

from rag_engine import ConversationalAnswer, StageTokenUsage, TokenUsage, ValidatedFollowup
from rag_engine import messages as rag_messages
from rag_engine.messages import CODE_FOLLOWUPS_NONE_VALID, CODE_RERANK_UNAVAILABLE

import app_support.conversational_rag.conversational_rag_form_ui as form_ui
from app_support.conversational_rag.conversational_rag_form_ui import (
    ConversationalControls,
    _prompt_tab_visible,
    aux_model_choices,
    build_conversational_config,
)
from app_support.i18n import STRINGS_EN


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


def test_prompt_tab_visible_follows_toggles() -> None:
    # A stage's prompt tab shows only when the feature that runs it is enabled.
    def visible(key: str, **overrides: object) -> bool:
        opts = {"decomposition": True, "followups": True, "reranker": "llm"}
        opts.update(overrides)
        return _prompt_tab_visible(key, **opts)  # type: ignore[arg-type]

    assert visible("answer") and visible("state")  # always shown
    assert visible("decompose") and not visible("decompose", decomposition=False)
    assert visible("followups") and not visible("followups", followups=False)
    assert visible("answerability") and not visible("answerability", followups=False)
    assert visible("rerank")  # LLM re-ranker → its prompt is used
    assert not visible("rerank", reranker="local") and not visible("rerank", reranker="off")


def test_inspect_note_returns_localized_text_for_matching_code() -> None:
    warnings = [rag_messages.rerank_unavailable("llm", "unparsable ranking")]

    note = form_ui._inspect_note(STRINGS_EN, warnings, CODE_RERANK_UNAVAILABLE)

    assert isinstance(note, str) and note  # the relocated warning is localized
    # A code with no matching warning yields nothing to show in that tab.
    assert form_ui._inspect_note(STRINGS_EN, warnings, CODE_FOLLOWUPS_NONE_VALID) is None


def test_compact_tokens_shortens_thousands() -> None:
    assert form_ui._compact_tokens(320) == "320"
    assert form_ui._compact_tokens(1400) == "1.4k"


def test_stage_tokens_sums_and_folds_answerability() -> None:
    usage = [
        StageTokenUsage("answer", "main", TokenUsage(500, 900, 1400)),
        StageTokenUsage("decomposition", "aux", TokenUsage(10, 10, 20)),
        StageTokenUsage("followups", "aux", TokenUsage(30, 30, 60)),
        StageTokenUsage("answerability", "aux", TokenUsage(40, 40, 80)),
    ]

    totals = form_ui._stage_tokens(usage)

    # Mapped to display-stage keys; the answerability probe folds into follow-ups (60 + 80).
    assert totals == {"answer": 1400, "plan": 20, "followups": 140}


def test_render_followup_bubble_lays_out_suggestions_inline(monkeypatch, tmp_path) -> None:
    # The suggestions are wrapped in a horizontal container so they flow inline
    # like a sentence (a wrapping row) instead of stacking vertically.
    fake_st = MagicMock()
    fake_st.button.return_value = False
    monkeypatch.setattr(form_ui, "st", fake_st)

    strings = {
        "CONV_FOLLOWUP_INTRO_DEFAULT": "Want to explore further?",
        "CONV_NO_FOLLOWUPS_DEFAULT": "No suggestions this time.",
    }
    follow_ups = [
        ValidatedFollowup(question="How does X work?"),
        ValidatedFollowup(question="Why Y?"),
    ]

    clicked = form_ui.render_followup_bubble(strings, tmp_path, follow_ups, 0)

    assert clicked is None  # nothing clicked
    assert fake_st.button.call_count == 2  # one clickable link per suggestion
    assert any(
        call.kwargs.get("horizontal") is True for call in fake_st.container.call_args_list
    )  # suggestions flow inline inside a horizontal container


def test_render_diagnostics_surfaces_all_messages(monkeypatch) -> None:
    # Every warning and error moves to the Inspect Diagnostics tab, so none is lost
    # when they are kept out of the chat bubble.
    fake_st = MagicMock()
    monkeypatch.setattr(form_ui, "st", fake_st)
    answer = ConversationalAnswer(
        answer="",
        warnings=[rag_messages.no_context(), rag_messages.plan_unparsable()],
        errors=[rag_messages.retrieval_failed("ssl boom")],
    )

    form_ui._render_diagnostics(STRINGS_EN, answer)

    assert fake_st.warning.call_count == 2  # both warnings shown
    assert fake_st.error.call_count == 1  # the error shown
    fake_st.caption.assert_not_called()


def test_render_diagnostics_notes_a_clean_turn(monkeypatch) -> None:
    fake_st = MagicMock()
    monkeypatch.setattr(form_ui, "st", fake_st)

    form_ui._render_diagnostics(STRINGS_EN, ConversationalAnswer(answer="ok"))

    fake_st.caption.assert_called_once()  # a clean turn shows the empty-state note
    fake_st.warning.assert_not_called()
    fake_st.error.assert_not_called()
