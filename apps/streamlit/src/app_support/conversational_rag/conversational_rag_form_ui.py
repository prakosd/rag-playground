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
    "INSPECT_BUBBLE_KEY_PREFIX",
    "aux_model_choices",
    "build_conversational_config",
    "decomposition_help_text",
    "followup_answerability_rows",
    "render_advanced_controls",
    "render_followup_bubble",
    "render_turn_inspection",
    "render_turn_metadata",
    "subquestion_provenance_rows",
]

_RERANKER_KEYS = ("off", "local", "llm")
# Panel layout mirrors Step 4's Basic RAG Q&A panel: a wide control + a compact one.
_PANEL_COLUMN_WIDTHS = (0.8, 0.2)
_MAX_TOP_K = 20
# The follow-up limit doubles as the on/off switch (0-5): 0 = off, 1-5 = show at most
# that many (fewer appear when few pass validation).
_FOLLOWUP_SHOW_MIN = 0
_FOLLOWUP_SHOW_MAX = 5
# Decomposition limit (1-5): 1 = off (one question), 2-5 = split into at most N sub-questions.
_DECOMPOSITION_LIMIT_MIN = 1
_DECOMPOSITION_LIMIT_MAX = 5
# Follow-up answerability tuning (library defaults 3 / 2): how many passages each
# follow-up probe fetches and how many the model reads to judge a borderline one.
_PROBE_K_MIN = 1
_PROBE_K_MAX = 10
_ANSWERABILITY_CHUNKS_MIN = 1
_ANSWERABILITY_CHUNKS_MAX = 10
# Conversation-memory start turn (library default 4): opening turns kept verbatim
# before the model begins summarising.
_STATE_START_TURN_MIN = 1
_STATE_START_TURN_MAX = 20
# Rolling conversation-summary length cap (library default 150 words).
_STATE_MAX_WORDS_MIN = 50
_STATE_MAX_WORDS_MAX = 300
_STATE_MAX_WORDS_STEP = 10
# Recent-turn windows (0 = none): turns the answer prompt sees (library default 3,
# app default 5) and turns the planner prompt sees / the memory recent-questions window.
_ANSWER_RECENT_TURNS_MIN = 0
_ANSWER_RECENT_TURNS_MAX = 10
_PLAN_RECENT_TURNS_MIN = 0
_PLAN_RECENT_TURNS_MAX = 10
# Ask the model for a few more candidates than will be shown, so validation (which
# drops unanswerable or duplicate suggestions) still has enough left to fill the limit.
_FOLLOWUP_CANDIDATE_BUFFER = 2
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
# Each per-turn Inspect panel renders inside its own keyed container so page CSS can
# scope the nested Prompt/Response tab tightening to just these panels.
INSPECT_BUBBLE_KEY_PREFIX = "conv-inspect-"
# Answerability verdict markers for the Inspect follow-ups grid (emoji → theme-independent).
_VERDICT_KEEP_EMOJI = "🟢"
_VERDICT_DROP_EMOJI = "🔴"


@dataclass(frozen=True)
class ConversationalControls:
    """The Step 5 UI choices that shape a :class:`ConversationalConfig`."""

    index: IndexRef | None
    answer_model: str
    top_k: int
    tone: str
    reranker: str
    aux_model_id: str
    decomposition_limit: int
    followup_show_count: int
    inspect: bool
    followup_drop: float
    followup_keep: float
    followup_probe_k: int
    answerability_chunks: int
    state_summary_start_turn: int
    state_summary_max_words: int
    answer_recent_turns: int
    plan_recent_turns: int


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
        plan_enabled=controls.decomposition_limit > _DECOMPOSITION_LIMIT_MIN,
        plan_max_subquestions=controls.decomposition_limit,
        reranker=controls.reranker,
        rerank_top_n=settings.conv_rag_rerank_top_n,
        followups_enabled=controls.followup_show_count > 0,
        followups_parallel=settings.conv_rag_followups_parallel,
        # A 0 limit means "off" (handled above); clamp to >= 1 so the library model,
        # which requires a positive count, still validates.
        followup_show_count=max(controls.followup_show_count, 1),
        # Size the candidate pool (the prompt's {count}) from the shown limit so the
        # limit drives generation, keeping a small buffer for validation drop-off.
        followup_candidate_count=max(controls.followup_show_count, 1) + _FOLLOWUP_CANDIDATE_BUFFER,
        followup_min_score=controls.followup_keep,
        followup_drop_score=controls.followup_drop,
        followup_probe_k=controls.followup_probe_k,
        answerability_chunks=controls.answerability_chunks,
        state_summary_start_turn=controls.state_summary_start_turn,
        state_summary_max_words=controls.state_summary_max_words,
        answer_recent_turns=controls.answer_recent_turns,
        plan_recent_turns=controls.plan_recent_turns,
        tone=controls.tone,
        language=language,
    )


