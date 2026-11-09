"""Downloads / Output-Files UI for the Streamlit app.

Renders the Output Files panel: the download tree (per-file download + preview,
per-folder zip export + delete), the signed-zip import dialog, the ready-result
download panel, and the file-preview modal. Extracted from ``streamlit_app.py``
so the shell keeps only navigation, session, and job orchestration. Shared
constants and shell helpers come from ``app_runtime`` (no import cycle: nothing
here imports ``streamlit_app``). ``st.session_state`` is a global singleton, so
these renderers read/write the same state the shell owns.
"""

from __future__ import annotations

import html
import mimetypes
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st
from artifact_store.archives import verify_zip_bytes
from artifact_store.naming import VECTOR_FOLDER_PREFIX

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _DOWNLOAD_LIMIT_BYTES,
    _DOWNLOADS_REFRESH_INTERVAL,
    _ICON_BUTTON_WIDTH_PX,
    _PREVIEW_DIALOG_CONTENT_KEY,
    _PREVIEW_DIALOG_SCOPE_CLASS,
    _PREVIEW_DIALOG_VIEWPORT_HEIGHT,
    _PREVIEW_DIALOG_VIEWPORT_WIDTH,
    _PREVIEW_DIALOG_WIDTH,
    _PREVIEW_LIMIT_BYTES,
    _PREVIEW_LIMIT_KIB,
    _STATUS_ROW_STYLE,
    _UTC_DISPLAY_FORMAT,
    _auto_refresh_fragment,
    _cached_download_tree,
    _cached_list_generated_files,
    _crawl_job_active,
    _files_actions_busy,
    _job_is_alive,
    _session_root,
    _vector_job_active,
)
from app_support.conversational_rag.build_manager import (
    BuildSnapshot,
    build_run_dir,
    builds_referencing_folder,
    is_build_name,
    load_build,
    rename_build,
)
from app_support.conversational_rag.conversational_rag_build_ui import (
    render_build_token_panel,
    render_build_tree_actions,
    resolve_build_index,
)
from app_support.dialog_ui import (
    SCROLLABLE_DIALOG_CONTENT_HEIGHT_PX,
    enter_submits_confirm_css,
    render_confirm_dialog,
    render_notice_dialog,
    scrollable_dialog_css,
)
from app_support.focus import click_widget, select_widget_text
from app_support.generated_files import (
    build_folder_zip_bytes,
    collapse_artifact_run_folder,
    delete_generated_folder,
    download_folder_icon,
    download_tree_entry_sort_key,
    files_excluding,
    find_site_graph_file,
    find_site_graph_for_result,
    format_file_size,
    format_history_folder_label,
    generated_files_cache_token,
    history_exists,
    import_history_zip,
    import_sample_fixture,
    import_signed_zip,
    import_target_name,
    is_build_folder,
    is_history_folder,
    is_run_folder,
    list_sample_fixtures,
    rename_generated_folder,
    run_folder_label_split,
    zip_top_folder,
)
from app_support.i18n import get_strings
from app_support.settings import get_settings
from app_support.site_graph_3d.launcher import render_explore_3d_button
from app_support.support import (
    GeneratedFile,
    ReadyDownload,
    build_ready_download,
    ensure_within_root,
    find_ready_download_in_session,
    is_text_previewable,
    preview_created_timestamp,
    read_text_preview,
)

# Session-state keys for the rename-folder dialog (input value, inline error, one-shot
# "select the prefilled text" flag).
_RENAME_INPUT_KEY = "rename_folder_label_input"
_RENAME_ERROR_KEY = "rename_folder_error"
_RENAME_SELECT_KEY = "rename_folder_select_pending"
# Tracks which folder the rename dialog last opened for, so a fresh open resets the
# input/error and auto-selects — letting any trigger (folder or build button) just set
# ``rename_folder_relative_path`` (like the delete flow) without cross-module coupling.
_RENAME_OPENED_FOR_KEY = "rename_folder_opened_for"
# Tracks which folder the export dialog has already deferred its zip build for, so the
# first run reruns immediately (fast, no block) and the (possibly slow) build runs on the
# next run — a dialog that blocks on its first run lets the previous dialog's elements
# linger as a ghost (streamlit#10907). Cleared on dismiss.
_EXPORT_PAINTED_KEY = "export_dialog_painted_for"


def _format_preview_timestamp_utc(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).strftime(_UTC_DISPLAY_FORMAT)
    except (OverflowError, OSError, ValueError):
        return None


def _preview_caption_html(
    path_text: str, size_text: str, modified_text: str | None, created_text: str | None
) -> str:
    """Build the preview dialog's caption rows with every value HTML-escaped.

    The path row carries the file's crawler- or import-derived relative path, so each
    value is escaped before embedding to stop a crafted filename injecting markup.
    """
    rows = (
        f'<div style="{_STATUS_ROW_STYLE}"><span>{html.escape(path_text)}</span>'
        f"<span>{html.escape(size_text)}</span></div>"
    )
    if modified_text and created_text:
        rows += (
            f'<div style="{_STATUS_ROW_STYLE}"><span>{html.escape(modified_text)}</span>'
            f"<span>{html.escape(created_text)}</span></div>"
        )
    elif modified_text:
        rows += f"<div>{html.escape(modified_text)}</div>"
    elif created_text:
        rows += f"<div>{html.escape(created_text)}</div>"
    return rows


