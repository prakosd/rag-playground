from __future__ import annotations

from app_support.dialog_ui import confirm_dialog_css, scrollable_dialog_css


def test_confirm_dialog_css_scopes_styles_to_given_keys() -> None:
    css = confirm_dialog_css("my_cancel", "my_confirm")
    assert ".st-key-my_cancel button" in css
    assert ".st-key-my_confirm button" in css


def test_confirm_dialog_css_colors_cancel_green_and_confirm_red() -> None:
    css = confirm_dialog_css("cancel_k", "confirm_k")
    # Cancel/keep button is green; confirm button is red.
    assert "#28a745" in css
    assert "#dc3545" in css


def test_confirm_dialog_css_docks_confirm_button_to_the_right() -> None:
    css = confirm_dialog_css("cancel_k", "confirm_k")
    assert "align-items: flex-end;" in css
    assert ".st-key-confirm_k)" in css


def test_scrollable_dialog_css_sizes_dialog_and_scopes_scroll_to_content_key() -> None:
    css = scrollable_dialog_css("my-scope", "my_content", width="60vw", height="55vh")
    # Scope marker + shallow dialog width, and the content container owns the height.
    assert 'class="my-scope"' in css
    assert ":has(.my-scope)" in css
    assert "width: 60vw" in css
    assert "st-key-my_content" in css
    assert "height: 55vh" in css


def test_scrollable_dialog_css_defaults_to_70_percent_viewport() -> None:
    css = scrollable_dialog_css("scope", "content")
    assert "width: 70vw" in css
    assert "height: 70vh" in css


def _render_confirm(*, body_as_warning: bool = False, with_title: bool = False) -> None:
    # Self-contained render for AppTest.from_function (isolated namespace).
    import streamlit as st

    from app_support.dialog_ui import render_confirm_dialog

    def _cancel() -> None:
        st.session_state["confirm_outcome"] = "cancelled"

    def _confirm() -> None:
        st.session_state["confirm_outcome"] = "confirmed"

    render_confirm_dialog(
        body="Delete this folder?",
        cancel_label="Keep",
        cancel_key="cancel_btn",
        on_cancel=_cancel,
        confirm_label="Delete",
        confirm_key="confirm_btn",
        confirm_icon=":material/delete:",
        on_confirm=_confirm,
        title="Confirm" if with_title else None,
        body_as_warning=body_as_warning,
    )


# Risk: the confirm button must invoke on_confirm (title + warning-body branches render).
# Type: unit (AppTest).
def test_render_confirm_dialog_confirm_invokes_callback() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(
        _render_confirm, kwargs={"with_title": True, "body_as_warning": True}
    ).run()
    assert not app.exception
    assert any(warning.value == "Delete this folder?" for warning in app.warning)
    next(button for button in app.button if button.key == "confirm_btn").click()
    app.run()
    assert app.session_state["confirm_outcome"] == "confirmed"


# Risk: the cancel button must invoke on_cancel (plain-write body branch renders).
# Type: unit (AppTest).
def test_render_confirm_dialog_cancel_invokes_callback() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_render_confirm).run()
    assert not app.exception
    next(button for button in app.button if button.key == "cancel_btn").click()
    app.run()
    assert app.session_state["confirm_outcome"] == "cancelled"
