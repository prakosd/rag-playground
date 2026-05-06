from __future__ import annotations

from crawl4md_streamlit.controls import crawl_action_buttons


def _actions_for(state: str, *, resume_ready: bool = False) -> list[tuple[str, str, bool, str]]:
    return [
        (button.action, button.label, button.disabled, button.button_type)
        for button in crawl_action_buttons(
            state,
            job_alive=state == "running",
            resume_ready=resume_ready,
            stop_requested=False,
        )
    ]


def test_idle_shows_green_start_action() -> None:
    assert _actions_for("idle") == [("start", "Start", False, "primary")]


def test_running_shows_disabled_start_and_pause() -> None:
    assert _actions_for("running") == [
        ("start", "Start", True, "primary"),
        ("pause", "Pause", False, "secondary"),
    ]


def test_pausing_shows_preparing_resume_and_stop() -> None:
    assert _actions_for("pausing") == [
        ("preparing_resume", "Preparing resume...", True, "secondary"),
        ("stop", "Stop", False, "secondary"),
    ]


def test_cancel_requested_uses_pausing_actions() -> None:
    assert _actions_for("cancel_requested") == _actions_for("pausing")


def test_paused_shows_resume_and_stop_without_start() -> None:
    assert _actions_for("paused", resume_ready=True) == [
        ("resume", "Resume", False, "primary"),
        ("stop", "Stop", False, "secondary"),
    ]


def test_paused_resume_stays_disabled_until_ready() -> None:
    assert _actions_for("paused", resume_ready=False) == [
        ("resume", "Resume", True, "primary"),
        ("stop", "Stop", False, "secondary"),
    ]