def _on_preview_dismiss() -> None:
    st.session_state.preview_file_relative_path = ""


@st.dialog(
    _DIALOG_PLACEHOLDER_TITLE,
    width=_PREVIEW_DIALOG_WIDTH,
    on_dismiss=_on_preview_dismiss,
)
def _file_preview_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    session_folder = _session_root()
    try:
        file_path = ensure_within_root(session_folder, session_folder / preview_relative_path)
    except ValueError:
        st.session_state.preview_file_relative_path = ""
        return
    file_name = Path(preview_relative_path).name
    st.markdown(
        scrollable_dialog_css(
            _PREVIEW_DIALOG_SCOPE_CLASS,
            _PREVIEW_DIALOG_CONTENT_KEY,
            width=_PREVIEW_DIALOG_VIEWPORT_WIDTH,
            height=_PREVIEW_DIALOG_VIEWPORT_HEIGHT,
        ),
        unsafe_allow_html=True,
    )
    st.subheader(file_name)
    if not file_path.exists() or not file_path.is_file():
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    if not is_text_previewable(file_name):
        st.info(strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file_name))
        return
    try:
        current_stat = file_path.stat()
    except OSError:
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    current_size = current_stat.st_size

    path_text = strings["FILES_PREVIEW_PATH"].format(path=preview_relative_path)
    size_text = strings["FILES_PREVIEW_SIZE"].format(size_kib=round(current_size / 1024, 1))
    modified_display = _format_preview_timestamp_utc(current_stat.st_mtime)
    modified_text = (
        strings["FILES_PREVIEW_MODIFIED_AT"].format(value=modified_display)
        if modified_display
        else None
    )

    created_timestamp = preview_created_timestamp(current_stat)
    created_display = _format_preview_timestamp_utc(created_timestamp)
    created_text = (
        strings["FILES_PREVIEW_CREATED_AT"].format(value=created_display)
        if created_display
        else None
    )

    st.caption(
        _preview_caption_html(path_text, size_text, modified_text, created_text),
        unsafe_allow_html=True,
    )

    try:
        preview = read_text_preview(file_path, max_bytes=_PREVIEW_LIMIT_BYTES)
    except OSError:
        st.warning(strings["FILES_PREVIEW_READ_ERROR"].format(file=preview_relative_path))
        return

    with st.container(
        height=SCROLLABLE_DIALOG_CONTENT_HEIGHT_PX,
        border=False,
        key=_PREVIEW_DIALOG_CONTENT_KEY,
    ):
        if preview.text:
            st.code(
                preview.text,
                language="text",
                line_numbers=True,
                wrap_lines=False,
            )
        else:
            st.info(strings["FILES_PREVIEW_EMPTY"].format(file=file_name))
        if preview.truncated:
            st.caption(strings["FILES_PREVIEW_TRUNCATED"].format(limit_kib=_PREVIEW_LIMIT_KIB))


def _on_delete_folder_dismiss() -> None:
    st.session_state.delete_folder_relative_path = ""


def _builds_blocking_index_delete(
    session_root: Path | str, relative_path: str
) -> list[BuildSnapshot]:
    """Return Step 5 builds referencing the vector index at *relative_path*.

    Guards only a top-level vector-index folder delete; other deletes (crawl runs,
    builds, nested paths) are never blocked. Derived by scanning the session's
    builds, so it is always current.
    """
    name = relative_path.strip("/")
    if "/" in name or not name.startswith(VECTOR_FOLDER_PREFIX):
        return []
    return builds_referencing_folder(session_root, name)


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_delete_folder_dismiss)
def _delete_folder_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    relative_path = str(st.session_state.get("delete_folder_relative_path", ""))
    if not relative_path:
        return
    folder_name = Path(relative_path).name

    def _cancel() -> None:
        st.session_state.delete_folder_relative_path = ""
        st.rerun()

    blocking = _builds_blocking_index_delete(_session_root(), relative_path)
    if blocking:
        render_notice_dialog(
            title=strings["FILES_DELETE_BLOCKED_TITLE"],
            body=strings["FILES_DELETE_BLOCKED_BODY"].format(count=len(blocking)),
            items=[
                strings["FILES_DELETE_BLOCKED_ITEM"].format(name=snapshot.name, slug=snapshot.slug)
                for snapshot in blocking
            ],
            close_label=strings["FILES_DELETE_BLOCKED_CLOSE"],
            # Key must avoid the "delete_folder_" prefix: the red-delete CSS (see the
            # st.markdown block below) substring-matches it and would turn this primary
            # button's text dark-red-on-red. Keep it readable (white-on-primary).
            close_key="blocked_index_delete_close",
            on_close=_cancel,
        )
        return

    render_confirm_dialog(
        title=strings["FILES_DELETE_FOLDER_DIALOG_TITLE"],
        body=strings["FILES_DELETE_FOLDER_DIALOG_BODY"].format(folder=folder_name),
        body_as_warning=True,
        cancel_label=strings["FILES_DELETE_DIALOG_CANCEL"],
        cancel_key="delete_folder_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["FILES_DELETE_FOLDER_DIALOG_CONFIRM"],
        confirm_key="delete_folder_confirm_button",
        confirm_icon=":material/delete_forever:",
        on_confirm=lambda: _delete_folder(relative_path),
    )


