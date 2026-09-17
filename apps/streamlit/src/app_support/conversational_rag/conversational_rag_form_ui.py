"""Step 5 (Conversational RAG) controls, per-turn metadata, and inspection panels.

Rendering lives here so the page module stays thin. The pure helpers
(``aux_model_choices``, ``build_conversational_config``) are unit-tested; the
``render_*`` functions are thin Streamlit wrappers around the shared rag_shared
helpers (``render_result_cards``, ``kv_grid_html``).
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from rag_engine import (
    CHAT_MODEL_OPTIONS,
    CONVERSATIONAL_PROMPT_FIELDS,
    ConversationalAnswer,
    ConversationalConfig,
    ConversationState,
    QueryPlan,
    RagConfig,
    ValidatedFollowup,
)

from app_support.basic_rag_qa.basic_rag_qa_form_ui import tone_choices
from app_support.conversational_rag.conversational_prompts import (
    CONVERSATIONAL_PROMPT_KEYS,
    WELCOME_PROMPT_KEY,
    conversational_prompt_is_valid,
    editor_prompt_text,
    reset_conversational_prompt,
    resolve_conversational_prompts,
    resolve_welcome_message,
    save_conversational_prompt,
)
from app_support.i18n._types import Strings
from app_support.model_pricing import load_pricing_catalog
from app_support.rag_shared.index_catalog import IndexRef
from app_support.rag_shared.llm_form_ui import (
    chat_model_choices,
    chat_model_label,
    resolve_chat_model_choices,
    resolve_offered_from_pricing,
)
from app_support.rag_shared.rag_ui import kv_grid_html, render_result_cards, select_index
from app_support.settings import get_settings

__all__ = [
    "ConversationalControls",
    "aux_model_choices",
    "build_conversational_config",
    "render_advanced_controls",
    "render_followup_buttons",
    "render_turn_inspection",
    "render_turn_metadata",
]

_RERANKER_KEYS = ("off", "local", "llm")
# Panel layout mirrors Step 4's Basic RAG Q&A panel: a wide control + a compact one.
_PANEL_COLUMN_WIDTHS = (0.8, 0.2)
_MAX_TOP_K = 20
_PROMPT_EDITOR_HEIGHT = 240  # px height of each prompt-template text area
# ConversationalPrompts field name → its editor tab's i18n label key.
_PROMPT_TAB_KEYS = {
    "answer": "CONV_PROMPT_TAB_ANSWER",
    "decompose": "CONV_PROMPT_TAB_DECOMPOSE",
    "rerank": "CONV_PROMPT_TAB_RERANK",
    "followups": "CONV_PROMPT_TAB_FOLLOWUPS",
    "answerability": "CONV_PROMPT_TAB_ANSWERABILITY",
    "state": "CONV_PROMPT_TAB_STATE",
}


@dataclass(frozen=True)
class ConversationalControls:
    """The Step 5 UI choices that shape a :class:`ConversationalConfig`."""

    index: IndexRef | None
    answer_model: str
    top_k: int
    tone: str
    reranker: str
    aux_model_id: str
    decomposition: bool
    followups: bool
    inspect: bool
    followup_drop: float
    followup_keep: float


def aux_model_choices() -> tuple[list[str], int]:
    """Return the curated auxiliary-model options and the default-selected index.

    The configured list (``CONV_RAG_AUX_MODELS``) is filtered to models priced in
    the small size bands (``CONV_RAG_AUX_SIZE_BANDS``), so only genuinely small
    helper models (micro / mini / lite) are offered — larger or unpriced ids are
    dropped even if listed. Falls back to the full catalog only if that filter
    yields nothing (e.g. the pricing config is missing).
    """
    settings = get_settings()
    configured = [
        model.strip() for model in settings.conv_rag_aux_models.split(",") if model.strip()
    ]
    aux_bands = {
        band.strip() for band in settings.conv_rag_aux_size_bands.split(",") if band.strip()
    }
    catalog_ids = [info.model_id for info in CHAT_MODEL_OPTIONS]
    allowed = resolve_offered_from_pricing(load_pricing_catalog().models, aux_bands, catalog_ids)
    if not allowed:
        allowed = catalog_ids
    return resolve_chat_model_choices(configured, allowed, settings.conv_rag_default_aux_model)


def build_conversational_config(
    controls: ConversationalControls,
    session_root: Path | str | None = None,
    *,
    language: str = "English",
) -> ConversationalConfig:
    """Build the library config from the UI *controls* and deployment settings.

    Prompt overrides resolve from the session's saved edits → the shipped config
    files → the built-in library templates via ``resolve_conversational_prompts``.
    *language* is the answer language (a free-form name) threaded into the answer
    prompt so the reply matches the active UI language.
    """
    settings = get_settings()
    return ConversationalConfig(
        rag=RagConfig(llm_model=controls.answer_model, top_k=controls.top_k),
        prompts=resolve_conversational_prompts(session_root),
        aux_model_id=controls.aux_model_id or None,
        plan_enabled=controls.decomposition,
        reranker=controls.reranker,
        rerank_top_n=settings.conv_rag_rerank_top_n,
        followups_enabled=controls.followups,
        followup_show_count=settings.conv_rag_followup_show_count,
        followup_min_score=controls.followup_keep,
        followup_drop_score=controls.followup_drop,
        tone=controls.tone,
        language=language,
    )


def render_advanced_controls(
    strings: Strings, key_prefix: str, indexes: Sequence[IndexRef], session_root: Path
) -> ConversationalControls:
    """Render the index / chunks / model / tone panel and the advanced options."""
    settings = get_settings()
    model_options, model_default = chat_model_choices()
    tones, tone_default = tone_choices()
    with st.container(border=True):
        index_col, chunks_col = st.columns(_PANEL_COLUMN_WIDTHS, vertical_alignment="center")
        with index_col:
            index = select_index(strings, indexes, key=f"{key_prefix}_index")
        disabled = index is None
        with chunks_col:
            top_k = int(
                st.number_input(
                    strings["RAG_TOP_K_LABEL"],
                    min_value=1,
                    max_value=_MAX_TOP_K,
                    value=settings.rag_top_k,
                    step=1,
                    help=strings["RAG_TOP_K_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_top_k",
                )
            )
        model_col, tone_col = st.columns(_PANEL_COLUMN_WIDTHS)
        with model_col:
            answer_model = st.selectbox(
                strings["RAG_LLM_LABEL"],
                options=model_options,
                index=model_default,
                format_func=lambda model_id: chat_model_label(model_id, strings),
                help=strings["RAG_LLM_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_llm_model",
            )
        with tone_col:
            tone = st.selectbox(
                strings["BASIC_QA_TONE_LABEL"],
                options=tones,
                index=tone_default,
                help=strings["BASIC_QA_TONE_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_tone",
            )
    with st.expander(strings["CONV_ADVANCED_LABEL"], expanded=False):
        reranker_labels = {
            "off": strings["CONV_RERANKER_OFF"],
            "local": strings["CONV_RERANKER_LOCAL"],
            "llm": strings["CONV_RERANKER_LLM"],
        }
        default_reranker = (
            settings.conv_rag_reranker if settings.conv_rag_reranker in _RERANKER_KEYS else "local"
        )
        reranker = (
            st.segmented_control(
                strings["CONV_RERANKER_LABEL"],
                options=list(_RERANKER_KEYS),
                format_func=lambda key: reranker_labels[key],
                default=default_reranker,
                help=strings["CONV_RERANKER_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_reranker",
            )
            or "off"
        )
        aux_options, aux_default = aux_model_choices()
        aux_model_id = st.selectbox(
            strings["CONV_AUX_MODEL_LABEL"],
            options=aux_options,
            index=aux_default,
            format_func=lambda model_id: chat_model_label(model_id, strings),
            help=strings["CONV_AUX_MODEL_HELP"],
            disabled=disabled,
            key=f"{key_prefix}_aux_model",
        )
        drop, keep = st.slider(
            strings["CONV_THRESHOLD_LABEL"],
            min_value=0.0,
            max_value=1.0,
            value=(settings.conv_rag_followup_drop_score, settings.conv_rag_followup_min_score),
            step=0.05,
            help=strings["CONV_THRESHOLD_HELP"],
            disabled=disabled,
            key=f"{key_prefix}_thresholds",
        )
        st.caption(strings["CONV_THRESHOLD_CAPTION"].format(drop=f"{drop:.2f}", keep=f"{keep:.2f}"))
        with st.container(horizontal=True):
            decomposition = st.toggle(
                strings["CONV_DECOMPOSITION_LABEL"],
                value=settings.conv_rag_decomposition_enabled,
                help=strings["CONV_DECOMPOSITION_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_decomposition",
            )
            followups = st.toggle(
                strings["CONV_FOLLOWUPS_LABEL"],
                value=settings.conv_rag_followups_enabled,
                help=strings["CONV_FOLLOWUPS_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_followups",
            )
            inspect = st.toggle(
                strings["CONV_INSPECT_LABEL"],
                value=False,
                help=strings["CONV_INSPECT_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_inspect",
            )
        _render_prompt_editor(strings, key_prefix, session_root, disabled=disabled)
    return ConversationalControls(
        index=index,
        answer_model=answer_model,
        top_k=top_k,
        tone=tone,
        reranker=reranker,
        aux_model_id=aux_model_id,
        decomposition=decomposition,
        followups=followups,
        inspect=inspect,
        followup_drop=float(drop),
        followup_keep=float(keep),
    )


def _render_prompt_editor(
    strings: Strings, key_prefix: str, session_root: Path, *, disabled: bool
) -> None:
    """Render the prompt-template editor (one tab per Step 5 LLM prompt + Welcome)."""
    st.caption(strings["CONV_PROMPTS_LABEL"])
    st.caption(strings["CONV_PROMPTS_CAPTION"])
    tab_labels = [strings[_PROMPT_TAB_KEYS[key]] for key in CONVERSATIONAL_PROMPT_KEYS]
    tab_labels.append(strings["CONV_PROMPT_TAB_WELCOME"])
    tabs = st.tabs(tab_labels)
    for tab, prompt_key in zip(tabs[:-1], CONVERSATIONAL_PROMPT_KEYS, strict=True):
        with tab:
            _render_single_prompt(strings, key_prefix, session_root, prompt_key, disabled=disabled)
    with tabs[-1]:
        _render_welcome_prompt(strings, key_prefix, session_root, disabled=disabled)


def _render_prompt_actions(
    strings: Strings,
    session_root: Path,
    prompt_key: str,
    widget_key: str,
    *,
    disabled: bool,
    fields: str | None = None,
) -> None:
    """Render the shared Reset / Save row for a prompt-editor tab.

    ``fields`` is the placeholder list shown when an edit drops a required
    placeholder; pass ``None`` for a prompt with no placeholders (the Welcome
    greeting), which then saves unconditionally.
    """
    reset_col, save_col = st.columns(2, vertical_alignment="center")
    with reset_col:
        if st.button(
            strings["CONV_PROMPT_RESET"],
            icon=":material/restart_alt:",
            disabled=disabled,
            key=f"{widget_key}_reset",
        ):
            reset_conversational_prompt(session_root, prompt_key)
            st.session_state.pop(widget_key, None)
            st.toast(strings["CONV_PROMPT_RESET_TOAST"], icon=":material/check:")
            st.rerun()
    with save_col, st.container(horizontal_alignment="right"):
        if st.button(
            strings["CONV_PROMPT_SAVE"],
            type="primary",
            icon=":material/check:",
            disabled=disabled,
            key=f"{widget_key}_save",
        ):
            if fields is not None and not conversational_prompt_is_valid(
                prompt_key, st.session_state.get(widget_key, "")
            ):
                st.warning(strings["CONV_PROMPT_INVALID"].format(fields=fields))
            else:
                save_conversational_prompt(session_root, prompt_key, st.session_state[widget_key])
                st.toast(strings["CONV_PROMPT_SAVED_TOAST"], icon=":material/check:")
                st.rerun()


def _render_single_prompt(
    strings: Strings, key_prefix: str, session_root: Path, prompt_key: str, *, disabled: bool
) -> None:
    """Render one prompt's editable text area with Save / Reset-to-default."""
    fields = ", ".join("{" + name + "}" for name in CONVERSATIONAL_PROMPT_FIELDS[prompt_key])
    widget_key = f"{key_prefix}_prompt_{prompt_key}"
    # Seed the text area with the effective prompt (and self-heal a blank value so
    # the editor never shows empty); assigning before the widget avoids the
    # value+key warning.
    st.session_state[widget_key] = editor_prompt_text(
        st.session_state.get(widget_key), prompt_key, session_root
    )
    st.text_area(
        strings[_PROMPT_TAB_KEYS[prompt_key]],
        height=_PROMPT_EDITOR_HEIGHT,
        label_visibility="collapsed",
        disabled=disabled,
        key=widget_key,
    )
    st.caption(strings["CONV_PROMPT_FIELDS_CAPTION"].format(fields=fields))
    _render_prompt_actions(
        strings, session_root, prompt_key, widget_key, disabled=disabled, fields=fields
    )


