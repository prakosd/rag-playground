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
# Breathing room (px) left above a message pinned to the top of the chat panel so
# it is not flush with the panel's top edge.
_SCROLL_TOP_MARGIN_PX = 8

# Tracks which page last became active so a page can focus its primary field once
# on entry (a fresh navigation) without stealing focus on every later rerun.
_ACTIVE_PAGE_KEY = "_focus_active_page"


def entered_page(page_id: str) -> bool:
    """Return True the first render after *page_id* becomes the active page.

    ``st.navigation`` runs only the selected page each rerun, so the active page
    updates a shared marker; this returns True only when the marker changes to
    *page_id* (a fresh navigation, or the first load) and False on every later
    rerun of the same page. Callers use it to move focus to a page's primary
    field once on entry without stealing focus while the user is interacting.
    """
    if st.session_state.get(_ACTIVE_PAGE_KEY) != page_id:
        st.session_state[_ACTIVE_PAGE_KEY] = page_id
        return True
    return False


def focus_widget(key: str) -> None:
    """Move browser focus to the input/textarea of the widget keyed ``key``."""
    _focus_first(f".st-key-{key} input, .st-key-{key} textarea")


def focus_chat_input() -> None:
    """Move browser focus to the page's chat input.

    ``st.chat_input`` is pinned to the viewport bottom and its textarea does not
    carry the ``st-key-<key>`` class other widgets expose, so :func:`focus_widget`
    cannot target it; this focuses its stable test-id'd textarea instead.
    """
    _focus_first('[data-testid="stChatInput"] textarea')


def _focus_first(selector_expr: str) -> None:
    """Inject a one-shot script that focuses the first element matching a selector."""
    selector = json.dumps(selector_expr)
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


def scroll_message_into_view(panel_key: str, message_key: str) -> None:
    """Scroll the keyed panel so the keyed message sits near the top of the view.

    ChatGPT-style: after a new turn, pin the just-asked question near the top of
    the fixed-height chat panel so the question and the start of its (possibly
    long) answer are both visible — instead of jumping to the absolute bottom,
    which would push the question above the panel. Best-effort — if either element
    is not found the scroll is left where it was. Inject it only once (via a
    one-shot flag) so it never fights the user scrolling up to read history.
    """
    panel_selector = json.dumps(f".st-key-{panel_key}")
    message_selector = json.dumps(f".st-key-{message_key}")
    st.iframe(
        f"""
        <script>
        (function() {{
            const panelSelector = {panel_selector};
            const messageSelector = {message_selector};
            const doc = window.parent.document;
            let attempts = 0;
            function intoView() {{
                const root = doc.querySelector(panelSelector);
                const target = doc.querySelector(messageSelector);
                if (root && target) {{
                    const scrollable = [root, ...root.querySelectorAll(":scope *")].find(
                        (el) => el.scrollHeight > el.clientHeight + 4
                    ) || root;
                    const delta = target.getBoundingClientRect().top
                        - scrollable.getBoundingClientRect().top;
                    scrollable.scrollTop += delta - {_SCROLL_TOP_MARGIN_PX};
                    return;
                }}
                if (attempts++ < {_FOCUS_MAX_ATTEMPTS}) {{
                    window.requestAnimationFrame(intoView);
                }}
            }}
            intoView();
        }})();
        </script>
        """,
        height=_FOCUS_COMPONENT_HEIGHT,
    )
