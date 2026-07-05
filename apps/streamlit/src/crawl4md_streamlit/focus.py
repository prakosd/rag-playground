"""Client-side helpers for Streamlit widgets (focus and programmatic click).

Streamlit has no server-side "focus this widget" or "click this widget" API, so
these embed a tiny ``st.iframe`` whose script reaches into the parent document
and acts on the first matching element inside a keyed widget's container.
Streamlit tags each keyed widget's container with a ``st-key-<key>`` CSS class
(the app already relies on this class for styling), so that is what we target.

Call :func:`focus_widget` once — right after the widget renders and only when a
one-shot session flag says focus is pending — so it never steals focus while the
user is typing. :func:`click_widget` likewise auto-clicks a button/link once, used
to start a prepared download without a second user click.
"""

from __future__ import annotations

import json

import streamlit as st

# 1px keeps the injected helper effectively invisible. st.iframe rejects a
# non-positive height, and the script still runs regardless of the frame size.
_FOCUS_COMPONENT_HEIGHT = 1
# Give the parent DOM a few animation frames to mount the target widget before
# giving up, so the action survives the render race after an st.rerun().
_FOCUS_MAX_ATTEMPTS = 20


def focus_widget(key: str) -> None:
    """Move browser focus to the input/textarea of the widget keyed ``key``."""
    selector = json.dumps(f".st-key-{key} input, .st-key-{key} textarea")
    st.iframe(
        f"""
        <script>
        (function() {{
            const selector = {selector};
            const doc = window.parent.document;
            let attempts = 0;
            function tryFocus() {{
                const target = doc.querySelector(selector);
                if (target) {{
                    target.focus();
                    return;
                }}
                if (attempts++ < {_FOCUS_MAX_ATTEMPTS}) {{
                    window.requestAnimationFrame(tryFocus);
                }}
            }}
            tryFocus();
        }})();
        </script>
        """,
        height=_FOCUS_COMPONENT_HEIGHT,
    )


def click_widget(key: str) -> None:
    """Programmatically click the button/link inside the widget keyed ``key``.

    Used to auto-start a just-prepared download (the ``st.download_button`` holds
    the bytes efficiently, so we click it rather than embedding the payload). The
    caller must inject this only once per prepared download — the widget click
    triggers a rerun, and re-injecting would loop.
    """
    selector = json.dumps(f".st-key-{key} button, .st-key-{key} a")
    st.iframe(
        f"""
        <script>
        (function() {{
            const selector = {selector};
            const doc = window.parent.document;
            let attempts = 0;
            function tryClick() {{
                const target = doc.querySelector(selector);
                if (target) {{
                    target.click();
                    return;
                }}
                if (attempts++ < {_FOCUS_MAX_ATTEMPTS}) {{
                    window.requestAnimationFrame(tryClick);
                }}
            }}
            tryClick();
        }})();
        </script>
        """,
        height=_FOCUS_COMPONENT_HEIGHT,
    )