def _delete_folder(relative_path: str) -> None:
    session_folder = _session_root()
    try:
        deleted = delete_generated_folder(session_folder, relative_path)
    except (OSError, ValueError):
        deleted = False
    st.session_state.delete_folder_relative_path = ""
    if deleted:
        prefix = f"{relative_path}/"
        preview_path = str(st.session_state.get("preview_file_relative_path", ""))
        if preview_path == relative_path or preview_path.startswith(prefix):
            st.session_state.preview_file_relative_path = ""
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _clear_rename_state() -> None:
    """Clear the rename dialog's session state (callback-safe — no rerun).

    Used for Cancel (``on_click``) and dialog dismiss (``on_dismiss``), which both rerun
    on their own; the fresh-open guard re-seeds the input on the next open.
    """
    st.session_state.rename_folder_relative_path = ""
    st.session_state.pop(_RENAME_ERROR_KEY, None)
    st.session_state.pop(_RENAME_OPENED_FOR_KEY, None)


def _close_rename() -> None:
    """Close the rename dialog from a render context (blocked notice / early return)."""
    _clear_rename_state()
    st.rerun()


def _reset_after_rename(relative_path: str) -> None:
    """Clear all rename state after a successful rename (more than cancel: it also drops
    the typed input and any stale preview of a file under the renamed folder)."""
    _clear_rename_state()
    st.session_state.pop(_RENAME_INPUT_KEY, None)
    preview_path = str(st.session_state.get("preview_file_relative_path", ""))
    if preview_path == relative_path or preview_path.startswith(f"{relative_path}/"):
        st.session_state.preview_file_relative_path = ""
    _cached_list_generated_files.clear()
    _cached_download_tree.clear()


def _apply_rename(relative_path: str) -> None:
    """Apply the rename from the Confirm form-submit, running in the render context.

    Running here (a form submit, not an ``on_click`` callback) lets a successful rename
    ``st.rerun()`` to close the modal cleanly instead of leaving a blank dialog behind;
    an invalid/duplicate label sets the inline error and reruns so the dialog re-renders
    with it. The form batches the field + submit, so there is no two-click issue.
    """
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    new_label = str(st.session_state.get(_RENAME_INPUT_KEY, ""))
    # Build folders store their name in build.json, so route them through rename_build
    # (which keeps that field in sync); crawl/vector folders use the plain dir rename.
    is_build = is_build_folder(Path(relative_path).name)
    try:
        if is_build:
            rename_build(_session_root(), relative_path, new_label)
        else:
            rename_generated_folder(_session_root(), relative_path, new_label)
    except FileExistsError as exc:
        st.session_state[_RENAME_ERROR_KEY] = strings["FILES_RENAME_DUPLICATE_ERROR"].format(
            name=str(exc)
        )
    except (OSError, ValueError):
        st.session_state[_RENAME_ERROR_KEY] = strings["FILES_RENAME_INVALID_ERROR"]
    else:
        _reset_after_rename(relative_path)
    st.rerun()


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_clear_rename_state)
def _rename_folder_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    relative_path = str(st.session_state.get("rename_folder_relative_path", ""))
    if not relative_path:
        return

    # A referenced vector index's full name still changes, so block it like delete does
    # (reusing the delete-blocked item/close strings).
    blocking = _builds_blocking_index_delete(_session_root(), relative_path)
    if blocking:
        render_notice_dialog(
            title=strings["FILES_RENAME_BLOCKED_TITLE"],
            body=strings["FILES_RENAME_BLOCKED_BODY"].format(count=len(blocking)),
            items=[
                strings["FILES_DELETE_BLOCKED_ITEM"].format(name=snapshot.name, slug=snapshot.slug)
                for snapshot in blocking
            ],
            close_label=strings["FILES_DELETE_BLOCKED_CLOSE"],
            close_key="rename_folder_blocked_close",
            on_close=_close_rename,
        )
        return

    split = run_folder_label_split(Path(relative_path).name)
    if split is None:  # not a numbered run folder — nothing safe to rename
        _close_rename()
        return
    locked, current_label = split

    # A fresh open (first render for this folder) resets any stale typed value/error from a
    # previous rename and arms the auto-select, so a trigger only needs to set the path.
    if st.session_state.get(_RENAME_OPENED_FOR_KEY) != relative_path:
        st.session_state[_RENAME_OPENED_FOR_KEY] = relative_path
        st.session_state.pop(_RENAME_INPUT_KEY, None)
        st.session_state.pop(_RENAME_ERROR_KEY, None)
        st.session_state[_RENAME_SELECT_KEY] = True

    confirm_key = "rename_folder_confirm_button"
    st.subheader(strings["FILES_RENAME_FOLDER_DIALOG_TITLE"])
    # A form so Enter submits the single-line field and the Confirm handler runs in the
    # render context (not an on_click callback): a successful rename then st.rerun()s to
    # close the modal cleanly instead of leaving a blank dialog, and the form batches the
    # field + submit so there is no two-click issue.
    with st.form("rename_folder_form", enter_to_submit=True, border=False):
        # Show the locked <prefix>NN_ inline before the field (centred, hugging it) so it
        # is clear it stays; only the trailing label is editable.
        with st.container(horizontal=True, vertical_alignment="center", gap=None):
            st.markdown(f"**{locked}**")
            st.text_input(
                strings["FILES_RENAME_FOLDER_INPUT_LABEL"],
                value=current_label,
                key=_RENAME_INPUT_KEY,
                label_visibility="collapsed",
            )
        error = st.session_state.get(_RENAME_ERROR_KEY)
        if error:
            st.error(error)
        # Enter-to-submit fires the FIRST submit button in element-tree order, so Confirm must
        # live in the first column (col[0]) — otherwise Enter triggers Cancel and dismisses the
        # dialog without renaming. The row is then visually reversed (enter_submits_confirm_css)
        # so Cancel still reads left and Confirm right, like the other confirm dialogs.
        st.markdown(enter_submits_confirm_css(confirm_key), unsafe_allow_html=True)
        action_cols = st.columns(2)
        with action_cols[0], st.container(horizontal_alignment="right"):
            confirm = st.form_submit_button(
                strings["FILES_RENAME_FOLDER_DIALOG_CONFIRM"],
                type="primary",
                icon=":material/edit:",
                key=confirm_key,
            )
        with action_cols[1]:
            cancel = st.form_submit_button(
                strings["FILES_RENAME_FOLDER_DIALOG_CANCEL"],
                key="rename_folder_cancel_button",
            )
    if st.session_state.pop(_RENAME_SELECT_KEY, False):
        select_widget_text(_RENAME_INPUT_KEY)  # once, on open: prefilled text starts selected
    if cancel:
        _clear_rename_state()
        st.rerun()
    if confirm:
        _apply_rename(relative_path)


