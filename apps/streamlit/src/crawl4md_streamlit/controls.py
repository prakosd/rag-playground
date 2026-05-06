"""Small UI-state helpers for the crawl4md Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_ACTION_PAUSE = "pause"
_ACTION_PREPARING_RESUME = "preparing_resume"
_ACTION_RESUME = "resume"
_ACTION_START = "start"
_ACTION_STOP = "stop"

_BUTTON_TYPE_PRIMARY = "primary"
_BUTTON_TYPE_SECONDARY = "secondary"

_ICON_PAUSE = ":material/pause:"
_ICON_PREPARING_RESUME = ":material/hourglass_top:"
_ICON_RESUME = ":material/play_arrow:"
_ICON_START = ":material/play_arrow:"
_ICON_STOP = ":material/stop_circle:"

_LABEL_PAUSE = "Pause"
_LABEL_PREPARING_RESUME = "Preparing resume..."
_LABEL_RESUME = "Resume"
_LABEL_START = "Start"
_LABEL_STOP = "Stop"

_STATE_CANCEL_REQUESTED = "cancel_requested"
_STATE_PAUSED = "paused"
_STATE_PAUSING = "pausing"
_STATE_RUNNING = "running"


CrawlActionName = Literal[
    "pause",
    "preparing_resume",
    "resume",
    "start",
    "stop",
]
ButtonType = Literal["primary", "secondary"]


@dataclass(frozen=True)
class CrawlActionButton:
    """A Streamlit form button needed for the current crawl state."""

    action: CrawlActionName
    label: str
    icon: str
    button_type: ButtonType
    disabled: bool = False


def crawl_action_buttons(
    state: str,
    *,
    job_alive: bool,
    resume_ready: bool,
    stop_requested: bool,
) -> tuple[CrawlActionButton, ...]:
    """Return the action buttons that should be visible for a crawl state."""
    action_state = _STATE_PAUSING if state == _STATE_CANCEL_REQUESTED else state
    if action_state == _STATE_RUNNING:
        return (
            CrawlActionButton(
                action=_ACTION_START,
                label=_LABEL_START,
                icon=_ICON_START,
                button_type=_BUTTON_TYPE_PRIMARY,
                disabled=True,
            ),
            CrawlActionButton(
                action=_ACTION_PAUSE,
                label=_LABEL_PAUSE,
                icon=_ICON_PAUSE,
                button_type=_BUTTON_TYPE_SECONDARY,
            ),
        )
    if action_state == _STATE_PAUSING:
        return (
            CrawlActionButton(
                action=_ACTION_PREPARING_RESUME,
                label=_LABEL_PREPARING_RESUME,
                icon=_ICON_PREPARING_RESUME,
                button_type=_BUTTON_TYPE_SECONDARY,
                disabled=True,
            ),
            CrawlActionButton(
                action=_ACTION_STOP,
                label=_LABEL_STOP,
                icon=_ICON_STOP,
                button_type=_BUTTON_TYPE_SECONDARY,
                disabled=stop_requested,
            ),
        )
    if action_state == _STATE_PAUSED:
        return (
            CrawlActionButton(
                action=_ACTION_RESUME,
                label=_LABEL_RESUME,
                icon=_ICON_RESUME,
                button_type=_BUTTON_TYPE_PRIMARY,
                disabled=not resume_ready,
            ),
            CrawlActionButton(
                action=_ACTION_STOP,
                label=_LABEL_STOP,
                icon=_ICON_STOP,
                button_type=_BUTTON_TYPE_SECONDARY,
            ),
        )
    return (
        CrawlActionButton(
            action=_ACTION_START,
            label=_LABEL_START,
            icon=_ICON_START,
            button_type=_BUTTON_TYPE_PRIMARY,
            disabled=job_alive,
        ),
    )
