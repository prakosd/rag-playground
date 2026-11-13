"""Step 5 build management: the Build & launch button and per-build tree actions.

A "build" freezes the current Conversational RAG settings and all 10 prompts into a
single ``build.json`` that can be relaunched as a read-only showcase. This module maps
the live controls to a :class:`BuildSnapshot`, freezes the effective prompts, and
renders each build's actions (Export/Launch/Load/Delete + Token usage)
inside its Output Files tree folder. The pure mapping helpers are unit-tested; the
``render_*`` functions are thin Streamlit wrappers that reuse the shared file dialogs.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from app_support.conversational_rag.build_manager import (
    SCHEMA_VERSION,
    BuildSnapshot,
    allocate_build_name,
    allocate_showcase_slug,
    build_config_signature,
    build_dir,
    build_run_dir,
    create_build,
    load_build,
    newest_build,
)
from app_support.conversational_rag.conversational_prompts import (
    CONVERSATIONAL_PROMPT_KEYS,
    ERROR_REPLY_PROMPT_KEY,
    FOLLOWUP_INTRO_PROMPT_KEY,
    NO_FOLLOWUPS_PROMPT_KEY,
    WELCOME_PROMPT_KEY,
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
from app_support.conversational_rag.session_snapshot import (
    read_session_snapshot,
    snapshot_prompts,
    write_session_snapshot,
)
from app_support.conversational_rag.showcase_launch import render_launch_button
from app_support.i18n._types import Strings
from app_support.rag_shared.index_catalog import (
    IndexRef,
    embedding_model_of,
    list_session_indexes,
)

__all__ = [
    "apply_pending_load",
    "apply_session_snapshot",
    "control_widget_values",
    "frozen_prompt_texts",
    "load_build_as_controls",
    "render_build_launch_button",
    "render_build_load_dialog",
    "render_build_token_panel",
    "render_build_tree_actions",
    "resolve_build_index",
    "save_session_snapshot",
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
    controls: ConversationalControls,
    *,
    language: str,
    name: str,
    slug: str,
    prompts: dict[str, str],
) -> BuildSnapshot:
    """Map the live Step 5 controls + frozen prompts to a persistable :class:`BuildSnapshot`."""
    return BuildSnapshot(
        schema_version=SCHEMA_VERSION,
        created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        name=name,
        slug=slug,
        language=language,
        answer_model=controls.answer_model,
        top_k=controls.top_k,
        tone=controls.tone,
        reranker=controls.reranker,
        aux_model_id=controls.aux_model_id,
        decomposition_limit=controls.decomposition_limit,
        followup_show_count=controls.followup_show_count,
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
        prompts=dict(prompts),
        answer_temperature=controls.answer_temperature,
        injection_prevention=controls.injection_prevention,
    )


def save_session_snapshot(
    controls: ConversationalControls,
    session_root: Path | str,
    language: str,
) -> None:
    """Persist the live Step 5 settings as the session ``snapshot.json``, keeping prompt edits.

    Called after each committed turn so a reload — or importing the exported session into a
    fresh session/browser — restores the last-used options and index (the chat lives in
    ``transactions.jsonl``; prompt edits persist on Save). Only genuine prompt edits are kept
    (not every resolved prompt), so an un-edited prompt still resolves from the shipped config
    / library default. No-op without a selected index (nothing to snapshot).
    """
    if controls.index is None:
        return
    edits = snapshot_prompts(session_root)
    snapshot = snapshot_from_controls(controls, language=language, name="", slug="", prompts=edits)
    write_session_snapshot(session_root, dataclasses.asdict(snapshot))


def load_build_as_controls(build_root: Path | str) -> ConversationalControls | None:
    """Reconstruct the frozen Step 5 controls from a build, for showcase rendering.

    Returns None when the build is unreadable or its referenced index is missing, so
    the caller can show a friendly error instead of a broken chat.
    """
    snapshot = load_build(build_root)
    if snapshot is None:
        return None
    index = resolve_build_index(build_root, snapshot)
    if index is None:
        return None
    return ConversationalControls(
        index=index,
        answer_model=snapshot.answer_model,
        top_k=snapshot.top_k,
        tone=snapshot.tone,
        reranker=snapshot.reranker,
        aux_model_id=snapshot.aux_model_id,
        decomposition_limit=snapshot.decomposition_limit,
        followup_show_count=snapshot.followup_show_count,
        inspect=False,
        followup_drop=snapshot.followup_drop,
        followup_keep=snapshot.followup_keep,
        followup_probe_k=snapshot.followup_probe_k,
        answerability_chunks=snapshot.answerability_chunks,
        state_summary_start_turn=snapshot.state_summary_start_turn,
        state_summary_max_words=snapshot.state_summary_max_words,
        answer_recent_turns=snapshot.answer_recent_turns,
        plan_recent_turns=snapshot.plan_recent_turns,
        answer_temperature=snapshot.answer_temperature,
        injection_prevention=snapshot.injection_prevention,
    )


_CONTROL_KEY_PREFIX = "conversational_rag"
# The just-built build, so the Builds list can expand + best-effort auto-open it.
_JUST_BUILT_KEY = "conversational_rag_just_built"
# Build awaiting the Load confirmation, then (once confirmed) awaiting application
# at the top of the next run — before the controls instantiate.
_LOAD_TRIGGER = "conversational_rag_pending_load"
_APPLY_LOAD_KEY = "conversational_rag_apply_load"
# The session root the controls were last restored for, so apply_session_snapshot
# re-seeds when the active session changes but not on every rerun.
_SNAPSHOT_RESTORED_FOR_KEY = "conversational_rag_snapshot_restored_for"


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
        f"{prefix}_answer_temperature": snapshot.answer_temperature,
        f"{prefix}_injection_prevention": snapshot.injection_prevention,
        f"{prefix}_followup_count": snapshot.followup_show_count,
        f"{prefix}_followup_probe_k": snapshot.followup_probe_k,
        f"{prefix}_answerability_chunks": snapshot.answerability_chunks,
        f"{prefix}_thresholds": (snapshot.followup_drop, snapshot.followup_keep),
        f"{prefix}_state_start_turn": snapshot.state_summary_start_turn,
        f"{prefix}_state_max_words": snapshot.state_summary_max_words,
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


def resolve_build_index(build_root: Path | str, snapshot: BuildSnapshot) -> IndexRef | None:
    """Resolve the index a build uses.

    Prefers the shared index still living in the build's owner session (the current
    reference model — builds point at the session's index rather than copying it),
    and falls back to an index copied inside the build for older self-contained
    builds. Returns None when neither is present.
    """
    root = Path(build_root)
    shared = _matching_index(root.parent, snapshot)
    if shared is not None:
        return shared
    run_dir = build_run_dir(root)
    if run_dir is None:
        return None
    copied = list_session_indexes(run_dir)
    return copied[0] if copied else None


def _seed_options_and_index(session_root: Path | str, snapshot: BuildSnapshot) -> None:
    """Seed the option control widgets + the matching index from *snapshot* into session state.

    Shared by the build Load and the session-snapshot restore; both must run before the
    controls instantiate (Streamlit forbids setting a widget's state key after it renders).
    """
    for key, value in control_widget_values(snapshot).items():
        st.session_state[key] = value
    ref = _matching_index(session_root, snapshot)
    if ref is not None:
        st.session_state[f"{_CONTROL_KEY_PREFIX}_index"] = ref


def _apply_load(session_root: Path | str, snapshot: BuildSnapshot) -> None:
    """Write a build's settings + frozen prompts into the live Step 5 control state.

    Runs before the controls instantiate (see ``apply_pending_load``): Streamlit
    forbids setting a widget's state key once its widget has rendered. Prompts come
    from the snapshot (build.json), not disk.
    """
    _seed_options_and_index(session_root, snapshot)
    for key, text in snapshot.prompts.items():
        if text and text.strip():
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


def apply_session_snapshot(session_root: Path | str) -> None:
    """Seed the Step 5 controls from the session's ``snapshot.json`` at the top of the page.

    Runs before the controls instantiate (Streamlit forbids setting a widget's state key
    once its widget has rendered) and only re-seeds when the active session changes — so a
    reload or a switched-to/imported session restores its last-used options and index
    without clobbering live edits on later reruns. Prompts restore lazily via
    ``resolve_conversational_prompt``, so only the option widgets + index need seeding.
    """
    if st.session_state.get(_SNAPSHOT_RESTORED_FOR_KEY) == str(session_root):
        return
    st.session_state[_SNAPSHOT_RESTORED_FOR_KEY] = str(session_root)
    snapshot = BuildSnapshot.from_dict(read_session_snapshot(session_root))
    if snapshot is None:
        return
    _seed_options_and_index(session_root, snapshot)


def _build_now(
    strings: Strings, controls: ConversationalControls, session_root: Path | str, language: str
) -> str:
    """Freeze the current settings into a new build; return its folder name."""
    name = allocate_build_name(session_root)
    slug = allocate_showcase_slug(Path(session_root).parent)
    prompts = frozen_prompt_texts(strings, session_root)
    snapshot = snapshot_from_controls(
        controls, language=language, name=name, slug=slug, prompts=prompts
    )
    create_build(session_root, snapshot)
    return name


def _current_build_snapshot(
    strings: Strings, controls: ConversationalControls, session_root: Path | str, language: str
) -> BuildSnapshot:
    """Freeze the live controls + prompts into a snapshot for signature comparison.

    Name/slug are placeholders — ``build_config_signature`` ignores them.
    """
    prompts = frozen_prompt_texts(strings, session_root)
    return snapshot_from_controls(controls, language=language, name="", slug="", prompts=prompts)


def render_build_launch_button(
    strings: Strings,
    controls: ConversationalControls,
    session_root: Path | str,
    language: str,
    *,
    disabled: bool = False,
) -> None:
    """Render the primary build control beneath the conversation picker.

    Shows 'Launch' (re-open the most recent build) while the live settings, prompts,
    and index still match that build, so a click can't create a duplicate; any change
    flips it back to 'Build & launch', which freezes a new build.
    """
    build_disabled = disabled or controls.index is None
    latest = None if build_disabled else newest_build(session_root)
    if latest is not None and build_config_signature(
        _current_build_snapshot(strings, controls, session_root, language)
    ) == build_config_signature(latest):
        _render_relaunch_button(strings, latest, disabled=build_disabled)
        return
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


def _render_relaunch_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    """Re-open the most recent build's showcase, reusing the just-built auto-open path."""
    if st.button(
        strings["CONV_BUILD_RELAUNCH_BUTTON"],
        icon=":material/rocket_launch:",
        type="primary",
        help=strings["CONV_BUILD_RELAUNCH_HELP"].format(name=snapshot.name),
        disabled=disabled,
        key="conversational_rag_build",
    ):
        st.session_state[_JUST_BUILT_KEY] = snapshot.name
        st.toast(
            strings["CONV_BUILD_RELAUNCH_TOAST"].format(name=snapshot.name),
            icon=":material/rocket_launch:",
        )
        st.rerun()


def render_build_token_panel(strings: Strings, session_root: Path | str, name: str) -> None:
    """Render a build's Token usage panel from its showcase chat history, if any.

    Rendered in the Output Files tree right after the build's ``conversational_rag``
    folder (the content it summarizes), above the build's action row. No-op for a build
    with no run dir or no recorded conversations.
    """
    run_dir = build_run_dir(build_dir(session_root, name))
    if run_dir is None:
        return
    records = load_conversational_rag_history(run_dir)
    if records:
        render_conversational_token_panel(strings, records, key_suffix=f"_{name}")


def render_build_tree_actions(
    strings: Strings, session_root: Path | str, name: str, *, disabled: bool = False
) -> None:
    """Render a build's action row inside its Output Files tree folder.

    The run-folder tree already lists build.json (with its own preview/download) and the
    showcase chat history; :func:`render_build_token_panel` adds the Token-usage panel just
    under that history, and this adds the Export/Launch/Load/Rename/Delete action row.
    """
    build_root = build_dir(session_root, name)
    snapshot = load_build(build_root)
    run_dir = build_run_dir(build_root)
    if snapshot is None or run_dir is None:
        return
    # The just-built build auto-opens its showcase tab once (set by the Build button).
    just_built = st.session_state.get(_JUST_BUILT_KEY) == name
    if just_built:
        st.session_state.pop(_JUST_BUILT_KEY, None)
    with st.container(horizontal=True, vertical_alignment="center", width="content", gap="xxsmall"):
        _export_button(strings, snapshot, disabled=disabled)
        _launch_button(strings, snapshot, auto_open=just_built)
        _load_button(strings, snapshot, disabled=disabled)
        _rename_button(strings, snapshot, disabled=disabled)
        _delete_button(strings, snapshot, disabled=disabled)


def _rename_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        strings["FILES_RENAME_FOLDER_BUTTON"],
        icon=":material/edit:",
        help=strings["FILES_RENAME_FOLDER_HELP"].format(folder=snapshot.name),
        disabled=disabled,
        key=f"rename_folder_build_{snapshot.name}",
    ):
        # The shared rename dialog (downloads_ui) resets + auto-selects on a fresh open,
        # so setting the path is enough; build folders route through rename_build there.
        st.session_state.rename_folder_relative_path = snapshot.name
        st.rerun()