def _render_open_rename_folder_dialog() -> None:
    rename_path = str(st.session_state.get("rename_folder_relative_path", ""))
    if not rename_path:
        return
    if not (_session_root() / rename_path).is_dir():
        st.session_state.rename_folder_relative_path = ""
        return
    _rename_folder_confirmation_dialog()


def _render_file_preview_button(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    previewable = is_text_previewable(file.name)
    preview_help = (
        strings["FILES_PREVIEW_HELP"].format(file=file.name)
        if previewable
        else strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file.name)
    )
    if st.button(
        label=strings["FILES_PREVIEW_BUTTON"],
        width=_ICON_BUTTON_WIDTH_PX,
        key=f"preview_{st.session_state.session_id}_{file.relative_path}",
        help=preview_help,
        disabled=_files_actions_busy() or not previewable,
    ):
        st.session_state.preview_file_relative_path = file.relative_path
        st.rerun()


def _render_folder_zip_button(relative_path: str) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    folder_name = Path(relative_path).name
    # Nothing is built on render: a folder zip reads and compresses every file
    # (heavy for vector indexes), and st.download_button needs the bytes upfront.
    # Clicking opens a modal that builds it on demand and auto-starts the
    # download, so the file tree stays fast and low-memory even with big indexes.
    if st.button(
        strings["FILES_DOWNLOAD_ZIP_BUTTON"],
        width="content",
        key=f"export_zip_{st.session_state.session_id}_{relative_path}",
        help=strings["FILES_DOWNLOAD_ZIP_HELP"].format(folder=folder_name),
        disabled=_files_actions_busy(),
    ):
        st.session_state.export_folder_relative_path = relative_path
        st.session_state.pop("export_zip_payload", None)
        st.session_state.export_autoclicked = False
        st.rerun()


def _build_index_export_dirs(session_root: Path | str, relative_path: str) -> dict[str, Path]:
    """Map an archive prefix → the build's referenced-index source dir.

    Lets a build export re-bundle a fresh copy of its shared index so the zip stays
    self-contained and re-imports as a standalone build. Empty for non-build folders
    and for older builds that already carry a copied index (already in the zip).
    """
    name = relative_path.strip("/")
    if "/" in name or not is_build_name(name):
        return {}
    build_root = Path(session_root) / name
    snapshot = load_build(build_root)
    run_dir = build_run_dir(build_root)
    if snapshot is None or run_dir is None:
        return {}
    index = resolve_build_index(build_root, snapshot)
    if index is None or Path(index.run_dir).resolve().is_relative_to(build_root.resolve()):
        return {}
    arc_prefix = f"{name}/{run_dir.name}/{snapshot.index_vector_folder}/{snapshot.index_run_name}"
    return {arc_prefix: index.run_dir}


