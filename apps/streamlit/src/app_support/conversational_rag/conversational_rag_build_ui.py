"""Step 5 build management: the Build & launch button and the Builds list.

A "build" freezes the current Conversational RAG settings into a self-contained
session folder that can be relaunched as a read-only showcase. This module maps the
live controls to a :class:`BuildSnapshot`, freezes the effective prompts, and renders
the Builds section (each build's settings-file preview/download, delete, and the
reused Token usage panel). The pure mapping helpers are unit-tested; the ``render_*``
functions are thin Streamlit wrappers that reuse the shared file dialogs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from app_support.conversational_rag.build_manager import (
    BUILD_MANIFEST_FILENAME,
    SCHEMA_VERSION,
    BuildSnapshot,
    allocate_build_name,
    build_dir,
    create_build,
    format_built_at,
    list_builds,
    load_build,
    make_showcase_token,
)
from app_support.conversational_rag.conversational_prompts import (
    APP_MESSAGE_PROMPT_KEYS,
    CONVERSATIONAL_PROMPT_KEYS,
    ERROR_REPLY_PROMPT_KEY,
    FOLLOWUP_INTRO_PROMPT_KEY,
    NO_FOLLOWUPS_PROMPT_KEY,
    WELCOME_PROMPT_KEY,
    load_saved_conversational_prompt,
    resolve_app_message,
    resolve_conversational_prompt,
    save_conversational_prompt,
)
from app_support.conversational_rag.conversational_rag_form_ui import ConversationalControls
from app_support.conversational_rag.conversational_rag_history import (
    load_conversational_rag_history,
)
from app_support.conversational_rag.conversational_token_ui import (
    render_conversational_token_panel,
)
from app_support.conversational_rag.showcase_launch import render_launch_button
from app_support.i18n._types import Strings
from app_support.rag_shared.index_catalog import (
    IndexRef,
    embedding_model_of,
    list_session_indexes,
)
from app_support.settings import get_settings

__all__ = [
    "apply_pending_load",
    "control_widget_values",
    "frozen_prompt_texts",
    "load_build_as_controls",
    "render_build_launch_button",
    "render_builds_list",
    "snapshot_from_controls",
]

# App-message prompt key -> its localized default-text i18n key, so the effective
# greeting / error / follow-up messages are frozen into the build too.
_APP_MESSAGE_DEFAULT_KEYS = {
    WELCOME_PROMPT_KEY: "CHAT_WELCOME_DEFAULT",
    ERROR_REPLY_PROMPT_KEY: "CONV_ERROR_REPLY_DEFAULT",
    FOLLOWUP_INTRO_PROMPT_KEY: "CONV_FOLLOWUP_INTRO_DEFAULT",
    NO_FOLLOWUPS_PROMPT_KEY: "CONV_NO_FOLLOWUPS_DEFAULT",
}


def frozen_prompt_texts(strings: Strings, session_root: Path | str) -> dict[str, str]:
    """Resolve the effective 10 prompts (6 model + 4 app messages) to freeze."""
    texts = {
        key: resolve_conversational_prompt(key, session_root) for key in CONVERSATIONAL_PROMPT_KEYS
    }
    for key, default_key in _APP_MESSAGE_DEFAULT_KEYS.items():
        texts[key] = resolve_app_message(session_root, key, strings[default_key])
    return texts


def snapshot_from_controls(
    controls: ConversationalControls, *, language: str, name: str
) -> BuildSnapshot:
    """Map the live Step 5 controls to a persistable :class:`BuildSnapshot`."""
    return BuildSnapshot(
        schema_version=SCHEMA_VERSION,
        created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        name=name,
        language=language,
        answer_model=controls.answer_model,
        top_k=controls.top_k,
        tone=controls.tone,
        reranker=controls.reranker,
        aux_model_id=controls.aux_model_id,
        decomposition_limit=controls.decomposition_limit,
        followup_show_count=controls.followup_show_count,
        inspect=controls.inspect,
        followup_drop=controls.followup_drop,
        followup_keep=controls.followup_keep,
        followup_probe_k=controls.followup_probe_k,
        answerability_chunks=controls.answerability_chunks,
        state_summary_start_turn=controls.state_summary_start_turn,
        state_summary_max_words=controls.state_summary_max_words,
        answer_recent_turns=controls.answer_recent_turns,
        plan_recent_turns=controls.plan_recent_turns,
        index_vector_folder=controls.index.vector_folder,
        index_run_name=controls.index.run_name,
        embedding_model=embedding_model_of(controls.index),
    )


def load_build_as_controls(build_root: Path | str) -> ConversationalControls | None:
    """Reconstruct the frozen Step 5 controls from a build, for showcase rendering.

    Returns None when the build is unreadable or its copied index is missing, so the
    caller can show a friendly error instead of a broken chat.
    """
    snapshot = load_build(build_root)
    if snapshot is None:
        return None
    indexes = list_session_indexes(build_root)
    if not indexes:
        return None
    return ConversationalControls(
        index=indexes[0],
        answer_model=snapshot.answer_model,
        top_k=snapshot.top_k,
        tone=snapshot.tone,
        reranker=snapshot.reranker,
        aux_model_id=snapshot.aux_model_id,
        decomposition_limit=snapshot.decomposition_limit,
        followup_show_count=snapshot.followup_show_count,
        inspect=snapshot.inspect,
        followup_drop=snapshot.followup_drop,
        followup_keep=snapshot.followup_keep,
        followup_probe_k=snapshot.followup_probe_k,
        answerability_chunks=snapshot.answerability_chunks,
        state_summary_start_turn=snapshot.state_summary_start_turn,
        state_summary_max_words=snapshot.state_summary_max_words,
        answer_recent_turns=snapshot.answer_recent_turns,
        plan_recent_turns=snapshot.plan_recent_turns,
    )


_CONTROL_KEY_PREFIX = "conversational_rag"
# The just-built build, so the Builds list can expand + best-effort auto-open it.
_JUST_BUILT_KEY = "conversational_rag_just_built"
# Build awaiting the Load confirmation, then (once confirmed) awaiting application
# at the top of the next run — before the controls instantiate.
_LOAD_TRIGGER = "conversational_rag_pending_load"
_APPLY_LOAD_KEY = "conversational_rag_apply_load"


def control_widget_values(snapshot: BuildSnapshot) -> dict[str, object]:
    """Map a snapshot to the Step 5 control widget-state keys it should restore."""
    prefix = _CONTROL_KEY_PREFIX
    return {
        f"{prefix}_top_k": snapshot.top_k,
        f"{prefix}_llm_model": snapshot.answer_model,
        f"{prefix}_tone": snapshot.tone,
        f"{prefix}_reranker": snapshot.reranker,
        f"{prefix}_aux_model": snapshot.aux_model_id,
        f"{prefix}_decomposition": snapshot.decomposition_limit,
        f"{prefix}_plan_recent_turns": snapshot.plan_recent_turns,
        f"{prefix}_answer_recent_turns": snapshot.answer_recent_turns,
        f"{prefix}_followup_count": snapshot.followup_show_count,
        f"{prefix}_followup_probe_k": snapshot.followup_probe_k,
        f"{prefix}_answerability_chunks": snapshot.answerability_chunks,
        f"{prefix}_thresholds": (snapshot.followup_drop, snapshot.followup_keep),
        f"{prefix}_state_start_turn": snapshot.state_summary_start_turn,
        f"{prefix}_state_max_words": snapshot.state_summary_max_words,
        f"{prefix}_inspect": snapshot.inspect,
    }


def _matching_index(session_root: Path | str, snapshot: BuildSnapshot) -> IndexRef | None:
    """Return the live session index matching the snapshot's, if still present."""
    for ref in list_session_indexes(session_root):
        if (
            ref.vector_folder == snapshot.index_vector_folder
            and ref.run_name == snapshot.index_run_name
        ):
            return ref
    return None


