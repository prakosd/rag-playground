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
from artifact_store import LibraryMessage
from rag_engine import (
    CHAT_MODEL_OPTIONS,
    CONVERSATIONAL_PROMPT_FIELDS,
    ConversationalAnswer,
    ConversationalConfig,
    ConversationState,
    QueryPlan,
    RagConfig,
    RetrievedChunk,
    StagePromptTrace,
    StageTokenUsage,
    ValidatedFollowup,
)
from rag_engine.messages import CODE_FOLLOWUPS_NONE_VALID, CODE_RERANK_UNAVAILABLE

from app_support.basic_rag_qa.basic_rag_qa_form_ui import tone_choices
from app_support.conversational_rag.conversational_prompts import (
    CONVERSATIONAL_PROMPT_KEYS,
    ERROR_REPLY_PROMPT_KEY,
    FOLLOWUP_INTRO_PROMPT_KEY,
    NO_FOLLOWUPS_PROMPT_KEY,
    WELCOME_PROMPT_KEY,
    conversational_prompt_is_valid,
    editor_prompt_text,
    pick_random_line,
    reset_conversational_prompt,
    resolve_app_message,
    resolve_conversational_prompts,
    save_conversational_prompt,
)
from app_support.i18n import localize_message
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
    "FOLLOWUP_BUBBLE_KEY_PREFIX",
    "aux_model_choices",
    "build_conversational_config",
    "render_advanced_controls",
    "render_followup_bubble",
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
# Suggested follow-ups render in their own keyed container so the page CSS can hide
# the duplicate assistant avatar (they read as a continuation of the answer bubble).
FOLLOWUP_BUBBLE_KEY_PREFIX = "conv-followup-"


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
        aux_options, aux_default = aux_model_choices()
        # One row: reranking (compact) · auxiliary model (wide enough for the full
        # label) · thresholds slider (the remaining space).
        rerank_col, aux_col, threshold_col = st.columns(
            [2.4, 4.3, 3.3], vertical_alignment="bottom"
        )
        with rerank_col:
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
        with aux_col:
            aux_model_id = st.selectbox(
                strings["CONV_AUX_MODEL_LABEL"],
                options=aux_options,
                index=aux_default,
                format_func=lambda model_id: chat_model_label(model_id, strings),
                help=strings["CONV_AUX_MODEL_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_aux_model",
            )
        with threshold_col:
            drop, keep = st.slider(
                strings["CONV_THRESHOLD_LABEL"],
                min_value=0.0,
                max_value=1.0,
                value=(
                    settings.conv_rag_followup_drop_score,
                    settings.conv_rag_followup_min_score,
                ),
                step=0.05,
                help=strings["CONV_THRESHOLD_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_thresholds",
            )
        toggles_left, toggles_right = st.columns([3, 1], vertical_alignment="center")
        with toggles_left, st.container(horizontal=True):
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
        with toggles_right, st.container(horizontal_alignment="right"):
            inspect = st.toggle(
                strings["CONV_INSPECT_LABEL"],
                value=False,
                help=strings["CONV_INSPECT_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_inspect",
            )
        _render_prompt_editor(
            strings,
            key_prefix,
            session_root,
            disabled=disabled,
            decomposition=decomposition,
            followups=followups,
            reranker=reranker,
        )
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


# App-only message tabs: (prompt key, tab-label key, caption key, default-text key).
# The welcome greeting and error reply always show; the follow-up ones follow the
# Follow-ups toggle.
_WELCOME_TAB = (
    WELCOME_PROMPT_KEY,
    "CONV_PROMPT_TAB_WELCOME",
    "CONV_PROMPT_WELCOME_CAPTION",
    "CHAT_WELCOME_DEFAULT",
)
_ERROR_REPLY_TAB = (
    ERROR_REPLY_PROMPT_KEY,
    "CONV_PROMPT_TAB_ERROR_REPLY",
    "CONV_PROMPT_ERROR_REPLY_CAPTION",
    "CONV_ERROR_REPLY_DEFAULT",
)
_FOLLOWUP_MESSAGE_TABS = (
    (
        FOLLOWUP_INTRO_PROMPT_KEY,
        "CONV_PROMPT_TAB_FOLLOWUP_INTRO",
        "CONV_PROMPT_FOLLOWUP_INTRO_CAPTION",
        "CONV_FOLLOWUP_INTRO_DEFAULT",
    ),
    (
        NO_FOLLOWUPS_PROMPT_KEY,
        "CONV_PROMPT_TAB_NO_FOLLOWUPS",
        "CONV_PROMPT_NO_FOLLOWUPS_CAPTION",
        "CONV_NO_FOLLOWUPS_DEFAULT",
    ),
)


def _prompt_tab_visible(key: str, *, decomposition: bool, followups: bool, reranker: str) -> bool:
    """Whether a stage's prompt tab shows, given the toggles that gate that stage."""
    if key == "decompose":
        return decomposition
    if key in ("followups", "answerability"):
        return followups
    if key == "rerank":
        return reranker == "llm"
    return True


def _render_prompt_editor(
    strings: Strings,
    key_prefix: str,
    session_root: Path,
    *,
    disabled: bool,
    decomposition: bool,
    followups: bool,
    reranker: str,
) -> None:
    """Render the prompt-template editor, hiding tabs whose feature is turned off."""
    with st.expander(strings["CONV_PROMPTS_LABEL"], expanded=False):
        model_keys = [
            key
            for key in CONVERSATIONAL_PROMPT_KEYS
            if _prompt_tab_visible(
                key, decomposition=decomposition, followups=followups, reranker=reranker
            )
        ]
        message_tabs = [
            _WELCOME_TAB,
            _ERROR_REPLY_TAB,
            *(_FOLLOWUP_MESSAGE_TABS if followups else ()),
        ]
        labels = [strings[_PROMPT_TAB_KEYS[key]] for key in model_keys]
        labels += [strings[label_key] for _, label_key, _, _ in message_tabs]
        tabs = st.tabs(labels)
        for tab, prompt_key in zip(tabs[: len(model_keys)], model_keys, strict=True):
            with tab:
                _render_single_prompt(
                    strings, key_prefix, session_root, prompt_key, disabled=disabled
                )
        for tab, spec in zip(tabs[len(model_keys) :], message_tabs, strict=True):
            with tab:
                _render_app_message_prompt(
                    strings, key_prefix, session_root, spec, disabled=disabled
                )


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
    st.markdown(
        f"<div style='margin:-0.5rem 0 0.25rem;opacity:0.6;font-size:0.875rem'>"
        f"{html.escape(strings['CONV_PROMPT_FIELDS_CAPTION'].format(fields=fields))}</div>",
        unsafe_allow_html=True,
    )
    st.text_area(
        strings[_PROMPT_TAB_KEYS[prompt_key]],
        height=_PROMPT_EDITOR_HEIGHT,
        label_visibility="collapsed",
        disabled=disabled,
        key=widget_key,
    )
    _render_prompt_actions(
        strings, session_root, prompt_key, widget_key, disabled=disabled, fields=fields
    )


def _render_app_message_prompt(
    strings: Strings,
    key_prefix: str,
    session_root: Path,
    spec: tuple[str, str, str, str],
    *,
    disabled: bool,
) -> None:
    """Render one app-only message editor (welcome / follow-up intro / no-suggestions).

    These carry no placeholders and hold one alternate per line; a random line is
    shown at render (seeded per turn/conversation), so Save stores them verbatim.
    """
    prompt_key, label_key, caption_key, default_key = spec
    widget_key = f"{key_prefix}_prompt_{prompt_key}"
    current = st.session_state.get(widget_key)
    if not (current and str(current).strip()):
        st.session_state[widget_key] = resolve_app_message(
            session_root, prompt_key, strings[default_key]
        )
    st.text_area(
        strings[label_key],
        height=_PROMPT_EDITOR_HEIGHT,
        label_visibility="collapsed",
        disabled=disabled,
        key=widget_key,
    )
    st.caption(strings[caption_key])
    _render_prompt_actions(strings, session_root, prompt_key, widget_key, disabled=disabled)


# Per-turn timing stages in execution order: (timings key, i18n label key).
_TIMING_STAGES = (
    ("plan", "CONV_META_PLAN"),
    ("retrieve", "CONV_META_RETRIEVE"),
    ("rerank", "CONV_META_RERANK"),
    ("answer", "CONV_META_ANSWER"),
    ("followups", "CONV_META_FOLLOWUPS"),
    ("state", "CONV_META_STATE"),
)
# Token-usage process key → display stage; the answerability probe folds into
# follow-ups. Display stages render in execution order (retrieval spends no tokens).
_TOKEN_PROCESS_STAGE = {
    "decomposition": "plan",
    "reranking": "rerank",
    "answer": "answer",
    "followups": "followups",
    "answerability": "followups",
    "state": "state",
}


def _compact_tokens(count: int) -> str:
    """Short token count, e.g. 320 or 1.4k."""
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _stage_tokens(token_usage: Sequence[StageTokenUsage]) -> dict[str, int]:
    """Total tokens per display stage (the answerability probe folds into follow-ups)."""
    totals: dict[str, int] = {}
    for stage in token_usage:
        display = _TOKEN_PROCESS_STAGE.get(stage.process)
        if display is None or stage.usage.total_tokens is None:
            continue
        totals[display] = totals.get(display, 0) + stage.usage.total_tokens
    return totals


def render_turn_metadata(strings: Strings, answer: ConversationalAnswer) -> None:
    """Render per-turn metadata: a Process | Time·Tokens grid (2 stages/row), then models."""
    timings = answer.timings
    tokens = _stage_tokens(answer.token_usage)
    rows: list[tuple[str, str]] = []
    for key, label in _TIMING_STAGES:
        value = f"{timings.get(key, 0.0):.2f}s"
        if key in tokens:
            value += f" · {_compact_tokens(tokens[key])}"
        rows.append((strings[label], value))
    st.markdown(kv_grid_html(rows, columns=4), unsafe_allow_html=True)
    model_rows = [
        (strings["CONV_META_ANSWER_MODEL"], answer.model_used or "—"),
        (strings["CONV_META_AUX_MODEL"], answer.aux_model_used or "—"),
        (strings["CONV_META_RERANKER"], answer.reranker_used or "—"),
    ]
    st.markdown(kv_grid_html(model_rows, columns=2, margin_top=True), unsafe_allow_html=True)


def _render_diagnostics(strings: Strings, answer: ConversationalAnswer) -> None:
    """List this turn's raw warnings and errors, kept out of the chat for a clean flow."""
    if not answer.warnings and not answer.errors:
        st.caption(strings["CONV_DIAGNOSTICS_EMPTY"])
        return
    for warning in answer.warnings:
        st.warning(localize_message(strings, warning.as_dict()))
    for error in answer.errors:
        st.error(localize_message(strings, error.as_dict()))


def render_turn_inspection(
    strings: Strings, answer: ConversationalAnswer, *, default_tab: str = "raw"
) -> None:
    """Render the 'Inspect this turn' expander: metadata strip + a tab per stage."""
    with st.expander(strings["CONV_INSPECT_EXPANDER"], expanded=False):
        render_turn_metadata(strings, answer)
        tabs = st.tabs(
            [
                strings["CONV_TAB_ANSWER"],
                strings["CONV_TAB_DECOMPOSITION"],
                strings["CONV_TAB_RETRIEVAL"],
                strings["CONV_TAB_FOLLOWUPS"],
                strings["CONV_TAB_STATE"],
                strings["CONV_TAB_DIAGNOSTICS"],
            ]
        )
        with tabs[0]:
            _render_stage_prompt(strings, answer, "answer")
        with tabs[1]:
            _render_decomposition(strings, answer.plan)
            _render_stage_prompt(strings, answer, "decomposition")
        with tabs[2]:
            _render_retrieval(strings, answer, default_tab=default_tab)
        with tabs[3]:
            _render_followups(
                strings,
                answer.follow_ups,
                none_valid_note=_inspect_note(strings, answer.warnings, CODE_FOLLOWUPS_NONE_VALID),
            )
            _render_followups_prompts(strings, answer)
        with tabs[4]:
            _render_state(strings, answer.state)
            st.caption(strings["CONV_INSPECT_STATE_HELP"])
            _render_stage_prompt(strings, answer, "state")
        with tabs[5]:
            _render_diagnostics(strings, answer)


def _render_prompt_trace(strings: Strings, trace: StagePromptTrace) -> None:
    """Show one stage's rendered prompt and raw reply in Prompt/Response sub-tabs."""
    prompt_tab, response_tab = st.tabs(
        [strings["CONV_INSPECT_PROMPT_LABEL"], strings["CONV_INSPECT_RESPONSE_LABEL"]]
    )
    with prompt_tab:
        st.code(trace.prompt or "—", language=None, wrap_lines=True)
    with response_tab:
        st.code(trace.response or "—", language=None, wrap_lines=True)


def _render_stage_prompt(strings: Strings, answer: ConversationalAnswer, process: str) -> None:
    """Show the captured prompt/reply for *process*, or a note when none was sent."""
    trace = next((item for item in answer.prompt_traces if item.process == process), None)
    if trace is None:
        st.caption(strings["CONV_INSPECT_NO_PROMPT"])
        return
    _render_prompt_trace(strings, trace)


def _render_followups_prompts(strings: Strings, answer: ConversationalAnswer) -> None:
    """Follow-up generation prompt in sub-tabs, then each answerability probe below."""
    _render_stage_prompt(strings, answer, "followups")
    probes = [item for item in answer.prompt_traces if item.process == "answerability"]
    for index, probe in enumerate(probes, start=1):
        with st.expander(strings["CONV_INSPECT_ANSWERABILITY_PROBE"].format(n=index)):
            _render_prompt_trace(strings, probe)


def render_followup_bubble(
    strings: Strings,
    session_root: Path,
    follow_ups: Sequence[ValidatedFollowup],
    turn_id: int,
) -> str | None:
    """Render the follow-up suggestions as a continuation bubble under the answer.

    Shows an editable intro line followed by the suggestions as inline text links
    (tertiary buttons); when a turn produced none, a gentle nudge stands in. The
    intro/nudge wording is a per-session template with one alternate per line, a
    random one chosen per turn. Returns the clicked question, or None.
    """
    with st.container(key=f"{FOLLOWUP_BUBBLE_KEY_PREFIX}{turn_id}"), st.chat_message("assistant"):
        if not follow_ups:
            nudge = resolve_app_message(
                session_root, NO_FOLLOWUPS_PROMPT_KEY, strings["CONV_NO_FOLLOWUPS_DEFAULT"]
            )
            st.markdown(pick_random_line(nudge, turn_id))
            return None
        intro = resolve_app_message(
            session_root, FOLLOWUP_INTRO_PROMPT_KEY, strings["CONV_FOLLOWUP_INTRO_DEFAULT"]
        )
        st.markdown(pick_random_line(intro, turn_id))
        clicked: str | None = None
        with st.container(horizontal=True, gap="small"):
            for index, item in enumerate(follow_ups):
                if st.button(
                    item.question,
                    key=f"conversational_rag_sugg_{turn_id}_{index}",
                    type="tertiary",
                ):
                    clicked = item.question
        return clicked


def _render_decomposition(strings: Strings, plan: QueryPlan) -> None:
    st.markdown(f"**{strings['CONV_INSPECT_SUBQUESTIONS']}**")
    for question in plan.sub_questions:
        st.markdown(f"- {question}")
    if plan.degraded:
        st.caption(strings["CONV_INSPECT_DEGRADED"])


def subquestion_provenance_rows(
    sources: Sequence[RetrievedChunk], plan: QueryPlan
) -> list[tuple[str, str]]:
    """Map each sub-question to the result ranks (#N) it retrieved.

    Lets the merged Retrieval tab show which sub-question each result came from.
    Returns [] when planning produced a single sub-question (no per-query provenance
    is recorded) or when no chunk carries matched-query provenance.
    """
    if len(plan.sub_questions) <= 1:
        return []
    ranks: dict[str, list[str]] = {question: [] for question in plan.sub_questions}
    for rank, chunk in enumerate(sources, start=1):
        for question in chunk.matched_queries:
            if question in ranks:
                ranks[question].append(f"#{rank}")
    return [(question, ", ".join(hits)) for question, hits in ranks.items() if hits]


def _render_retrieval(strings: Strings, answer: ConversationalAnswer, *, default_tab: str) -> None:
    """Merged Retrieval + re-ranking view: explain, group by sub-question, then cards."""
    if not answer.sources:
        st.caption(strings["RAG_NO_INDEX_HINT"])
        return
    st.caption(strings["CONV_INSPECT_RETRIEVAL_HELP"])
    st.caption(strings["CONV_INSPECT_RERANKER_USED"].format(reranker=answer.reranker_used or "—"))
    rerank_note = _inspect_note(strings, answer.warnings, CODE_RERANK_UNAVAILABLE)
    if rerank_note:
        st.caption(rerank_note)
    rows = subquestion_provenance_rows(answer.sources, answer.plan)
    if rows:
        st.markdown(f"**{strings['CONV_INSPECT_RETRIEVAL_BYQUERY']}**")
        for question, hits in rows:
            st.markdown(f"- {question} → {hits}")
    render_result_cards(strings, answer.sources, default_tab=default_tab, preserve_order=True)
    _render_stage_prompt(strings, answer, "reranking")


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


def _inspect_note(strings: Strings, warnings: Sequence[LibraryMessage], code: str) -> str | None:
    """Localized text of the first warning matching *code* (relocated into Inspect)."""
    for message in warnings:
        if message.code == code:
            return localize_message(strings, message.as_dict())
    return None


def _render_followups(
    strings: Strings,
    follow_ups: Sequence[ValidatedFollowup],
    *,
    none_valid_note: str | None = None,
) -> None:
    if not follow_ups:
        st.caption(none_valid_note or strings["CONV_INSPECT_FOLLOWUPS_NONE"])
        return
    rows = [
        (html.unescape(item.question), f"{round(max(0.0, min(1.0, item.score)) * 100)}%")
        for item in follow_ups
    ]
    st.markdown(kv_grid_html(rows, columns=2), unsafe_allow_html=True)
    st.caption(strings["CONV_INSPECT_FOLLOWUPS_HELP"])
