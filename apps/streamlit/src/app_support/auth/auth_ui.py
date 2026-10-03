"""Authentication credentials panel for the Crawl page.

Renders a collapsible "Authentication" section where a user adds and deletes
session-scoped HTTP (Basic/Bearer) credentials. The matching credential is applied
to the crawler as an ``Authorization`` header (wired in the shell). All reads and
writes go through ``app_support.auth.store`` (encrypted at rest); this module only
renders. Add and delete run inline then ``st.rerun()`` so the dialog closes and the
table refreshes immediately.
"""

from __future__ import annotations

import contextlib
import html

import streamlit as st
from pydantic import ValidationError

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _session_root,
)
from app_support.auth.credentials import HttpCredential, parse_url_prefixes
from app_support.auth.crypto import CredentialCipher
from app_support.auth.store import (
    CredentialRow,
    add_credential,
    delete_credentials,
    list_credential_rows,
)
from app_support.dialog_ui import render_confirm_dialog
from app_support.generated_files import format_local_datetime
from app_support.i18n import Strings, get_strings
from app_support.settings import get_settings

__all__ = ["render_authentication_panel"]

_ADD_OPEN_KEY = "auth_add_open"
_DELETE_IDS_KEY = "auth_delete_ids"
_TABLE_KEY = "auth_credentials_table"
# Keys the HTTP header's content-width title container: scopes the "?" hint beside the
# title and anchors the subtitle's pull-up CSS (both must reference the same key).
_HTTP_TITLE_KEY = "auth_http_title"

# Scoped to the Add-credential dialog: the Create button is the only action, so hide
# each field's "Press Enter to apply" instruction (Enter does nothing in this modal).
_ADD_DIALOG_SCOPE_CLASS = "auth-add-credential-scope"
_ADD_DIALOG_CSS = f"""
<div class="{_ADD_DIALOG_SCOPE_CLASS}" style="display:none"></div>
<style>
div[data-testid="stDialog"]:has(.{_ADD_DIALOG_SCOPE_CLASS}) [data-testid="InputInstructions"] {{
    display: none;
}}
</style>
"""


def render_authentication_panel(*, strings: Strings, disabled: bool) -> None:
    """Render the collapsible Authentication panel (HTTP credentials)."""
    session_id = str(st.session_state.get("session_id", ""))
    if not session_id:
        return
    rows = list_credential_rows(_session_root(session_id))

    with st.expander(strings["AUTH_PANEL_LABEL"], expanded=False):
        _render_http_section(rows, disabled=disabled, strings=strings)

    if st.session_state.get(_ADD_OPEN_KEY):
        _add_credential_dialog()
    if st.session_state.get(_DELETE_IDS_KEY):
        _delete_credential_dialog()


def auth_type_label(auth_type: str | None, strings: Strings) -> str:
    """Return the localized label for an HTTP auth type (Bearer/Basic)."""
    if auth_type == "bearer":
        return strings["AUTH_TYPE_BEARER"]
    if auth_type == "basic":
        return strings["AUTH_TYPE_BASIC"]
    return auth_type or ""


def credential_dataframe_rows(rows: list[CredentialRow], strings: Strings) -> list[dict[str, str]]:
    """Return display dicts (Name / Auth type / Created at) for the credential table."""
    return [
        {
            strings["AUTH_COL_NAME"]: row.name,
            strings["AUTH_COL_TYPE"]: auth_type_label(row.auth_type, strings),
            strings["AUTH_COL_CREATED"]: (
                format_local_datetime(row.created_at, abbreviate_month=True)
                if row.created_at
                else "—"
            ),
        }
        for row in rows
    ]


def selected_credential_ids(positions: list[int], rows: list[CredentialRow]) -> list[str]:
    """Map selected dataframe row positions to their credential ids."""
    return [rows[position].id for position in positions if 0 <= position < len(rows)]


def _http_subtitle_html(strings: Strings) -> str:
    """Build the dim subtitle under the HTTP title (folds in the header's pull-up CSS)."""
    return (
        f"<style>.st-key-{_HTTP_TITLE_KEY}{{margin-top:-0.5rem}}</style>"
        '<div style="opacity:0.65;font-size:0.875rem;margin-top:-0.85rem">'
        f"{html.escape(strings['AUTH_HTTP_SUBTITLE'])}</div>"
    )


def _selected_ids(rows: list[CredentialRow]) -> list[str]:
    """Map the table's persisted row selection (from the prior run) to credential ids."""
    state = st.session_state.get(_TABLE_KEY)
    selection = getattr(state, "selection", None)
    if selection is None:
        return []
    return selected_credential_ids(list(selection.get("rows", [])), rows)