def _render_welcome_prompt(
    strings: Strings, key_prefix: str, session_root: Path, *, disabled: bool
) -> None:
    """Render the editable new-conversation welcome greeting (app-only, no placeholders)."""
    widget_key = f"{key_prefix}_prompt_{WELCOME_PROMPT_KEY}"
    current = st.session_state.get(widget_key)
    if not (current and str(current).strip()):
        st.session_state[widget_key] = resolve_welcome_message(
            session_root, strings["CHAT_WELCOME_DEFAULT"]
        )
    st.text_area(
        strings["CONV_PROMPT_TAB_WELCOME"],
        height=_PROMPT_EDITOR_HEIGHT,
        label_visibility="collapsed",
        disabled=disabled,
        key=widget_key,
    )
    st.caption(strings["CONV_PROMPT_WELCOME_CAPTION"])
    _render_prompt_actions(strings, session_root, WELCOME_PROMPT_KEY, widget_key, disabled=disabled)


def render_turn_metadata(strings: Strings, answer: ConversationalAnswer) -> None:
    """Render the compact per-turn metadata strip (timings + models)."""
    timings = answer.timings
    rows = [
        (strings["CONV_META_PLAN"], f"{timings.get('plan', 0.0):.2f}s"),
        (strings["CONV_META_RETRIEVE"], f"{timings.get('retrieve', 0.0):.2f}s"),
        (strings["CONV_META_RERANK"], f"{timings.get('rerank', 0.0):.2f}s"),
        (strings["CONV_META_ANSWER"], f"{timings.get('answer', 0.0):.2f}s"),
        (strings["CONV_META_FOLLOWUPS"], f"{timings.get('followups', 0.0):.2f}s"),
        (strings["CONV_META_STATE"], f"{timings.get('state', 0.0):.2f}s"),
        (strings["CONV_META_ANSWER_MODEL"], answer.model_used or "—"),
        (strings["CONV_META_AUX_MODEL"], answer.aux_model_used or "—"),
        (strings["CONV_META_RERANKER"], answer.reranker_used or "—"),
    ]
    st.markdown(kv_grid_html(rows, columns=4, margin_top=True), unsafe_allow_html=True)


