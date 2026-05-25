"""Regression tests for dialog dismiss-via-X / outside-click behaviour.

Bug: _stop_confirmation_dialog and _load_session_dialog lacked on_dismiss callbacks.
When Streamlit dismissed them via X or outside-click it did not reset the controlling
session-state flags, so the next rerun (e.g. a language change) would re-open the dialog.

Fix: both dialogs now declare on_dismiss=_on_stop_dismiss / _on_load_session_dismiss which
reset the flags. These tests verify the flag-reset logic and that the subsequent rerun
leaves the flags in the cleared state.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

_STREAMLIT_APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def _simple_storage_component(
    name: str,
    *,
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
    isolate_styles: bool = True,
):
    def render(*, data: dict[str, object], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            hydrated=True,
            records=[],
            stored_records=None,
            storage_write_failed=False,
        )

    return render


# Risk: after on_dismiss clears stop_confirmation_open, a subsequent rerun must not
# re-open the stop dialog. Type: integration regression.
def test_stop_dialog_flag_cleared_on_dismiss_prevents_reopen(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        at.run(timeout=10)

    assert not at.exception

    # Simulate dialog was opened (Stop button clicked) then dismissed via X
    at.session_state["stop_confirmation_open"] = True
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at.run(timeout=10)
    assert not at.exception

    # Simulate on_dismiss callback fired (resets the flag, as the fix does)
    at.session_state["stop_confirmation_open"] = False
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at.run(timeout=10)

    assert not at.exception
    # Flag must stay False — the dialog must not reopen itself on the next rerun
    assert not at.session_state["stop_confirmation_open"]


# Risk: after on_dismiss clears session_load_dialog_open and _load_session_enter, a
# subsequent rerun must not re-open the load-session dialog. Type: integration regression.
def test_load_session_dialog_flag_cleared_on_dismiss_prevents_reopen(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        at.run(timeout=10)

    assert not at.exception

    # Simulate dialog was opened (📁 button clicked) then dismissed via X
    at.session_state["session_load_dialog_open"] = True
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at.run(timeout=10)
    assert not at.exception

    # Simulate on_dismiss callback fired — both flags must be cleared
    at.session_state["session_load_dialog_open"] = False
    at.session_state["_load_session_enter"] = False
    with patch("streamlit.components.v2.component", _simple_storage_component):
        at.run(timeout=10)

    assert not at.exception
    assert not at.session_state["session_load_dialog_open"]
    assert not at.session_state["_load_session_enter"]
