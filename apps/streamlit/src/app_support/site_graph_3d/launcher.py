"""Streamlit launcher for the 3D site-graph viewer.

Thin UI adapter: reads a crawl's ``site_graph.jsonl``, assembles the standalone
viewer document (:mod:`viewer_assembler`), and mounts an inline CCv2 button that
opens it in a new browser tab. All rendering lives in the frontend assets; this
module only wires data + localized labels into the component.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.components.v2 import component as component_v2

from app_support.app_runtime import _DEFAULT_LANGUAGE
from app_support.i18n import get_strings
from app_support.site_graph_3d.viewer_assembler import build_viewer_html
from app_support.site_graph_3d.viewer_labels import viewer_labels
from app_support.support import GeneratedFile

__all__ = ["render_explore_3d_button"]

_COMPONENT_NAME = "crawl4md_site_graph_3d"
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
# launcher.js renders the button into the component's host element directly, so
# the mounted HTML only needs to be a minimal, unambiguous inline root.
_LAUNCHER_HTML = """
<span></span>
"""


@lru_cache(maxsize=1)
def _component():
    """Register the inline launcher component once (deferred to first render)."""
    return component_v2(
        _COMPONENT_NAME,
        html=_LAUNCHER_HTML,
        js=(_ASSETS_DIR / "launcher.js").read_text(encoding="utf-8"),
        css=(_ASSETS_DIR / "launcher.css").read_text(encoding="utf-8"),
    )


def render_explore_3d_button(file: GeneratedFile, *, disabled: bool = False) -> None:
    """Mount the "Explore in 3D" button for a ``site_graph.jsonl`` file."""
    language = st.session_state.get("language", _DEFAULT_LANGUAGE)
    strings = get_strings(language)
    # A disabled button can't be clicked, and the panel auto-refreshes while a
    # job runs, so skip the (larger) document rebuild + transmit until it's live.
    html = ""
    if not disabled:
        try:
            jsonl_text = file.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        html = build_viewer_html(jsonl_text, viewer_labels(language))
    _component()(
        data={
            "html": html,
            "label": strings["FILES_EXPLORE_3D_LABEL"],
            "help": strings["FILES_EXPLORE_3D_HELP"],
            "disabled": bool(disabled),
        },
        key=f"explore3d_{st.session_state.get('session_id', '')}_{file.relative_path}",
    )