def render_turn_inspection(
    strings: Strings, answer: ConversationalAnswer, *, default_tab: str = "raw"
) -> None:
    """Render the 'Inspect this turn' expander: metadata strip + a tab per stage."""
    with st.expander(strings["CONV_INSPECT_EXPANDER"], expanded=False):
        render_turn_metadata(strings, answer)
        tabs = st.tabs(
            [
                strings["CONV_TAB_DECOMPOSITION"],
                strings["CONV_TAB_RETRIEVAL"],
                strings["CONV_TAB_RERANKING"],
                strings["CONV_TAB_STATE"],
                strings["CONV_TAB_FOLLOWUPS"],
            ]
        )
        with tabs[0]:
            _render_decomposition(strings, answer.plan)
        with tabs[1]:
            if answer.sources:
                render_result_cards(strings, answer.sources, default_tab=default_tab)
            else:
                st.caption(strings["RAG_NO_INDEX_HINT"])
        with tabs[2]:
            st.caption(
                strings["CONV_INSPECT_RERANKER_USED"].format(reranker=answer.reranker_used or "—")
            )
            _render_ranked_sources(answer.sources)
        with tabs[3]:
            _render_state(strings, answer.state)
        with tabs[4]:
            _render_followups(strings, answer.follow_ups)


def render_followup_buttons(
    strings: Strings, follow_ups: Sequence[ValidatedFollowup], turn_id: int
) -> str | None:
    """Render follow-up suggestion buttons; return the clicked question or None."""
    if not follow_ups:
        return None
    st.caption(strings["CONV_FOLLOWUPS_CAPTION"])
    clicked: str | None = None
    with st.container(horizontal=True):
        for index, item in enumerate(follow_ups):
            if st.button(item.question, key=f"conversational_rag_sugg_{turn_id}_{index}"):
                clicked = item.question
    return clicked