def _apply_load(session_root: Path | str, snapshot: BuildSnapshot) -> None:
    """Write a build's settings + prompts into the live Step 5 control state.

    Runs before the controls instantiate (see ``apply_pending_load``): Streamlit
    forbids setting a widget's state key once its widget has rendered.
    """
    for key, value in control_widget_values(snapshot).items():
        st.session_state[key] = value
    st.session_state[f"{_CONTROL_KEY_PREFIX}_inspect_on"] = snapshot.inspect
    ref = _matching_index(session_root, snapshot)
    if ref is not None:
        st.session_state[f"{_CONTROL_KEY_PREFIX}_index"] = ref
    build_root = build_dir(session_root, snapshot.name)
    for key in (*CONVERSATIONAL_PROMPT_KEYS, *APP_MESSAGE_PROMPT_KEYS):
        text = load_saved_conversational_prompt(build_root, key)
        if text is not None:
            save_conversational_prompt(session_root, key, text)
            st.session_state[f"{_CONTROL_KEY_PREFIX}_prompt_{key}"] = text


def apply_pending_load(strings: Strings, session_root: Path | str) -> None:
    """Apply a confirmed Load at the top of the page, before the controls render."""
    name = str(st.session_state.pop(_APPLY_LOAD_KEY, ""))
    if not name:
        return
    snapshot = load_build(build_dir(session_root, name))
    if snapshot is None:
        return
    _apply_load(session_root, snapshot)
    st.toast(strings["CONV_BUILD_LOADED_TOAST"].format(name=name), icon=":material/check:")


