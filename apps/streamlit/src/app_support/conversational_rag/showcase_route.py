"""Showcase route: render a build's read-only chat when a signed ?show token is set.

A showcase tab is a fresh Streamlit session that must NOT run the normal browser-
session bootstrap. This module is called at the very top of the app: if a valid
signed token is present it verifies it, resolves the one build folder it names
(never the whole session), hides the navigation, and renders the chat-only page;
otherwise it does nothing and the normal app runs. Only the pure token→folder
resolution is unit-tested; the render path is a thin ``st.navigation`` wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import streamlit as st

from app_support.app_runtime import _DEFAULT_LANGUAGE, _SESSIONS_ROOT
from app_support.conversational_rag.build_manager import build_dir, load_build, parse_showcase_token
from app_support.conversational_rag.conversational_rag_build_ui import load_build_as_controls
from app_support.i18n import get_strings
from app_support.rag_shared.rag_ui import RagPageContext
from app_support.session_manager import session_dir
from app_support.settings import get_settings

__all__ = ["maybe_render_showcase", "resolve_build_root"]


def maybe_render_showcase() -> bool:
    """Take over the run to render a build showcase when ``?show`` is present.

    Returns True when it rendered (the caller then stops), so a showcase tab never
    falls through to the normal session bootstrap.
    """
    token = str(st.query_params.get("show", ""))
    if not token:
        return False
    render_fn = _showcase_render_fn(token)
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    # One hidden default page served at the app root; the showcase link opens
    # "/?show=…" (see launch.js) so Streamlit routes it to this default (url_path="").
    page = st.Page(
        render_fn,
        title=strings["CONV_SHOWCASE_PAGE_TITLE"],
        url_path="",
        default=True,
    )
    st.navigation([page], position="hidden").run()
    return True


def resolve_build_root(token: str, sessions_root: Path | str, secret: str) -> Path | None:
    """Verify *token* and return the contained build folder it names, or None.

    None for a malformed/forged token, a path that escapes the sessions root, or a
    build folder that no longer exists — so the caller shows a friendly error.
    """
    parsed = parse_showcase_token(token, secret)
    if parsed is None:
        return None
    session_id, build_name = parsed
    try:
        root = build_dir(session_dir(sessions_root, session_id), build_name)
    except ValueError:
        return None
    return root if root.is_dir() else None


def _showcase_render_fn(token: str) -> Callable[[], None]:
    build_root = resolve_build_root(token, _SESSIONS_ROOT, get_settings().zip_signing_secret)
    if build_root is None:
        return _render_unavailable
    controls = load_build_as_controls(build_root)
    snapshot = load_build(build_root)
    if controls is None or snapshot is None:
        return _render_unavailable
    st.session_state["language"] = snapshot.language
    context = RagPageContext(
        default_language=snapshot.language,
        list_indexes=lambda: [],
        render_downloads=lambda: None,
        session_root=lambda: build_root,
    )
    # Imported lazily: app_pages is on sys.path only once the app script is running.
    import app_pages.conversational_rag as conversational_rag

    return partial(conversational_rag.render_page, context, showcase_controls=controls)


def _render_unavailable() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(strings["CONV_SHOWCASE_UNAVAILABLE_TITLE"])
    st.info(strings["CONV_SHOWCASE_UNAVAILABLE_BODY"])