def _render_http_section(rows: list[CredentialRow], *, disabled: bool, strings: Strings) -> None:
    selected = _selected_ids(rows)
    header, actions = st.columns([4, 1], vertical_alignment="center")
    with header:
        with st.container(horizontal=True, width="content", key=_HTTP_TITLE_KEY):
            st.markdown(f"**{strings['AUTH_HTTP_TITLE']}**", help=strings["AUTH_HTTP_HINT"])
        st.markdown(_http_subtitle_html(strings), unsafe_allow_html=True)
    with actions, st.container(horizontal=True, horizontal_alignment="right", gap="xxsmall"):
        if st.button(
            ":material/add:",
            type="primary",
            help=strings["AUTH_ADD_BUTTON"],
            disabled=disabled,
            key="auth_add_btn",
        ):
            st.session_state[_ADD_OPEN_KEY] = True
            st.rerun()
        if st.button(
            ":material/delete:",
            help=strings["AUTH_DELETE_SELECTED"],
            disabled=disabled or not selected,
            key="auth_delete_selected",
        ):
            st.session_state[_DELETE_IDS_KEY] = selected
            st.rerun()

    if not rows:
        st.caption(strings["AUTH_TABLE_EMPTY"])
        return

    st.dataframe(
        credential_dataframe_rows(rows, strings),
        hide_index=True,
        width="stretch",
        selection_mode="multi-row",
        on_select="rerun",
        key=_TABLE_KEY,
    )


def _on_add_dialog_dismiss() -> None:
    """Clear the add-dialog open flag when it is dismissed (x / click-away / Esc).

    Without this the flag persists and the dialog re-opens on the next page visit.
    """
    st.session_state[_ADD_OPEN_KEY] = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, on_dismiss=_on_add_dialog_dismiss)
def _add_credential_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.markdown(_ADD_DIALOG_CSS, unsafe_allow_html=True)
    st.markdown(
        f"<h3 style='margin:-0.75rem 0 0.25rem 0;padding:0'>"
        f"{html.escape(strings['AUTH_DIALOG_ADD_HTTP_TITLE'])}</h3>",
        unsafe_allow_html=True,
    )
    name = st.text_input(
        strings["AUTH_FIELD_NAME"], placeholder=strings["AUTH_FIELD_NAME_PLACEHOLDER"]
    )
    is_bearer = (
        st.selectbox(
            strings["AUTH_FIELD_AUTH_TYPE"],
            [strings["AUTH_TYPE_BEARER"], strings["AUTH_TYPE_BASIC"]],
        )
        == strings["AUTH_TYPE_BEARER"]
    )
    if is_bearer:
        secret = st.text_input(
            strings["AUTH_FIELD_BEARER_TOKEN"],
            type="password",
            placeholder=strings["AUTH_FIELD_BEARER_TOKEN_PLACEHOLDER"],
        )
    else:
        secret = st.text_input(
            strings["AUTH_FIELD_BASIC_CREDS"],
            type="password",
            placeholder=strings["AUTH_FIELD_BASIC_CREDS_PLACEHOLDER"],
            help=strings["AUTH_FIELD_BASIC_HELP"],
        )
    url_prefixes = st.text_input(
        strings["AUTH_FIELD_URL_PREFIXES"],
        placeholder=strings["AUTH_FIELD_URL_PREFIXES_PLACEHOLDER"],
        help=strings["AUTH_FIELD_URL_PREFIXES_HELP"],
    )
    error_slot = st.empty()
    if st.button(
        strings["AUTH_CREATE_BUTTON"], type="primary", width="stretch", key="auth_http_create"
    ):
        parsed_prefixes = parse_url_prefixes(url_prefixes)
        if not (name.strip() and secret.strip() and parsed_prefixes):
            error_slot.error(strings["AUTH_ERR_REQUIRED"])
            return
        try:
            credential = HttpCredential(
                name=name,
                auth_type="bearer" if is_bearer else "basic",
                secret=secret,
                url_prefixes=parsed_prefixes,
            )
        except ValidationError:
            error_slot.error(strings["AUTH_ERR_INVALID"])
            return
        _persist_and_close(credential)


def _persist_and_close(credential: HttpCredential) -> None:
    session_id = str(st.session_state.get("session_id", ""))
    cipher = CredentialCipher(get_settings().zip_signing_secret, session_id)
    add_credential(_session_root(session_id), credential, cipher)
    st.session_state[_ADD_OPEN_KEY] = False
    st.session_state.pop(_TABLE_KEY, None)
    st.rerun()


def _on_delete_dialog_dismiss() -> None:
    """Clear the pending-delete ids when the dialog is dismissed (x / click-away / Esc).

    Without this the ids persist and the dialog re-opens on the next page visit.
    """
    st.session_state[_DELETE_IDS_KEY] = []


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_delete_dialog_dismiss)
def _delete_credential_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    ids = [str(item) for item in st.session_state.get(_DELETE_IDS_KEY, []) if item]
    if not ids:
        return
    render_confirm_dialog(
        title=strings["AUTH_DELETE_DIALOG_TITLE"],
        body=strings["AUTH_DELETE_DIALOG_BODY"].format(count=len(ids)),
        body_as_warning=True,
        cancel_label=strings["AUTH_DELETE_CANCEL"],
        cancel_key="auth_delete_cancel",
        on_cancel=_close_delete_dialog,
        confirm_label=strings["AUTH_DELETE_CONFIRM"],
        confirm_key="auth_delete_confirm",
        confirm_icon=":material/delete:",
        on_confirm=lambda: _confirm_delete(ids),
    )


def _confirm_delete(ids: list[str]) -> None:
    session_id = str(st.session_state.get("session_id", ""))
    with contextlib.suppress(OSError, ValueError):
        delete_credentials(_session_root(session_id), ids)
    _close_delete_dialog()


def _close_delete_dialog() -> None:
    st.session_state[_DELETE_IDS_KEY] = []
    st.session_state.pop(_TABLE_KEY, None)
    st.rerun()
