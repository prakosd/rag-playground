"""Client-side focus helper for Streamlit widgets.

Streamlit has no server-side "focus this widget" API, so this injects a tiny
zero-height HTML component whose script reaches into the parent document and
focuses the first ``input``/``textarea`` inside a keyed widget's container.
Streamlit tags each keyed widget's container with a ``st-key-<key>`` CSS class
(the app already relies on this class for styling), so that is what we target.

Call :func:`focus_widget` once — right after the widget renders and only when a
one-shot session flag says focus is pending — so it never steals focus while the
user is typing.
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

# Zero height keeps the injected helper invisible; the script still runs.
_FOCUS_COMPONENT_HEIGHT = 0
# Give the parent DOM a few animation frames to mount the target widget before
# giving up, so focus survives the render race after an st.rerun().
_FOCUS_MAX_ATTEMPTS = 20


def focus_widget(key: str) -> None:
    """Move browser focus to the input/textarea of the widget keyed ``key``."""
    selector = json.dumps(f".st-key-{key} input, .st-key-{key} textarea")
    components.html(
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
