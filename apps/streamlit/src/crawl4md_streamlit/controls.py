"""Small UI-state helpers for the crawl4md Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_ACTION_START = "start"
_ACTION_STOP = "stop"

_BUTTON_TYPE_PRIMARY = "primary"
_BUTTON_TYPE_SECONDARY = "secondary"

_ICON_START = ":material/play_arrow:"
_ICON_STOP = ":material/stop_circle:"

_LABEL_START = "Start"
_LABEL_STOP = "Stop"

_STATE_CANCEL_REQUESTED = "cancel_requested"
_STATE_RUNNING = "running"


CrawlActionName = Literal["start", "stop"]
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
) -> tuple[CrawlActionButton, ...]:
    """Return the action buttons that should be visible for a crawl state."""
    if state == _STATE_CANCEL_REQUESTED:
        return (
            CrawlActionButton(
                action=_ACTION_STOP,
                label=_LABEL_STOP,
                icon=_ICON_STOP,
                button_type=_BUTTON_TYPE_SECONDARY,
                disabled=True,
            ),
        )
    if state == _STATE_RUNNING or job_alive:
        return (
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
        ),
    )
