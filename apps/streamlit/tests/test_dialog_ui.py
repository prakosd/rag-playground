from __future__ import annotations

from app_support.dialog_ui import confirm_dialog_css


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