def _delete_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        strings["FILES_DELETE_FOLDER_BUTTON"],
        icon=":material/delete_forever:",
        help=strings["CONV_BUILD_DELETE_HELP"],
        disabled=disabled,
        # The delete_folder_ key prefix inherits the shared red styling (downloads_ui).
        key=f"delete_folder_build_{snapshot.name}",
    ):
        st.session_state.delete_folder_relative_path = snapshot.name
        st.rerun()


def _export_button(strings: Strings, snapshot: BuildSnapshot, *, disabled: bool) -> None:
    if st.button(
        strings["FILES_DOWNLOAD_ZIP_BUTTON"],
        width="content",
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
        strings["CONV_BUILD_LOAD_LABEL"],
        icon=":material/settings_backup_restore:",
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


def render_build_load_dialog(strings: Strings, session_root: Path | str) -> None:
    """Show the Load-confirm dialog when a build's Load button set the trigger."""
    name = str(st.session_state.get(_LOAD_TRIGGER, ""))
    if not name:
        return
    if not build_dir(session_root, name).is_dir():
        st.session_state.pop(_LOAD_TRIGGER, None)
        return
    _load_confirm_dialog(strings, name)


def _launch_button(strings: Strings, snapshot: BuildSnapshot, *, auto_open: bool) -> None:
    render_launch_button(
        f"?showcase={snapshot.slug}",
        label=strings["CONV_BUILD_OPEN_LABEL"],
        help=strings["CONV_BUILD_OPEN_HELP"],
        key=f"build_launch_{snapshot.name}",
        auto_open=auto_open,
    )
