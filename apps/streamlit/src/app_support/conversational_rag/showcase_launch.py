"""Inline CCv2 button that opens a build's read-only showcase in a new browser tab.

Thin UI adapter mirroring the 3D launcher: it mounts a small component whose
frontend (``assets/launch.js``) opens the signed showcase URL on click (and, when
asked, best-effort once on mount). The Python side only wires the URL + localized
labels in; all rendering lives in the frontend asset.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from streamlit.components.v2 import component as component_v2

__all__ = ["render_launch_button"]

_COMPONENT_NAME = "crawl4md_showcase_launch"
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_LAUNCH_HTML = "<span></span>"


@lru_cache(maxsize=1)
def _component():
    """Register the inline launch component once (deferred to first render)."""
    return component_v2(
        _COMPONENT_NAME,
        html=_LAUNCH_HTML,
        js=(_ASSETS_DIR / "launch.js").read_text(encoding="utf-8"),
        css=(_ASSETS_DIR / "launch.css").read_text(encoding="utf-8"),
    )


def render_launch_button(
    url: str, *, label: str, help: str, key: str, auto_open: bool = False
) -> None:
    """Mount the Launch button that opens *url* in a new tab.

    *url* is relative (``?show=<token>``) so the frontend resolves it against the
    app's base URL, keeping base-path deploys working. *auto_open* attempts a
    best-effort open on mount for a just-built showcase.
    """
    _component()(
        data={"url": url, "label": label, "help": help, "auto_open": bool(auto_open)},
        key=key,
    )
