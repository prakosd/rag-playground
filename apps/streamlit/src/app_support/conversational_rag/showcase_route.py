"""Showcase route: render a build's read-only chat when a ?show slug is set.

A showcase tab is a fresh Streamlit session that must NOT run the normal browser-
session bootstrap. This module is called at the very top of the app: if a known
build slug is present it resolves the one build folder that claims it (never the
whole session), hides the navigation, and renders the chat-only page; otherwise it
does nothing and the normal app runs. Inspect and the Token usage panel are off by
default and opt-in per visit via ``?inspect`` and ``?showToken``. Only the pure
slug→folder resolution is unit-tested; the render path is a thin ``st.navigation``
wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path

import streamlit as st

from app_support.app_runtime import _DEFAULT_LANGUAGE, _SESSIONS_ROOT
from app_support.conversational_rag.build_manager import build_run_dir, load_build, resolve_slug
from app_support.conversational_rag.conversational_rag_build_ui import load_build_as_controls
from app_support.i18n import get_strings
from app_support.rag_shared.rag_ui import RagPageContext

__all__ = ["maybe_render_showcase", "resolve_build_root"]


def maybe_render_showcase() -> bool:
    """Take over the run to render a build showcase when ``?show`` is present.

    Returns True when it rendered (the caller then stops), so a showcase tab never
    falls through to the normal session bootstrap.
    """
    slug = str(st.query_params.get("show", ""))
    if not slug:
        return False
    render_fn = _showcase_render_fn(slug)
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


def resolve_build_root(slug: str, sessions_root: Path | str) -> Path | None:
    """Return the build folder named by *slug*, or None when no build claims it.

    Delegates to the slug registry scan; None for an empty or unknown slug so the
    caller shows a friendly error instead of a broken chat.
    """
    return resolve_slug(sessions_root, slug)


def _showcase_render_fn(slug: str) -> Callable[[], None]:
    build_root = resolve_build_root(slug, _SESSIONS_ROOT)
    if build_root is None:
        return _render_unavailable
    controls = load_build_as_controls(build_root)
    snapshot = load_build(build_root)
    run_dir = build_run_dir(build_root)
    if controls is None or snapshot is None or run_dir is None:
        return _render_unavailable
    st.session_state["language"] = snapshot.language
    # Inspect + the Token usage panel are per-visit URL opt-ins, not frozen settings.
    controls = replace(controls, inspect="inspect" in st.query_params)
    show_token_panel = "showToken" in st.query_params
    context = RagPageContext(
        default_language=snapshot.language,
        list_indexes=lambda: [],
        render_downloads=lambda: None,
        session_root=lambda: run_dir,
    )
    # Imported lazily: app_pages is on sys.path only once the app script is running.
    import app_pages.conversational_rag as conversational_rag

    return partial(
        conversational_rag.render_page,
        context,
        showcase_controls=controls,
        show_token_panel=show_token_panel,
        showcase_prompts=snapshot.prompts,
        showcase_slug=slug,
    )


def _render_unavailable() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(strings["CONV_SHOWCASE_UNAVAILABLE_TITLE"])
    st.info(strings["CONV_SHOWCASE_UNAVAILABLE_BODY"])