def _on_export_dismiss() -> None:
    st.session_state.export_folder_relative_path = ""
    st.session_state.pop("export_zip_payload", None)
    st.session_state.pop("export_autoclicked", None)
    st.session_state.pop(_EXPORT_PAINTED_KEY, None)


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_export_dismiss)
def _export_folder_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    relative_path = str(st.session_state.get("export_folder_relative_path", ""))
    if not relative_path:
        return
    folder_name = Path(relative_path).name

    # Build once and reuse across the dialog's reruns (bounded: cleared on dismiss), so the
    # auto-click rerun never rebuilds the zip. The build can be slow (big indexes); blocking
    # on it during this dialog's first run lets Streamlit leave a just-dismissed dialog's
    # elements on screen as a ghost (streamlit#10907). So on the first run just mark the
    # dialog painted and rerun (fast, no block); the zip build is deferred to the next run.
    payload = st.session_state.get("export_zip_payload")
    if not isinstance(payload, dict) or payload.get("relative_path") != relative_path:
        if st.session_state.get(_EXPORT_PAINTED_KEY) != relative_path:
            st.session_state[_EXPORT_PAINTED_KEY] = relative_path
            st.rerun()
        session_folder = _session_root()
        with st.spinner(strings["FILES_EXPORT_PREPARING"].format(folder=folder_name)):
            try:
                zip_bytes = build_folder_zip_bytes(
                    session_folder,
                    relative_path,
                    signing_secret=get_settings().zip_signing_secret,
                    extra_dirs=_build_index_export_dirs(session_folder, relative_path),
                )
            except (OSError, ValueError):
                st.error(strings["FILES_DOWNLOAD_ZIP_TOO_LARGE"].format(folder=folder_name))
                return
        payload = {"relative_path": relative_path, "bytes": zip_bytes}
        st.session_state.export_zip_payload = payload
        st.session_state.export_autoclicked = False

    zip_bytes = payload["bytes"]
    if len(zip_bytes) > _DOWNLOAD_LIMIT_BYTES:
        st.warning(strings["FILES_DOWNLOAD_ZIP_TOO_LARGE"].format(folder=folder_name))
        return

    download_key = f"export_download_{relative_path}"
    st.download_button(
        label=strings["FILES_DOWNLOAD_ZIP_BUTTON"],
        data=zip_bytes,
        file_name=f"{folder_name}.zip",
        mime="application/zip",
        width="stretch",
        key=download_key,
        help=strings["FILES_DOWNLOAD_ZIP_HELP"].format(folder=folder_name),
    )
    st.caption(strings["FILES_EXPORT_DOWNLOAD_STARTED"])
    # Auto-start the download once. The click triggers a rerun, so re-injecting
    # the click script would loop — guard it behind a one-shot flag. The visible
    # button above remains as a manual fallback if the browser blocks the click.
    if not st.session_state.get("export_autoclicked"):
        st.session_state.export_autoclicked = True
        click_widget(download_key)


def _render_open_export_dialog() -> None:
    export_path = str(st.session_state.get("export_folder_relative_path", ""))
    if not export_path:
        return
    if not (_session_root() / export_path).is_dir():
        _on_export_dismiss()
        return
    _export_folder_dialog()


def _render_folder_rename_button(relative_path: str) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    folder_name = Path(relative_path).name
    if st.button(
        label=strings["FILES_RENAME_FOLDER_BUTTON"],
        icon=":material/edit:",
        key=f"rename_folder_{st.session_state.session_id}_{relative_path}",
        help=strings["FILES_RENAME_FOLDER_HELP"].format(folder=folder_name),
        disabled=_files_actions_busy(),
    ):
        # The dialog resets its input/error + auto-selects on a fresh open (see
        # _RENAME_OPENED_FOR_KEY), so the trigger only sets the path, like delete.
        st.session_state.rename_folder_relative_path = relative_path
        st.rerun()


def _render_folder_delete_button(relative_path: str) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    folder_name = Path(relative_path).name
    if st.button(
        label=strings["FILES_DELETE_FOLDER_BUTTON"],
        icon=":material/delete_forever:",
        key=f"delete_folder_{st.session_state.session_id}_{relative_path}",
        help=strings["FILES_DELETE_FOLDER_HELP"].format(folder=folder_name),
        disabled=_files_actions_busy(),
    ):
        st.session_state.delete_folder_relative_path = relative_path
        st.rerun()


def render_generated_file_download(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    try:
        current_size = file.path.stat().st_size
    except OSError:
        return
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        width="content",
        gap="xxsmall",
    ):
        _render_file_preview_button(file)
        size_label = format_file_size(current_size)
        if not file.download_allowed or current_size > _DOWNLOAD_LIMIT_BYTES:
            st.button(
                label=f"📄 {file.name} • {size_label}",
                disabled=True,
                help=strings["FILES_DOWNLOAD_TOO_LARGE"].format(file=file.name),
                key=f"download_blocked_{st.session_state.session_id}_{file.relative_path}",
            )
        else:
            mime_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            with file.path.open("rb") as file_obj:
                file_bytes = file_obj.read()
            st.download_button(
                label=f"📄 {file.name} • {size_label}",
                data=file_bytes,
                file_name=file.name,
                mime=mime_type,
                key=f"download_{st.session_state.session_id}_{file.relative_path}",
                disabled=_files_actions_busy(),
            )


