from __future__ import annotations

from crawl4md_streamlit.controls import crawl_action_buttons


def _actions_for(
    state: str,
    *,
    job_alive: bool | None = None,
) -> list[tuple[str, str, bool, str]]:
    return [
        (button.action, button.label, button.disabled, button.button_type)
        for button in crawl_action_buttons(
            state,
            job_alive=state == "running" if job_alive is None else job_alive,
        )
    ]


def test_idle_shows_green_start_action() -> None:
    assert _actions_for("idle") == [("start", "Start", False, "primary")]


def test_running_shows_stop_action() -> None:
    assert _actions_for("running") == [("stop", "Stop", False, "secondary")]


def test_alive_job_shows_stop_action_even_before_state_updates() -> None:
    assert _actions_for("idle", job_alive=True) == [("stop", "Stop", False, "secondary")]


def test_cancel_requested_disables_stop_action() -> None:
    assert _actions_for("cancel_requested") == [("stop", "Stop", True, "secondary")]


def test_terminal_states_show_start_action() -> None:
    assert _actions_for("completed") == [("start", "Start", False, "primary")]
    assert _actions_for("failed") == [("start", "Start", False, "primary")]
    assert _actions_for("stopped") == [("start", "Start", False, "primary")]
