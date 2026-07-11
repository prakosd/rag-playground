"""Shared confirmation-dialog body for all `@st.dialog` confirm modals.

The `@st.dialog` decorator (with its fixed title and dismiss handler) stays in
``streamlit_app.py``; these helpers render the shared body so every confirm
modal has the same layout, button colours, and right-docked confirm button.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

__all__ = ["confirm_dialog_css", "render_confirm_dialog"]


def confirm_dialog_css(cancel_key: str, confirm_key: str) -> str:
    """Return the ``<style>`` block colouring a confirm dialog's two buttons.

    The cancel/keep button is green and the confirm button is red and docked to
    the right, scoped to the given Streamlit element keys so the styling only
    affects this dialog.
    """
    return f"""
        <style>
        div[data-testid="stElementContainer"].st-key-{cancel_key} button {{
            background-color: #28a745; border-color: #28a745; color: white;
        }}
        div[data-testid="stElementContainer"].st-key-{cancel_key} button:hover {{
            background-color: #218838; border-color: #1e7e34; color: white;
        }}
        div[data-testid="stElementContainer"].st-key-{confirm_key} button {{
            background-color: #dc3545; border-color: #dc3545; color: white;
        }}
        div[data-testid="stElementContainer"].st-key-{confirm_key} button:hover {{
            background-color: #c82333; border-color: #bd2130; color: white;
        }}
        div[data-testid="stColumn"]:has(.st-key-{confirm_key}) [data-testid="stVerticalBlock"] {{
            align-items: flex-end;
        }}
        </style>
    """


def render_confirm_dialog(
    *,
    body: str,
    cancel_label: str,
    cancel_key: str,
    on_cancel: Callable[[], None],
    confirm_label: str,
    confirm_key: str,
    confirm_icon: str,
    on_confirm: Callable[[], None],
    title: str | None = None,
    body_as_warning: bool = False,
) -> None:
    """Render the shared confirm-dialog body inside an ``@st.dialog`` function.

    The decorator owns the modal title and dismiss handler; this renders the
    consistent body (optional title, message, green keep + red confirm buttons)
    and invokes ``on_cancel`` / ``on_confirm`` when a button is clicked.
    """
    st.markdown(confirm_dialog_css(cancel_key, confirm_key), unsafe_allow_html=True)
    if title:
        st.subheader(title)
    if body_as_warning:
        st.warning(body)
    else:
        st.write(body)
    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button(cancel_label, key=cancel_key):
            on_cancel()
    with action_cols[1]:
        if st.button(confirm_label, type="secondary", icon=confirm_icon, key=confirm_key):
            on_confirm()