def render_download_tree(
    tree: Mapping[str, Any],
    *,
    allow_run_folder_collapse: bool = True,
    after_history_hook: Callable[[], None] | None = None,
) -> None:
    entries = sorted(
        tree.items(),
        key=lambda item: download_tree_entry_sort_key(
            item[0],
            item[1],
            top_level=allow_run_folder_collapse,
        ),
    )
    for name, entry in entries:
        if isinstance(entry, dict):
            folder_label = name
            folder_node: Mapping[str, Any] = entry
            if allow_run_folder_collapse:
                if is_history_folder(name):
                    folder_label = format_history_folder_label(name, entry)
                else:
                    folder_label, folder_node = collapse_artifact_run_folder(name, entry)
            is_build = allow_run_folder_collapse and is_build_folder(name)
            with st.expander(folder_label, icon=download_folder_icon(name)):
                render_download_tree(
                    folder_node,
                    allow_run_folder_collapse=False,
                    # A build drops its Token usage panel right after its history folder
                    # (next to the content it summarizes), above the action row below.
                    after_history_hook=(
                        partial(
                            render_build_token_panel,
                            get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE)),
                            _session_root(),
                            name,
                        )
                        if is_build
                        else None
                    ),
                )
                if is_build:
                    render_build_tree_actions(
                        get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE)),
                        _session_root(),
                        name,
                        disabled=_files_actions_busy(),
                    )
                elif allow_run_folder_collapse and (is_run_folder(name) or is_history_folder(name)):
                    with st.container(
                        horizontal=True,
                        vertical_alignment="center",
                        width="content",
                        gap="xxsmall",
                    ):
                        _render_folder_zip_button(name)
                        # A crawl folder's site graph opens the 3D "universe"
                        # viewer (see app_support.site_graph_3d); place it right
                        # of Export. Other folders (vector, history) have none.
                        site_graph = find_site_graph_file(folder_node)
                        if site_graph is not None:
                            render_explore_3d_button(site_graph, disabled=_files_actions_busy())
                        # Rename edits only a run folder's trailing label (crawl/vector);
                        # fixed history folders keep just Export + Delete.
                        if is_run_folder(name):
                            _render_folder_rename_button(name)
                        _render_folder_delete_button(name)
            # Fire the hook right after a history folder's expander closes so a build's
            # Token usage panel sits directly under conversational_rag_history.
            if after_history_hook is not None and is_history_folder(name):
                after_history_hook()
            continue
        render_generated_file_download(entry)