def _build_now(
    strings: Strings, controls: ConversationalControls, session_root: Path | str, language: str
) -> str:
    """Freeze the current settings into a new build; return its folder name."""
    name = allocate_build_name(session_root)
    snapshot = snapshot_from_controls(controls, language=language, name=name)
    create_build(
        session_root, snapshot, controls.index.run_dir, frozen_prompt_texts(strings, session_root)
    )
    return name


def render_build_launch_button(
    strings: Strings,
    controls: ConversationalControls,
    session_root: Path | str,
    language: str,
    *,
    disabled: bool = False,
) -> None:
    """Render the primary Build & launch button beneath the conversation picker."""
    build_disabled = disabled or controls.index is None
    if st.button(
        strings["CONV_BUILD_LAUNCH_BUTTON"],
        icon=":material/rocket_launch:",
        type="primary",
        help=strings["CONV_BUILD_LAUNCH_HELP"],
        disabled=build_disabled,
        key="conversational_rag_build",
    ):
        name = _build_now(strings, controls, session_root, language)
        st.session_state[_JUST_BUILT_KEY] = name
        st.toast(strings["CONV_BUILD_CREATED_TOAST"].format(name=name), icon=":material/check:")
        st.rerun()


def render_builds_list(
    strings: Strings, session_root: Path | str, *, disabled: bool = False
) -> None:
    """Render the Builds section: one collapsible card list of saved builds, newest first."""
    builds = list_builds(session_root)
    if not builds:
        return
    just_built = str(st.session_state.pop(_JUST_BUILT_KEY, ""))
    with st.expander(
        strings["CONV_BUILDS_LABEL"], icon=":material/inventory_2:", expanded=bool(just_built)
    ):
        for snapshot in builds:
            _render_build_row(
                strings,
                snapshot,
                session_root,
                disabled=disabled,
                auto_open=snapshot.name == just_built,
            )
    _render_open_load_dialog(strings, session_root)


def _render_build_row(
    strings: Strings,
    snapshot: BuildSnapshot,
    session_root: Path | str,
    *,
    disabled: bool,
    auto_open: bool = False,
) -> None:
    with st.container(border=True):
        st.markdown(f"**{snapshot.name}**")
        st.caption(
            strings["CONV_BUILD_BUILT_AT"].format(when=format_built_at(snapshot.created_at_utc))
        )
        _launch_button(strings, snapshot, auto_open=auto_open)
        with st.container(horizontal=True, vertical_alignment="center", gap="xxsmall"):
            _export_button(strings, snapshot, disabled=disabled)
            _load_button(strings, snapshot, disabled=disabled)
            _preview_button(strings, snapshot, disabled=disabled)
            _download_button(strings, snapshot, session_root, disabled=disabled)
            _delete_button(strings, snapshot, disabled=disabled)
        records = load_conversational_rag_history(build_dir(session_root, snapshot.name))
        if records:
            render_conversational_token_panel(strings, records, key_suffix=f"_{snapshot.name}")