def render_advanced_controls(
    strings: Strings,
    key_prefix: str,
    indexes: Sequence[IndexRef],
    session_root: Path,
    *,
    disabled: bool = False,
) -> ConversationalControls:
    """Render the index / chunks / model / tone panel and the advanced options.

    *disabled* locks every control while a turn is streaming, so a mid-stream change
    cannot interrupt the run and drop the just-streamed turn.
    """
    settings = get_settings()
    model_options, model_default = chat_model_choices()
    tones, tone_default = tone_choices()
    with st.container(border=True):
        index_col, chunks_col = st.columns(_PANEL_COLUMN_WIDTHS, vertical_alignment="center")
        with index_col:
            index = select_index(strings, indexes, key=f"{key_prefix}_index", disabled=disabled)
        disabled = index is None or disabled
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
        # Inspect is a view option (it reveals the per-turn glass-box panel), so it leads
        # the panel on its own row, above the pipeline-stage groups below.
        # Persist the preference in a plain key so it survives a session switch's page-less
        # reruns (which can drop the toggle's own widget state, leaving it shown on but
        # reading off): the toggle re-seeds from the plain key, mirrored back each run, and
        # drives the per-turn Inspect render.
        inspect_pref_key = f"{key_prefix}_inspect_on"
        inspect = st.toggle(
            strings["CONV_INSPECT_LABEL"],
            value=st.session_state.get(inspect_pref_key, False),
            help=strings["CONV_INSPECT_HELP"],
            disabled=disabled,
            key=f"{key_prefix}_inspect",
        )
        st.session_state[inspect_pref_key] = bool(inspect)

        # The groups below follow the turn pipeline: a shared helper model, then
        # decompose → re-rank → answer → follow-ups → memory, each under its own heading.
        _section_label(strings["CONV_ADV_GROUP_HELPER"])
        aux_model_id = st.selectbox(
            strings["CONV_AUX_MODEL_LABEL"],
            options=aux_options,
            index=aux_default,
            format_func=lambda model_id: chat_model_label(model_id, strings),
            help=strings["CONV_AUX_MODEL_HELP"],
            disabled=disabled,
            key=f"{key_prefix}_aux_model",
        )

        _section_label(strings["CONV_ADV_GROUP_DECOMPOSE"])
        decompose_col, plan_turns_col, _ = st.columns(3)
        with decompose_col:
            decomposition_limit = int(
                st.number_input(
                    strings["CONV_DECOMPOSITION_LABEL"],
                    min_value=_DECOMPOSITION_LIMIT_MIN,
                    max_value=_DECOMPOSITION_LIMIT_MAX,
                    value=min(
                        max(settings.conv_rag_decomposition_limit, _DECOMPOSITION_LIMIT_MIN),
                        _DECOMPOSITION_LIMIT_MAX,
                    ),
                    step=1,
                    help=strings["CONV_DECOMPOSITION_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_decomposition",
                )
            )
        decomposition_on = decomposition_limit > _DECOMPOSITION_LIMIT_MIN
        with plan_turns_col:
            plan_recent_turns = int(
                st.number_input(
                    strings["CONV_PLAN_RECENT_TURNS_LABEL"],
                    min_value=_PLAN_RECENT_TURNS_MIN,
                    max_value=_PLAN_RECENT_TURNS_MAX,
                    value=min(
                        max(settings.conv_rag_plan_recent_turns, _PLAN_RECENT_TURNS_MIN),
                        _PLAN_RECENT_TURNS_MAX,
                    ),
                    step=1,
                    help=strings["CONV_PLAN_RECENT_TURNS_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_plan_recent_turns",
                )
            )

        _section_label(strings["CONV_ADV_GROUP_RERANK"])
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

        _section_label(strings["CONV_ADV_GROUP_ANSWER"])
        answer_turns_col, _, _ = st.columns(3)
        with answer_turns_col:
            answer_recent_turns = int(
                st.number_input(
                    strings["CONV_ANSWER_RECENT_TURNS_LABEL"],
                    min_value=_ANSWER_RECENT_TURNS_MIN,
                    max_value=_ANSWER_RECENT_TURNS_MAX,
                    value=min(
                        max(settings.conv_rag_answer_recent_turns, _ANSWER_RECENT_TURNS_MIN),
                        _ANSWER_RECENT_TURNS_MAX,
                    ),
                    step=1,
                    help=strings["CONV_ANSWER_RECENT_TURNS_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_answer_recent_turns",
                )
            )

        _section_label(strings["CONV_ADV_GROUP_FOLLOWUPS"])
        followup_limit_col, threshold_col = st.columns([1, 2], vertical_alignment="bottom")
        with followup_limit_col:
            # The follow-up limit doubles as the on/off switch: 0 = off, 1-5 = show at
            # most that many. The deployment "start off" setting folds into the default.
            followup_default = (
                settings.conv_rag_followup_show_count
                if settings.conv_rag_followups_enabled
                else _FOLLOWUP_SHOW_MIN
            )
            followup_show_count = int(
                st.number_input(
                    strings["CONV_FOLLOWUPS_COUNT_LABEL"],
                    min_value=_FOLLOWUP_SHOW_MIN,
                    max_value=_FOLLOWUP_SHOW_MAX,
                    value=min(max(followup_default, _FOLLOWUP_SHOW_MIN), _FOLLOWUP_SHOW_MAX),
                    step=1,
                    help=strings["CONV_FOLLOWUPS_COUNT_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_followup_count",
                )
            )
            followups = followup_show_count > 0
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
        probe_col, answerability_col, _ = st.columns(3)
        with probe_col:
            followup_probe_k = int(
                st.number_input(
                    strings["CONV_PROBE_K_LABEL"],
                    min_value=_PROBE_K_MIN,
                    max_value=_PROBE_K_MAX,
                    value=min(max(settings.conv_rag_followup_probe_k, _PROBE_K_MIN), _PROBE_K_MAX),
                    step=1,
                    help=strings["CONV_PROBE_K_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_followup_probe_k",
                )
            )
        with answerability_col:
            answerability_chunks = int(
                st.number_input(
                    strings["CONV_ANSWERABILITY_CHUNKS_LABEL"],
                    min_value=_ANSWERABILITY_CHUNKS_MIN,
                    max_value=_ANSWERABILITY_CHUNKS_MAX,
                    value=min(
                        max(settings.conv_rag_answerability_chunks, _ANSWERABILITY_CHUNKS_MIN),
                        _ANSWERABILITY_CHUNKS_MAX,
                    ),
                    step=1,
                    help=strings["CONV_ANSWERABILITY_CHUNKS_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_answerability_chunks",
                )
            )

        _section_label(strings["CONV_ADV_GROUP_MEMORY"])
        memory_start_col, summary_words_col, _ = st.columns(3)
        with memory_start_col:
            state_summary_start_turn = int(
                st.number_input(
                    strings["CONV_STATE_START_TURN_LABEL"],
                    min_value=_STATE_START_TURN_MIN,
                    max_value=_STATE_START_TURN_MAX,
                    value=min(
                        max(settings.conv_rag_state_summary_start_turn, _STATE_START_TURN_MIN),
                        _STATE_START_TURN_MAX,
                    ),
                    step=1,
                    help=strings["CONV_STATE_START_TURN_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_state_start_turn",
                )
            )
        with summary_words_col:
            state_summary_max_words = int(
                st.number_input(
                    strings["CONV_STATE_MAX_WORDS_LABEL"],
                    min_value=_STATE_MAX_WORDS_MIN,
                    max_value=_STATE_MAX_WORDS_MAX,
                    value=min(
                        max(settings.conv_rag_state_summary_max_words, _STATE_MAX_WORDS_MIN),
                        _STATE_MAX_WORDS_MAX,
                    ),
                    step=_STATE_MAX_WORDS_STEP,
                    help=strings["CONV_STATE_MAX_WORDS_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_state_max_words",
                )
            )
        _render_prompt_editor(
            strings,
            key_prefix,
            session_root,
            disabled=disabled,
            decomposition=decomposition_on,
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
        decomposition_limit=decomposition_limit,
        followup_show_count=followup_show_count,
        inspect=inspect,
        followup_drop=float(drop),
        followup_keep=float(keep),
        followup_probe_k=followup_probe_k,
        answerability_chunks=answerability_chunks,
        state_summary_start_turn=state_summary_start_turn,
        state_summary_max_words=state_summary_max_words,
        answer_recent_turns=answer_recent_turns,
        plan_recent_turns=plan_recent_turns,
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
        # The model-stage prompts get a tab each; the app-only messages are grouped
        # under one "Messages" tab (nested tabs) so the row doesn't grow too wide.
        labels = [strings[_PROMPT_TAB_KEYS[key]] for key in model_keys]
        labels.append(strings["CONV_PROMPT_TAB_MESSAGES"])
        tabs = st.tabs(labels)
        for tab, prompt_key in zip(tabs[: len(model_keys)], model_keys, strict=True):
            with tab:
                _render_single_prompt(
                    strings, key_prefix, session_root, prompt_key, disabled=disabled
                )
        with tabs[-1]:
            message_labels = [strings[label_key] for _, label_key, _, _ in message_tabs]
            for tab, spec in zip(st.tabs(message_labels), message_tabs, strict=True):
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
    st.caption(
        strings["CONV_PROMPT_FIELDS_CAPTION"].format(fields=fields),
        help=strings["CONV_PROMPT_FIELDS_HELP"],
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
    # Caption above the field, matching the stage prompts, so it reads as a heading.
    st.markdown(
        f"<div style='margin:-0.5rem 0 0.25rem;opacity:0.6;font-size:0.875rem'>"
        f"{html.escape(strings[caption_key])}</div>",
        unsafe_allow_html=True,
    )
    st.text_area(
        strings[label_key],
        height=_PROMPT_EDITOR_HEIGHT,
        label_visibility="collapsed",
        disabled=disabled,
        key=widget_key,
    )
    _render_prompt_actions(strings, session_root, prompt_key, widget_key, disabled=disabled)


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
    """Short token count with unit, e.g. 320 Tok or 1.4 kTok."""
    return f"{count / 1000:.1f} kTok" if count >= 1000 else f"{count} Tok"


def _stage_tokens(token_usage: Sequence[StageTokenUsage]) -> dict[str, int]:
    """Total tokens per display stage (the answerability probe folds into follow-ups)."""
    totals: dict[str, int] = {}
    for stage in token_usage:
        display = _TOKEN_PROCESS_STAGE.get(stage.process)
        if display is None or stage.usage.total_tokens is None:
            continue
        totals[display] = totals.get(display, 0) + stage.usage.total_tokens
    return totals


def _numbered_stage_rows(stages: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Prefix each stage (label, value) with its 1-based position in execution order."""
    return [(f"{number}. {label}", value) for number, (label, value) in enumerate(stages, start=1)]


def render_turn_metadata(strings: Strings, answer: ConversationalAnswer) -> None:
    """Render per-turn metadata as two side-by-side 4-row grids: timings | models.

    The left grid lists each stage's time (and tokens when it spent any), numbered in
    execution order with decomposition and retrieval folded into one row (retrieval is a
    token-free vector search); the right grid leads with the fifth stage (state), then the
    unnumbered models used. Keeping both grids four rows tall avoids a lopsided gap.
    """
    timings = answer.timings
    tokens = _stage_tokens(answer.token_usage)

    def _timed(key: str) -> str:
        value = f"{timings.get(key, 0.0):.2f}s"
        if key in tokens:
            value += f" · {_compact_tokens(tokens[key])}"
        return value

    # The five pipeline stages are numbered in execution order; the first four fill the
    # left grid and the fifth (state) leads the right grid above the unnumbered model rows.
    stages = [
        (
            strings["CONV_META_DECOMPOSE_RETRIEVE"],
            f"{_timed('plan')} / {timings.get('retrieve', 0.0):.2f}s",
        ),
        (strings["CONV_META_RERANK"], _timed("rerank")),
        (strings["CONV_META_ANSWER"], _timed("answer")),
        (strings["CONV_META_FOLLOWUPS"], _timed("followups")),
        (strings["CONV_META_STATE"], _timed("state")),
    ]
    numbered = _numbered_stage_rows(stages)
    stage_rows = numbered[:4]
    model_rows = [
        numbered[4],
        (strings["CONV_META_ANSWER_MODEL"], answer.model_used or "—"),
        (strings["CONV_META_AUX_MODEL"], answer.aux_model_used or "—"),
        (strings["CONV_META_RERANKER"], answer.reranker_used or "—"),
    ]
    stages_col, models_col = st.columns(2)
    with stages_col:
        st.markdown(kv_grid_html(stage_rows, columns=2), unsafe_allow_html=True)
    with models_col:
        st.markdown(kv_grid_html(model_rows, columns=2), unsafe_allow_html=True)


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
    strings: Strings,
    answer: ConversationalAnswer,
    *,
    default_tab: str = "raw",
    turn_id: int = 0,
) -> None:
    """Render the 'Inspect this turn' expander: metadata strip + a tab per stage.

    The expander lives in a per-turn keyed container so page CSS can tighten the
    nested Prompt/Response tabs to just these panels.
    """
    with (
        st.container(key=f"{INSPECT_BUBBLE_KEY_PREFIX}{turn_id}"),
        st.expander(strings["CONV_INSPECT_EXPANDER"], expanded=False),
    ):
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
                answer.dropped_followups,
                none_valid_note=_inspect_note(strings, answer.warnings, CODE_FOLLOWUPS_NONE_VALID),
            )
            _render_followups_prompts(strings, answer)
        with tabs[4]:
            _render_state(strings, answer.state)
            _render_stage_prompt(
                strings, answer, "state", help_text=strings["CONV_INSPECT_STATE_HELP"]
            )
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


def _render_stage_prompt(
    strings: Strings,
    answer: ConversationalAnswer,
    process: str,
    *,
    help_text: str | None = None,
) -> None:
    """Show the captured prompt/reply for *process*, or a note when none was sent.

    *help_text* adds a hover hint to the "no prompt" note — used by the state tab to
    explain why early turns send no prompt without spending a caption line.
    """
    trace = next((item for item in answer.prompt_traces if item.process == process), None)
    if trace is None:
        st.caption(strings["CONV_INSPECT_NO_PROMPT"], help=help_text)
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


def _section_label(text: str, *, help_text: str | None = None) -> None:
    """Compact bold section label with an optional hover hint.

    Shared by every Inspect tab so section headers (Sub-questions, Re-ranker,
    Confidence %, conversation-state groups) read the same and stay tight.
    """
    st.caption(f"**{text}**", help=help_text)


def _bullet_list(items: Sequence[str]) -> None:
    """Render *items* as one tight `·`-prefixed block, one per line (markdown hard breaks)."""
    st.markdown("  \n".join(f"· {item}" for item in items))


def decomposition_help_text(strings: Strings, plan: QueryPlan) -> str:
    """Sub-questions hint, with the decomposition-cap note folded in when it applied.

    When the model proposed more sub-questions than the limit shows, the "proposed N,
    showing M" note joins the hover hint instead of a separate caption, keeping the
    panel uncluttered.
    """
    help_text = strings["CONV_INSPECT_SUBQUESTIONS_HELP"]
    if plan.proposed_count > len(plan.sub_questions):
        capped = strings["CONV_INSPECT_SUBQUESTIONS_CAPPED"].format(
            proposed=plan.proposed_count, shown=len(plan.sub_questions)
        )
        return f"{help_text} {capped}"
    return help_text


def _render_decomposition(strings: Strings, plan: QueryPlan) -> None:
    _section_label(
        strings["CONV_INSPECT_SUBQUESTIONS"], help_text=decomposition_help_text(strings, plan)
    )
    _bullet_list(plan.sub_questions)
    if plan.degraded:
        st.caption(strings["CONV_INSPECT_DEGRADED"])


def subquestion_provenance_rows(
    sources: Sequence[RetrievedChunk], plan: QueryPlan
) -> list[tuple[str, list[int]]]:
    """Map each sub-question to the sorted passage numbers (retrieval_rank) it retrieved.

    The passage number is the stable value shown on the result cards and returned by the
    re-ranker, so the merged Retrieval tab, the cards, and the re-ranker response line up.
    Returns [] when planning produced a single sub-question (no per-query provenance is
    recorded) or when no chunk carries matched-query provenance.
    """
    if len(plan.sub_questions) <= 1:
        return []
    numbers: dict[str, list[int]] = {question: [] for question in plan.sub_questions}
    for chunk in sources:
        for question in chunk.matched_queries:
            if question in numbers:
                numbers[question].append(chunk.retrieval_rank)
    return [(question, sorted(hits)) for question, hits in numbers.items() if hits]


def _render_retrieval(strings: Strings, answer: ConversationalAnswer, *, default_tab: str) -> None:
    """Merged Retrieval + re-ranking view: explain, group by sub-question, then cards."""
    if not answer.sources:
        st.caption(strings["RAG_NO_INDEX_HINT"])
        return
    all_chunks = [*answer.sources, *answer.overflow_sources]
    rows = subquestion_provenance_rows(all_chunks, answer.plan)
    reranker_label = strings["CONV_INSPECT_RERANKER_USED"].format(
        reranker=answer.reranker_used or "—"
    )
    if rows:
        # Re-ranker and the per-sub-question heading share one line to save height,
        # with their two hints merged behind a single help icon.
        _section_label(
            f"{reranker_label} · {strings['CONV_INSPECT_RETRIEVAL_BYQUERY']}",
            help_text=(
                f"{strings['CONV_INSPECT_RETRIEVAL_HELP']} "
                f"{strings['CONV_INSPECT_RETRIEVAL_BYQUERY_HELP']}"
            ),
        )
    else:
        _section_label(reranker_label, help_text=strings["CONV_INSPECT_RETRIEVAL_HELP"])
    rerank_note = _inspect_note(strings, answer.warnings, CODE_RERANK_UNAVAILABLE)
    if rerank_note:
        st.caption(rerank_note)
    if rows:
        badge = strings["RAG_RESULT_PASSAGE_BADGE"]
        _bullet_list(
            [
                f"{question} → " + " ".join(badge.format(n=n) for n in numbers)
                for question, numbers in rows
            ]
        )
    render_result_cards(strings, answer.sources, default_tab=default_tab, preserve_order=True)
    if answer.overflow_sources:
        with st.expander(
            strings["CONV_INSPECT_OVERFLOW"].format(count=len(answer.overflow_sources)),
            icon=":material/visibility_off:",
        ):
            render_result_cards(
                strings,
                answer.overflow_sources,
                default_tab=default_tab,
                preserve_order=True,
                start_rank=len(answer.sources) + 1,
            )
    _render_stage_prompt(strings, answer, "reranking")


def _render_state(strings: Strings, state: ConversationState) -> None:
    if not (state.summary or state.entities or state.recent_resolved or state.open_threads):
        st.caption(strings["CONV_INSPECT_STATE_EMPTY"])
        return
    if state.summary:
        _section_label(strings["CONV_INSPECT_STATE_SUMMARY"])
        st.write(state.summary)
    rows: list[tuple[str, str]] = list(state.entities.items())
    if rows:
        _section_label(strings["CONV_INSPECT_STATE_ENTITIES"])
        st.markdown(kv_grid_html(rows, columns=2), unsafe_allow_html=True)
    if state.recent_resolved:
        _section_label(strings["CONV_INSPECT_STATE_RECENT"])
        _bullet_list(state.recent_resolved)
    if state.open_threads:
        _section_label(strings["CONV_INSPECT_STATE_THREADS"])
        _bullet_list(state.open_threads)


def _inspect_note(strings: Strings, warnings: Sequence[LibraryMessage], code: str) -> str | None:
    """Localized text of the first warning matching *code* (relocated into Inspect)."""
    for message in warnings:
        if message.code == code:
            return localize_message(strings, message.as_dict())
    return None


def _answerability_value(emoji: str, verdict_label: str, score: float) -> str:
    """One verdict cell: emoji + Yes/No, with the confidence % appended when known."""
    label = f"{emoji} {verdict_label}"
    if score > 0:
        return f"{label} · {round(max(0.0, min(1.0, score)) * 100)}%"
    return label


def followup_answerability_rows(
    follow_ups: Sequence[ValidatedFollowup],
    dropped: Sequence[ValidatedFollowup],
    strings: Strings,
) -> list[tuple[str, str]]:
    """Inspect follow-up rows: (question, "🟢 Yes · 53%" / "🔴 No · 30%").

    Kept (answerable) candidates come first, then dropped (unanswerable) by confidence.
    The % — the follow-up's best semantic-search match — is omitted when unknown (e.g. a
    turn reloaded from history before scores were saved), leaving just the Yes/No verdict.
    """
    yes_label = strings["CONV_INSPECT_ANSWERABILITY_YES"]
    no_label = strings["CONV_INSPECT_ANSWERABILITY_NO"]
    rows: list[tuple[str, str]] = []
    for item in follow_ups:
        value = _answerability_value(_VERDICT_KEEP_EMOJI, yes_label, item.score)
        rows.append((html.unescape(item.question), value))
    for item in sorted(dropped, key=lambda item: item.score, reverse=True):
        value = _answerability_value(_VERDICT_DROP_EMOJI, no_label, item.score)
        rows.append((html.unescape(item.question), value))
    return rows


def _render_followups(
    strings: Strings,
    follow_ups: Sequence[ValidatedFollowup],
    dropped: Sequence[ValidatedFollowup] = (),
    *,
    none_valid_note: str | None = None,
) -> None:
    rows = followup_answerability_rows(follow_ups, dropped, strings)
    if not rows:
        st.caption(none_valid_note or strings["CONV_INSPECT_FOLLOWUPS_NONE"])
        return
    _section_label(
        strings["CONV_INSPECT_FOLLOWUPS_SCORE_HEADER"],
        help_text=strings["CONV_INSPECT_FOLLOWUPS_HELP"],
    )
    # Labels here are the questions themselves, so render them full-opacity with a
    # bullet rather than as dimmed field names.
    st.markdown(
        kv_grid_html(rows, columns=2, dim_labels=False, label_prefix="· "),
        unsafe_allow_html=True,
    )