def _render_ready_result_panel() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_root = _session_root()
    active_output_dir = str(st.session_state.get("active_output_dir", ""))
    ready: ReadyDownload | None = None
    if active_output_dir:
        ready = build_ready_download(
            active_output_dir,
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is None:
        ready = find_ready_download_in_session(
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is not None:
        _render_ready_result(ready, strings, session_root)


def _render_ready_result(ready: ReadyDownload, strings: dict[str, Any], session_root: Path) -> None:
    is_zip = ready.file.file_type == "zip"
    subtitle = (
        strings["READY_RESULT_ZIP_SUBTITLE"].format(count=ready.source_count)
        if is_zip
        else strings["READY_RESULT_SINGLE_SUBTITLE"]
    )
    path_parts = ready.file.relative_path.split("/")
    crawl_label = path_parts[0] if path_parts else ""
    timestamp = path_parts[1] if len(path_parts) > 1 else ""
    if crawl_label:
        subtitle = f"{subtitle} ({crawl_label})"
    if crawl_label and timestamp:
        download_name = f"{crawl_label}_{timestamp}.{ready.file.file_type}"
    else:
        download_name = ready.file.name
    st.markdown(
        f'<h3 style="margin-bottom:0;padding-bottom:0">{strings["READY_RESULT_HEADER"]}</h3>'
        f'<p style="opacity:0.7;font-size:0.875rem;margin:0 0 0.75rem">'
        f"{subtitle}</p>",
        unsafe_allow_html=True,
    )
    if not ready.file.download_allowed:
        st.warning(strings["READY_RESULT_TOO_LARGE"])
        return
    try:
        file_bytes = ready.file.path.read_bytes()
    except OSError:
        return
    mime_type = mimetypes.guess_type(download_name)[0] or "application/octet-stream"
    # With a site graph, put Download and Explore in 3D side by side (50/50);
    # otherwise Download spans the full width on its own.
    site_graph = find_site_graph_for_result(session_root, ready.file.relative_path)
    download_col: Any = nullcontext()
    explore_col = None
    if site_graph is not None:
        download_col, explore_col = st.columns(2, vertical_alignment="center")
    with download_col:
        st.download_button(
            label=strings["READY_RESULT_DOWNLOAD_BUTTON"],
            data=file_bytes,
            file_name=download_name,
            mime=mime_type,
            key=f"ready_result_{st.session_state.session_id}_{st.session_state.get('crawl_id', '')}",
            width="stretch",
        )
    if explore_col is not None:
        with explore_col:
            render_explore_3d_button(
                site_graph, disabled=_files_actions_busy(), key_suffix="ready", full_width=True
            )


def _render_open_preview_dialog(files: list[GeneratedFile]) -> None:
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    file_by_relative_path = {file.relative_path: file for file in files}
    if preview_relative_path not in file_by_relative_path:
        st.session_state.preview_file_relative_path = ""
        return
    _file_preview_dialog()


def _render_open_delete_folder_dialog() -> None:
    delete_folder_path = str(st.session_state.get("delete_folder_relative_path", ""))
    if not delete_folder_path:
        return
    target = _session_root() / delete_folder_path
    if not target.is_dir():
        st.session_state.delete_folder_relative_path = ""
        return
    _delete_folder_confirmation_dialog()


def _open_upload_dialog() -> None:
    st.session_state.pop("upload_zip_file", None)  # drop any prior pending file
    st.session_state.upload_dialog_open = True


def _render_import_button() -> None:
    """Render the Import button (mirrors the Export button style) at the top of the tree."""
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.button(
        label=strings["FILES_UPLOAD_BUTTON"],
        width="content",
        key="open_upload_dialog",
        help=strings["FILES_UPLOAD_BUTTON_HELP"],
        on_click=_open_upload_dialog,
        disabled=_files_actions_busy(),
    )


def _on_upload_dismiss() -> None:
    st.session_state.upload_dialog_open = False


def _import_uploaded_zip(zip_bytes: bytes) -> None:
    secret = get_settings().zip_signing_secret
    try:
        added = import_signed_zip(_session_root(), zip_bytes, secret)
    except (OSError, ValueError):
        added = None
    st.session_state.upload_dialog_open = False
    if added:
        st.session_state.upload_done_folder = added
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _import_uploaded_history_zip(zip_bytes: bytes) -> None:
    """Replace a per-session history folder in place from an uploaded history zip."""
    secret = get_settings().zip_signing_secret
    try:
        replaced = import_history_zip(_session_root(), zip_bytes, secret)
    except (OSError, ValueError):
        replaced = None
    st.session_state.upload_dialog_open = False
    if replaced:
        st.session_state.upload_done_folder = replaced
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


_SAMPLE_CATEGORY_CRAWL = "crawl_results"
_SAMPLE_CATEGORY_VECTOR = "vector_indexes"


def _import_sample_fixture_action(category: str, name: str) -> None:
    """Import a bundled sample into the session, then flag a success toast.

    Ends with a full app rerun (not the fragment-scoped one) so the shell fires
    the toast — same pattern as the signed-zip import.
    """
    added = import_sample_fixture(_session_root(), category, name)
    if added:
        st.session_state.sample_import_done_folder = added
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _render_sample_data_panel() -> None:
    """Render the collapsed Sample data panel: one-click import of bundled fixtures.

    Lets a user skip Steps 1-2 by importing a ready-made crawl or index into the
    session, then jump to Semantic search. Trusted repo files, so no signature
    check. One nested panel per fixtures category; each archive imports on click.
    """
    fixtures = list_sample_fixtures()
    if not fixtures:
        return
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    with st.expander(strings["FILES_SAMPLE_PANEL_TITLE"], expanded=False):
        st.caption(strings["FILES_SAMPLE_PANEL_CAPTION"])
        for category in sorted({fixture.category for fixture in fixtures}):
            if category == _SAMPLE_CATEGORY_CRAWL:
                label = strings["FILES_SAMPLE_CATEGORY_CRAWL_RESULTS"]
            elif category == _SAMPLE_CATEGORY_VECTOR:
                label = strings["FILES_SAMPLE_CATEGORY_VECTOR_INDEXES"]
            else:
                label = category.replace("_", " ").capitalize()
            with st.expander(label, expanded=False):
                for fixture in fixtures:
                    if fixture.category != category:
                        continue
                    if st.button(
                        label=f"{fixture.name} • {format_file_size(fixture.size_bytes)}",
                        icon=":material/move_to_inbox:",
                        help=strings["FILES_SAMPLE_IMPORT_HELP"],
                        key=f"sample_import_{fixture.category}_{fixture.name}",
                        disabled=_files_actions_busy(),
                    ):
                        _import_sample_fixture_action(fixture.category, fixture.name)


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_upload_dismiss)
def _upload_folder_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.subheader(strings["FILES_UPLOAD_DIALOG_TITLE"])
    uploaded = st.file_uploader(strings["FILES_UPLOAD_PROMPT"], type=["zip"], key="upload_zip_file")
    if uploaded is None:
        return
    zip_bytes = uploaded.getvalue()
    # Fast-fail check; import_signed_zip re-verifies to avoid a TOCTOU gap.
    if not verify_zip_bytes(zip_bytes, get_settings().zip_signing_secret):
        st.error(strings["FILES_UPLOAD_INVALID"])
        return

    def _cancel() -> None:
        st.session_state.upload_dialog_open = False
        st.rerun()

    top = zip_top_folder(zip_bytes) or ""
    if is_history_folder(top):
        # History imports replace that folder in place. Always confirm (consistent
        # with crawl/vector import); warn when there is existing data to overwrite.
        overwrite = history_exists(_session_root(), top)
        if overwrite:
            body = strings["FILES_UPLOAD_HISTORY_OVERWRITE_BODY"].format(folder=top)
            confirm_label = strings["FILES_UPLOAD_HISTORY_OVERWRITE_CONFIRM"]
        else:
            body = strings["FILES_UPLOAD_HISTORY_IMPORT_BODY"].format(folder=top)
            confirm_label = strings["FILES_UPLOAD_CONFIRM"]
        render_confirm_dialog(
            body=body,
            body_as_warning=overwrite,
            cancel_label=strings["FILES_UPLOAD_CANCEL"],
            cancel_key="upload_cancel_button",
            on_cancel=_cancel,
            confirm_label=confirm_label,
            confirm_key="upload_confirm_button",
            confirm_icon=":material/upload:",
            on_confirm=lambda: _import_uploaded_history_zip(zip_bytes),
        )
        return

    target = import_target_name(_session_root(), top)
    render_confirm_dialog(
        body=strings["FILES_UPLOAD_CONFIRM_BODY"].format(folder=target),
        cancel_label=strings["FILES_UPLOAD_CANCEL"],
        cancel_key="upload_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["FILES_UPLOAD_CONFIRM"],
        confirm_key="upload_confirm_button",
        confirm_icon=":material/upload:",
        on_confirm=lambda: _import_uploaded_zip(zip_bytes),
    )


def _session_log_generated_file() -> GeneratedFile | None:
    """Return a GeneratedFile for the current session's log, or None if absent.

    Built from a fresh ``stat`` (not the cached file listing), so the row always
    reflects the live log size even as it grows during a crawl.
    """
    relative_path = get_settings().log_file
    log_path = _session_root() / relative_path
    if not log_path.is_file():
        return None
    try:
        stat_result = log_path.stat()
    except OSError:
        return None
    return GeneratedFile(
        path=log_path,
        relative_path=relative_path,
        name=log_path.name,
        size_bytes=stat_result.st_size,
        modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
        file_type="log",
        download_allowed=stat_result.st_size <= _DOWNLOAD_LIMIT_BYTES,
    )


def _should_show_files_panel(*, job_alive: bool, has_files: bool) -> bool:
    """Decide whether the 📁 Files & folders panel renders this run.

    While a crawl/index job is active, show it only when it already holds files,
    so an empty panel never flashes mid-write. When idle, always show it — even
    before the session folder exists — so the Import button stays reachable after
    a browser reset clears the session and its outputs.
    """
    if job_alive:
        return has_files
    return True


def _downloads_body() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_folder = _session_root()
    session_folder_str = str(session_folder.resolve())
    files = _cached_list_generated_files(
        session_folder_str,
        session_folder_str,
        _DOWNLOAD_LIMIT_BYTES,
        generated_files_cache_token(session_folder),
    )
    # Merge in the (live) session log, replacing any stale cached entry, so the
    # tree, dataframe, and preview all reflect its current state.
    session_log = _session_log_generated_file()
    if session_log is not None:
        files = files_excluding(files, session_log.relative_path)
        files.append(session_log)
    # The session log is rendered on its own above the tree; keep it out of the
    # tree so its preview widget key is not created twice in the same pass.
    tree_files = files_excluding(files, session_log.relative_path if session_log else None)
    download_tree = _cached_download_tree(tuple(tree_files))
    job_alive = _job_is_alive(st.session_state.job)
    subtitle_text = (
        strings["FILES_DOWNLOADS_IN_PROGRESS"] if job_alive else strings["FILES_DOWNLOADS_SUBTITLE"]
    )
    st.markdown(
        f'<h3 style="padding-bottom:0">{strings["FILES_DOWNLOADS_SUBHEADER"]}</h3>'
        f'<p style="opacity:0.6;font-size:0.875rem;margin:0 0 0rem">{subtitle_text}</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("upload_dialog_open"):
        _upload_folder_dialog()
    # Red "Delete this folder" styling. The selector substring-matches ANY key containing
    # "st-key-delete_folder_" (both the tree buttons and the dialog's cancel/confirm, which
    # re-override it); dialog buttons that must NOT be red (e.g. a blocked-notice Close) must
    # use a key WITHOUT that prefix.
    st.markdown(
        """
        <style>
        div[data-testid="stElementContainer"][class*="st-key-delete_folder_"] button {
            color: #dc3545;
        }
        div[data-testid="stElementContainer"][class*="st-key-delete_folder_"] button:hover {
            color: #c82333; border-color: #dc3545;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # The Import button always renders (disabled mid-job) so its position stays
    # stable; the panel-visibility rule itself lives in _should_show_files_panel.
    show_panel = _should_show_files_panel(job_alive=job_alive, has_files=bool(files))
    if show_panel:
        with st.expander(strings["FILES_CRAWL_RESULT_LABEL"], expanded=True):
            _render_import_button()
            if session_log is not None:
                render_generated_file_download(session_log)
            render_download_tree(download_tree)

    if files:
        rows = [
            {
                strings["FILES_COL_NAME"]: file.relative_path,
                strings["FILES_COL_TYPE"]: file.file_type,
                strings["FILES_COL_SIZE"]: round(file.size_bytes / (1024 * 1024), 3),
                strings["FILES_COL_MODIFIED"]: file.modified_at.strftime(_UTC_DISPLAY_FORMAT),
            }
            for file in files
        ]
        with st.expander(strings["FILES_HEADER"], expanded=False):
            st.dataframe(rows, hide_index=True, width="stretch", lazy=True)

    _render_sample_data_panel()

    # Only one Files & folders modal is live at a time: render the first whose state is
    # set so a just-dismissed dialog can't linger beside a newly opened one (each
    # _render_open_* also re-checks its own state and is a no-op when unset).
    if str(st.session_state.get("preview_file_relative_path", "")):
        _render_open_preview_dialog(files)
    elif str(st.session_state.get("delete_folder_relative_path", "")):
        _render_open_delete_folder_dialog()
    elif str(st.session_state.get("rename_folder_relative_path", "")):
        _render_open_rename_folder_dialog()
    elif str(st.session_state.get("export_folder_relative_path", "")):
        _render_open_export_dialog()


def _render_downloads() -> None:
    """Auto-rerun downloads only while a crawl or vector-index job is active."""
    _auto_refresh_fragment(
        _downloads_body,
        active=_crawl_job_active() or _vector_job_active(),
        interval=_DOWNLOADS_REFRESH_INTERVAL,
    )