def _render_decomposition(strings: Strings, plan: QueryPlan) -> None:
    st.markdown(f"**{strings['CONV_INSPECT_SUBQUESTIONS']}**")
    for question in plan.sub_questions:
        st.markdown(f"- {question}")
    if plan.degraded:
        st.caption(strings["CONV_INSPECT_DEGRADED"])


def _render_ranked_sources(sources: Sequence) -> None:
    rows = [
        (f"{index}. {chunk.source or '?'}", f"{round(max(0.0, min(1.0, chunk.score)) * 100)}%")
        for index, chunk in enumerate(sources, start=1)
    ]
    if rows:
        st.markdown(kv_grid_html(rows, columns=2), unsafe_allow_html=True)


def _render_state(strings: Strings, state: ConversationState) -> None:
    if not (state.summary or state.entities or state.recent_resolved or state.open_threads):
        st.caption(strings["CONV_INSPECT_STATE_EMPTY"])
        return
    if state.summary:
        st.markdown(f"**{strings['CONV_INSPECT_STATE_SUMMARY']}**")
        st.write(state.summary)
    rows: list[tuple[str, str]] = list(state.entities.items())
    if rows:
        st.markdown(f"**{strings['CONV_INSPECT_STATE_ENTITIES']}**")
        st.markdown(kv_grid_html(rows, columns=2), unsafe_allow_html=True)
    if state.recent_resolved:
        st.markdown(f"**{strings['CONV_INSPECT_STATE_RECENT']}**")
        for question in state.recent_resolved:
            st.markdown(f"- {question}")
    if state.open_threads:
        st.markdown(f"**{strings['CONV_INSPECT_STATE_THREADS']}**")
        for thread in state.open_threads:
            st.markdown(f"- {thread}")


def _render_followups(strings: Strings, follow_ups: Sequence[ValidatedFollowup]) -> None:
    if not follow_ups:
        st.caption(strings["CONV_INSPECT_FOLLOWUPS_NONE"])
        return
    rows = [
        (html.unescape(item.question), f"{round(max(0.0, min(1.0, item.score)) * 100)}%")
        for item in follow_ups
    ]
    st.markdown(kv_grid_html(rows, columns=2), unsafe_allow_html=True)