def _preview_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        "",
        icon=":material/visibility:",
        help=strings["CONV_BUILD_PREVIEW_HELP"],
        disabled=disabled,
        key=f"build_preview_{snapshot.name}",
    ):
        st.session_state.preview_file_relative_path = f"{snapshot.name}/{BUILD_MANIFEST_FILENAME}"
        st.rerun()


def _download_button(
    strings: Strings, snapshot: BuildSnapshot, session_root: Path | str, *, disabled: bool
) -> None:
    try:
        data = (build_dir(session_root, snapshot.name) / BUILD_MANIFEST_FILENAME).read_bytes()
    except OSError:
        return
    st.download_button(
        "",
        data=data,
        file_name=f"{snapshot.name}.json",
        mime="application/json",
        icon=":material/download:",
        help=strings["CONV_BUILD_DOWNLOAD_HELP"],
        disabled=disabled,
        key=f"build_download_{snapshot.name}",
    )


def _delete_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        "",
        icon=":material/delete:",
        help=strings["CONV_BUILD_DELETE_HELP"],
        disabled=disabled,
        key=f"build_delete_{snapshot.name}",
    ):
        st.session_state.delete_folder_relative_path = snapshot.name
        st.rerun()


def _export_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        "",
        icon=":material/archive:",
        help=strings["CONV_BUILD_EXPORT_HELP"],
        disabled=disabled,
        key=f"build_export_{snapshot.name}",
    ):
        st.session_state.export_folder_relative_path = snapshot.name
        st.session_state.pop("export_zip_payload", None)
        st.session_state.export_autoclicked = False
        st.rerun()


def _load_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        "",
        icon=":material/upload:",
        help=strings["CONV_BUILD_LOAD_HELP"],
        disabled=disabled,
        key=f"build_load_{snapshot.name}",
    ):
        st.session_state[_LOAD_TRIGGER] = snapshot.name
        st.rerun()


@st.dialog(" ")
def _load_confirm_dialog(strings: Strings, name: str) -> None:
    st.markdown(f"**{strings['CONV_BUILD_LOAD_TITLE']}**")
    st.write(strings["CONV_BUILD_LOAD_CONFIRM"].format(name=name))
    cancel_col, load_col = st.columns(2, vertical_alignment="center")
    with cancel_col:
        if st.button(strings["CONV_BUILD_LOAD_CANCEL"], width="stretch", key="build_load_cancel"):
            st.session_state.pop(_LOAD_TRIGGER, None)
            st.rerun()
    with load_col:
        if st.button(
            strings["CONV_BUILD_LOAD_CONFIRM_BUTTON"],
            type="primary",
            width="stretch",
            key="build_load_confirm",
        ):
            st.session_state[_APPLY_LOAD_KEY] = name
            st.session_state.pop(_LOAD_TRIGGER, None)
            st.rerun()


def _render_open_load_dialog(strings: Strings, session_root: Path | str) -> None:
    name = str(st.session_state.get(_LOAD_TRIGGER, ""))
    if not name:
        return
    if not build_dir(session_root, name).is_dir():
        st.session_state.pop(_LOAD_TRIGGER, None)
        return
    _load_confirm_dialog(strings, name)


def _launch_button(strings: Strings, snapshot: BuildSnapshot, *, auto_open: bool) -> None:
    session_id = str(st.session_state.get("session_id", ""))
    token = make_showcase_token(session_id, snapshot.name, get_settings().zip_signing_secret)
    render_launch_button(
        f"?show={token}",
        label=strings["CONV_BUILD_OPEN_LABEL"],
        help=strings["CONV_BUILD_OPEN_HELP"],
        key=f"build_launch_{snapshot.name}",
        auto_open=auto_open,
    )
