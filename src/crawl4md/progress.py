"""Real-time progress reporting for Jupyter and terminal."""

from __future__ import annotations

import math
import sys
import time
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_CSV_FILE as _ACTIVITY_LOG_CSV_FILE,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_CSV_HEADER as _ACTIVITY_LOG_CSV_HEADER,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_FLUSH_EVERY as _ACTIVITY_LOG_FLUSH_EVERY,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_TXT_FILE as _ACTIVITY_LOG_TXT_FILE,
)
from crawl4md._internal.activity_log import (
    ActivityLogger,
)

# Maximum number of recent activities shown in the activity log.
_MAX_LOG_ENTRIES = 10

# IPython shell class names that indicate a notebook environment.
_NOTEBOOK_SHELL_NAMES = frozenset({"ZMQInteractiveShell", "Shell"})

# ---------------------------------------------------------------------------
# ETA / duration formatting
# ---------------------------------------------------------------------------
# Shown while ETA cannot yet be calculated (no pages completed).
_ETA_PLACEHOLDER = "estimating..."
# Durations shorter than this threshold are displayed as "<0.1s".
_SHORT_DURATION_THRESHOLD = 0.1

# ---------------------------------------------------------------------------
# Google Colab detection
# ---------------------------------------------------------------------------
# sys.modules key that indicates Google Colab runtime.
_COLAB_MODULE = "google.colab"
# HTML attribute and value used to detect Colab dark theme.
_COLAB_THEME_ATTR = "data-colab-attr-theme"
_COLAB_DARK_VALUE = "dark"

# ---------------------------------------------------------------------------
# Activity label truncation limits (characters)
# ---------------------------------------------------------------------------
# Maximum display length for the current-activity label.
_ACTIVITY_LABEL_MAX_LEN = 80
# Slice endpoint when truncating with an ellipsis character.
_ACTIVITY_LABEL_TRUNC = 77
# Maximum display length for activity-log labels.
_LOG_LABEL_MAX_LEN = 70
# Slice endpoint when truncating log labels.
_LOG_LABEL_TRUNC = 67

# ---------------------------------------------------------------------------
# Activity icon mapping (keyword → emoji)
# ---------------------------------------------------------------------------
_ACTIVITY_ICONS: dict[str, str] = {
    "failed": "❌",
    "skip": "⏭️",
    "no content": "📭",
    "reading page": "🌐",
    "downloading": "📥",
    "saving": "💾",
    "pausing": "⏸️",
    "waiting": "⏳",
    "blocking": "🛡️",
    "finding": "🔍",
    "found": "🔗",
}
# Fallback icon when no keyword matches.
_ACTIVITY_ICON_DEFAULT = "⚙️"

# Minimum seconds between notebook widget refreshes during active crawling.
_DISPLAY_MIN_INTERVAL_S = 0.25

# Separator string used to join header parts (e.g. "Round 1 · Page 5 / 10")
_HEADER_SEPARATOR = " · "
# Minimum spider column width percentage to keep it visible at 0% progress
_SPIDER_MIN_WIDTH_PCT = 2

# ---------------------------------------------------------------------------
# Spider wander animation — spider walks back and forth across the filled bar
# ---------------------------------------------------------------------------
# Minimum animation cycle duration (seconds) for small progress values.
_SPIDER_WANDER_MIN_DURATION_S = 3
# Maximum animation cycle duration (seconds) at 100% progress.
_SPIDER_WANDER_MAX_DURATION_S = 8
# Colab: sine-wave cycle period (seconds) for deterministic spider positioning.
_SPIDER_WANDER_CYCLE_S = 6
# Vertical bob amplitude in pixels during spider walk animation.
_SPIDER_BOB_PX = 3
# Spider emoji font size in pixels.
_SPIDER_FONT_SIZE_PX = 30
# Tilt angle (degrees) so the spider faces its direction of travel.
_SPIDER_TILT_DEG = 90
# Minimum completed pages before showing pages-per-minute rate
_RATE_MIN_PAGES = 2
# Explainer text shown on the first render (before any page completes)
_EXPLAINER_TEXT = (
    "Pages are being read and saved automatically. This may take a while for large sites."
)

# ---------------------------------------------------------------------------
# Phase-based bar gradients (threshold, light_gradient, dark_gradient)
# Bar color shifts through phases as progress increases for a "leveling up" feel.
# ---------------------------------------------------------------------------
_BAR_GRADIENTS: list[tuple[int, str, str]] = [
    (100, "linear-gradient(90deg,#ffd54f,#ffe082)", "linear-gradient(90deg,#ffd54f,#ffe082)"),
    (75, "linear-gradient(90deg,#ffa726,#ffb74d)", "linear-gradient(90deg,#ffa726,#ffb74d)"),
    (50, "linear-gradient(90deg,#43a047,#66bb6a)", "linear-gradient(90deg,#43a047,#66bb6a)"),
    (25, "linear-gradient(90deg,#26c6da,#4dd0e1)", "linear-gradient(90deg,#26c6da,#4dd0e1)"),
    (0, "linear-gradient(90deg,#42a5f5,#64b5f6)", "linear-gradient(90deg,#42a5f5,#64b5f6)"),
]

# Percentage label color matching each bar phase (light, dark).
_PCT_PHASE_COLORS: list[tuple[int, str, str]] = [
    (100, "#ffa726", "#ffe082"),
    (75, "#f57c00", "#ffb74d"),
    (50, "#43a047", "#81c784"),
    (25, "#00acc1", "#4dd0e1"),
    (0, "#1e88e5", "#64b5f6"),
]

# ---------------------------------------------------------------------------
# Milestone markers on the progress bar track.
# ---------------------------------------------------------------------------
_MILESTONES: list[int] = [25, 50, 75]

# ---------------------------------------------------------------------------
# Activity-aware pulse colors by category (light, dark).
# ---------------------------------------------------------------------------
_PULSE_COLORS: dict[str, tuple[str, str]] = {
    "crawl": ("#1a73e8", "#64b5f6"),
    "extract": ("#43a047", "#81c784"),
    "delay": ("#f9a825", "#fdd835"),
    "fail": ("#d32f2f", "#ef5350"),
}
# Default pulse color when category is unknown.
_PULSE_COLOR_DEFAULT: tuple[str, str] = ("#1a73e8", "#64b5f6")

# ---------------------------------------------------------------------------
# Celebratory milestone messages (checked descending; first match wins).
# ---------------------------------------------------------------------------
_MILESTONE_MESSAGES: list[tuple[int, str]] = [
    (100, "✨ Web complete!"),
    (75, "🔥 Almost done!"),
    (50, "🎯 Halfway there!"),
    (25, "🕷️ Making good progress!"),
    (1, "🕷️ Crawling..."),
    (0, "🕸️ Spinning up..."),
]

# ---------------------------------------------------------------------------
# Color palettes for light and dark themes
# ---------------------------------------------------------------------------
_LIGHT_COLORS: dict[str, str] = {
    "text": "#333",
    "header": "#111",
    "bar_bg": "#e8eaed",
    "bar_gradient": "linear-gradient(90deg,#43a047,#66bb6a)",
    "activity": "#1a73e8",
    "pulse": "#1a73e8",
    "duration": "#888",
    "log_heading": "#888",
    "log_text": "#555",
    "log_time": "#999",
    "log_dur": "#888",
    "log_fail": "#d32f2f",
    "footer": "#333",
    "pct": "#43a047",
    "thread": "#999",
    "web": "#bbb",
    "bar_glow": "rgba(255,255,255,0.2)",
    "pill_success_bg": "rgba(76,175,80,0.10)",
    "pill_fail_bg": "rgba(244,67,54,0.08)",
    "pill_total_bg": "rgba(0,0,0,0.04)",
    "milestone": "#bbb",
    "milestone_done": "#43a047",
}

_DARK_COLORS: dict[str, str] = {
    "text": "#e0e0e0",
    "header": "#f0f0f0",
    "bar_bg": "#3a3a3a",
    "bar_gradient": "linear-gradient(90deg,#43a047,#66bb6a)",
    "activity": "#64b5f6",
    "pulse": "#64b5f6",
    "duration": "#aaa",
    "log_heading": "#aaa",
    "log_text": "#bbb",
    "log_time": "#999",
    "log_dur": "#aaa",
    "log_fail": "#ef5350",
    "footer": "#d0d0d0",
    "pct": "#81c784",
    "thread": "#888",
    "web": "#666",
    "bar_glow": "rgba(255,255,255,0.12)",
    "pill_success_bg": "rgba(129,199,132,0.12)",
    "pill_fail_bg": "rgba(239,83,80,0.12)",
    "pill_total_bg": "rgba(255,255,255,0.06)",
    "milestone": "#666",
    "milestone_done": "#81c784",
}


def _in_notebook() -> bool:
    """Detect whether we are running inside a Jupyter/IPython notebook."""
    try:
        from IPython import get_ipython  # type: ignore[import-untyped]

        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ in _NOTEBOOK_SHELL_NAMES
    except ImportError:
        return False


def _in_colab() -> bool:
    """Detect whether we are running inside Google Colab."""
    return _COLAB_MODULE in sys.modules


def _colab_is_dark() -> bool:
    """Detect whether Google Colab is using a dark theme.

    Uses ``google.colab.output.eval_js`` to read the ``data-colab-attr-theme``
    attribute from the ``<html>`` element.  Returns ``False`` (light mode) if
    detection fails for any reason.
    """
    try:
        from google.colab import output  # type: ignore[import-untyped]

        theme = output.eval_js(f"document.documentElement.getAttribute('{_COLAB_THEME_ATTR}')")
        return str(theme).strip().lower() == _COLAB_DARK_VALUE
    except Exception:  # noqa: BLE001
        return False


class ProgressReporter:
    """Displays crawl progress to the user in real time."""

    def __init__(
        self,
        total: int,
        *,
        action: str = "Crawled",
        prior_success: int = 0,
        prior_fail: int = 0,
        round_label: str = "",
        max_log_entries: int = _MAX_LOG_ENTRIES,
        log_dir: Path | None = None,
    ) -> None:
        self.total = total
        self.count = 0
        self.action = action
        self._start_time = time.time()
        self._use_notebook = _in_notebook()
        self._use_colab = self._use_notebook and _in_colab()
        self._prior_success = prior_success
        self._prior_fail = prior_fail
        self._round_success = 0
        self._round_fail = 0
        self._round_label = round_label
        self._max_log_entries = max_log_entries
        self._log_dir = log_dir

        # Activity tracking
        self._current_activity: str = ""
        self._activity_start: float = 0.0
        self._activity_log: deque[tuple[datetime, str, float]] = deque(
            maxlen=max_log_entries if max_log_entries > 0 else None
        )
        self._activity_logger = ActivityLogger(
            log_dir=log_dir,
            round_label=round_label,
            icon_for_label=_ProgressWidget._activity_icon,
            format_duration=_ProgressWidget._fmt_duration,
        )
        self._last_refresh_ts = 0.0

    def __del__(self) -> None:
        with suppress(Exception):
            self._close_disk_log_handles()

    def _elapsed(self) -> str:
        seconds = int(time.time() - self._start_time)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def _eta_remaining(self) -> str:
        """Estimated time remaining."""
        if self.count == 0:
            return _ETA_PLACEHOLDER
        elapsed = time.time() - self._start_time
        remaining = elapsed / self.count * (self.total - self.count)
        mins, secs = divmod(int(remaining), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins:02d}m {secs:02d}s"
        return f"{mins:02d}:{secs:02d}"

    def _eta_finish_time(self) -> str:
        """Estimated wall-clock finish time."""
        if self.count == 0:
            return _ETA_PLACEHOLDER
        elapsed = time.time() - self._start_time
        remaining = elapsed / self.count * (self.total - self.count)
        finish = datetime.now() + timedelta(seconds=remaining)
        return finish.strftime("%H:%M:%S")

    def _eta_remaining_friendly(self) -> str:
        """Estimated time remaining as natural language (e.g. 'About 3 minutes left')."""
        if self.count == 0:
            return _ETA_PLACEHOLDER
        elapsed = time.time() - self._start_time
        remaining = int(elapsed / self.count * (self.total - self.count))
        if remaining < 60:
            return "Less than a minute left"
        hours, mins = divmod(remaining // 60, 60)
        if hours > 0:
            parts = [f"{hours} hour{'s' if hours != 1 else ''}"]
            if mins > 0:
                parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
            return f"About {' '.join(parts)} left"
        return f"About {mins} minute{'s' if mins != 1 else ''} left"

    def eta_remaining_seconds(self) -> float | None:
        """Remaining seconds estimated from current rate, or None if not yet computable."""
        if self.count == 0:
            return None
        elapsed = time.time() - self._start_time
        return elapsed / self.count * max(self.total - self.count, 0)

    # ------------------------------------------------------------------
    # Activity tracking
    # ------------------------------------------------------------------

    def set_activity(self, activity: str) -> None:
        """Record a new current activity (e.g. 'Crawling …', 'Extracting')."""
        self._close_activity()
        self._current_activity = activity
        self._activity_start = time.time()
        if self._use_notebook:
            self._refresh_display()

    def _close_activity(self) -> None:
        """Close the current activity and append it to the log."""
        if self._current_activity and self._activity_start > 0:
            duration = time.time() - self._activity_start
            ts = datetime.now()
            self._activity_log.append((ts, self._current_activity, duration))
            self._append_to_disk(ts, self._current_activity, duration)
        self._current_activity = ""
        self._activity_start = 0.0

    def _append_to_disk(self, ts: datetime, label: str, duration: float) -> None:
        """Append one activity entry to the TXT and CSV log files on disk."""
        self._activity_logger.append(ts, label, duration)

    def _ensure_disk_log_handles(self):
        return self._activity_logger.ensure_handles()

    def _flush_disk_logs(self) -> None:
        self._activity_logger.flush()

    def _close_disk_log_handles(self) -> None:
        self._activity_logger.close()

    def close(self) -> None:
        self._close_activity()
        self._close_disk_log_handles()

    def update_activity_label(self, label: str) -> None:
        """Update the label of the current activity without closing it."""
        self._current_activity = label
        if self._use_notebook:
            self._refresh_display()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _refresh_display(self, *, force: bool = False) -> None:
        """Refresh the Jupyter widget (notebook mode only)."""
        if not self._use_notebook:
            return
        now = time.time()
        if (
            not force
            and self._last_refresh_ts > 0
            and now - self._last_refresh_ts < _DISPLAY_MIN_INTERVAL_S
        ):
            return
        self._last_refresh_ts = now
        from IPython.display import HTML, clear_output, display  # type: ignore[import-untyped]

        clear_output(wait=True)
        widget = self._build_widget()
        if self._use_colab:
            display(HTML(widget._repr_html_()))
        else:
            display(widget)

    def _build_widget(self) -> _ProgressWidget:
        """Construct the widget with current state."""
        eta = self._eta_remaining_friendly()
        total_crawled = (
            self._prior_success + self._prior_fail + self._round_success + self._round_fail
        )
        total_success = self._prior_success + self._round_success
        total_fail = self._prior_fail + self._round_fail
        stats = f"\u2705 {total_success} &nbsp; \u274c {total_fail} &nbsp; \U0001f4c4 {total_crawled} total"

        # Pages-per-minute rate (shown after enough data)
        pages_per_min = ""
        elapsed = time.time() - self._start_time
        if self.count >= _RATE_MIN_PAGES and elapsed > 0:
            rate = self.count / elapsed * 60
            pages_per_min = f"~{rate:.0f} pages/min"

        activity_est_duration = ""
        activity_category = ""
        if self._current_activity and self._activity_start > 0:
            # Estimate finish from avg duration of same-category activities
            cat = _ProgressWidget._activity_category(self._current_activity)
            activity_category = cat
            durations = [
                d
                for _, lbl, d in self._activity_log
                if _ProgressWidget._activity_category(lbl) == cat
            ]
            if durations:
                avg = sum(durations) / len(durations)
                activity_est_duration = _ProgressWidget._fmt_duration(avg)

        return _ProgressWidget(
            current=self.count,
            total=self.total,
            eta=eta,
            stats=stats,
            pages_per_min=pages_per_min,
            round_label=self._round_label,
            activity=self._current_activity,
            activity_est_duration=activity_est_duration,
            activity_category=activity_category,
            activity_log=list(self._activity_log),
            success_count=total_success,
            fail_count=total_fail,
            total_count=total_crawled,
            colab=self._use_colab,
            dark=self._use_colab and _colab_is_dark(),
        )

    def update(self, url: str, *, success: bool = True) -> None:
        """Report that a page has been processed."""
        if not success and self._current_activity:
            self._current_activity = f"\u274c FAILED \u2014 {self._current_activity}"
        self._close_activity()
        self.count += 1
        if success:
            self._round_success += 1
        else:
            self._round_fail += 1

        if self._use_notebook:
            self._refresh_display()
        else:
            eta = self._eta_remaining_friendly()
            msg = f"[{self.count}/{self.total}] ({self._elapsed()}) {self.action}: {url}"
            total_crawled = (
                self._prior_success + self._prior_fail + self._round_success + self._round_fail
            )
            total_success = self._prior_success + self._round_success
            total_fail = self._prior_fail + self._round_fail
            rate_info = ""
            elapsed = time.time() - self._start_time
            if self.count >= _RATE_MIN_PAGES and elapsed > 0:
                rate = self.count / elapsed * 60
                rate_info = f" (~{rate:.0f} pages/min)"
            stats = (
                f"\u2705 {total_success}  \u274c {total_fail}"
                f"  \U0001f4c4 {total_crawled} total{rate_info}"
            )
            print(f"{msg}  |  {eta}")
            print(stats)

    def finish(self, output_dir: str | None = None) -> None:
        """Report that processing is complete."""
        self.close()
        msg = f"\nDone! {self.action} {self.count} page(s) in {self._elapsed()}."
        if output_dir:
            msg += f"\nOutput folder: {output_dir}"
        if self._use_notebook:
            self._refresh_display(force=True)
            print(msg)
        else:
            print(msg)


class _ProgressWidget:
    """Rich HTML progress widget with animated spider for Jupyter notebooks."""

    def __init__(
        self,
        current: int,
        total: int,
        eta: str = "",
        stats: str = "",
        pages_per_min: str = "",
        round_label: str = "",
        activity: str = "",
        activity_est_duration: str = "",
        activity_category: str = "",
        activity_log: list[tuple[datetime, str, float]] | None = None,
        success_count: int = 0,
        fail_count: int = 0,
        total_count: int = 0,
        *,
        colab: bool = False,
        dark: bool = False,
    ) -> None:
        self.current = current
        self.total = total
        self.eta = eta
        self.stats = stats
        self.pages_per_min = pages_per_min
        self.round_label = round_label
        self.activity = activity
        self.activity_est_duration = activity_est_duration
        self.activity_category = activity_category
        self.activity_log = activity_log or []
        self.success_count = success_count
        self.fail_count = fail_count
        self.total_count = total_count
        self.colab = colab
        self.dark = dark

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        """Format a duration as a compact human-readable string."""
        if seconds < _SHORT_DURATION_THRESHOLD:
            return "<0.1s"
        if seconds < 60:
            return f"{seconds:.1f}s"
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs:02d}s"

    @staticmethod
    def _activity_category(label: str) -> str:
        """Categorise an activity label for ETA averaging."""
        low = label.lower()
        if "reading page" in low or "downloading" in low:
            return "crawl"
        if "saving page" in low or "saving pdf" in low:
            return "extract"
        if "saving progress" in low:
            return "flush"
        if "pausing" in low or "waiting" in low or "blocking" in low:
            return "delay"
        if "finding" in low or "found" in low:
            return "discover"
        return "other"

    @staticmethod
    def _activity_icon(label: str) -> str:
        """Pick a small icon for the activity label."""
        low = label.lower()
        for keyword, icon in _ACTIVITY_ICONS.items():
            if keyword in low:
                return icon
        return _ACTIVITY_ICON_DEFAULT

    @staticmethod
    def _bar_gradient(pct: int, *, dark: bool = False) -> str:
        """Return the bar gradient string for a given progress percentage."""
        idx = 1 if dark else 0  # _BAR_GRADIENTS stores (threshold, light, dark)
        for threshold, light, dark_g in _BAR_GRADIENTS:
            if pct >= threshold:
                return dark_g if dark else light
        return _BAR_GRADIENTS[-1][1 + idx]

    @staticmethod
    def _pct_color(pct: int, *, dark: bool = False) -> str:
        """Return the percentage label color matching the current bar phase."""
        for threshold, light, dark_c in _PCT_PHASE_COLORS:
            if pct >= threshold:
                return dark_c if dark else light
        return _PCT_PHASE_COLORS[-1][2 if dark else 1]

    @staticmethod
    def _milestone_message(pct: int) -> str:
        """Return a celebratory message for the current progress level."""
        for threshold, msg in _MILESTONE_MESSAGES:
            if pct >= threshold:
                return msg
        return ""

    @staticmethod
    def _pulse_color(category: str, *, dark: bool = False) -> str:
        """Return the pulse dot color for a given activity category."""
        pair = _PULSE_COLORS.get(category, _PULSE_COLOR_DEFAULT)
        return pair[1] if dark else pair[0]

    @staticmethod
    def _web_svg(web_color: str, *, display_block: bool = False) -> str:
        """Render the small web decoration used by Jupyter and Colab widgets."""
        style_attr = ' style="display:block"' if display_block else ""
        return (
            f'<svg width="28" height="28" viewBox="0 0 28 28" fill="none"'
            f"{style_attr}"
            f' xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M0 0 Q0 14 14 14" stroke="{web_color}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 21 21 21" stroke="{web_color}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 28 28 28" stroke="{web_color}" stroke-width="0.8" fill="none"/>'
            f'<line x1="0" y1="0" x2="14" y2="0" stroke="{web_color}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="0" y2="14" stroke="{web_color}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="10" y2="10" stroke="{web_color}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="4" y2="13" stroke="{web_color}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="13" y2="4" stroke="{web_color}" stroke-width="0.8"/>'
            f"</svg>"
        )

    def _activity_log_row_html(
        self,
        ts: datetime,
        label: str,
        duration: float,
        *,
        colab: bool,
        colors: dict[str, str],
    ) -> str:
        icon = self._activity_icon(label)
        display_label = (
            label if len(label) <= _LOG_LABEL_MAX_LEN else label[:_LOG_LABEL_TRUNC] + "…"
        )
        ts_str = ts.strftime("%H:%M:%S")
        is_fail = label.startswith("\u274c")
        if colab:
            label_color = f"color:{colors['log_fail']}" if is_fail else ""
            return (
                f"<tr>"
                f'<td style="white-space:nowrap;font-family:monospace;'
                f"color:{colors['log_time']};"
                f'font-size:11px;width:58px;padding:1px 4px">{ts_str}</td>'
                f'<td style="width:18px;text-align:center;padding:1px 4px">{icon}</td>'
                f'<td style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                f'max-width:460px;padding:1px 4px;{label_color}">{display_label}</td>'
                f'<td style="text-align:right;color:{colors["log_dur"]};white-space:nowrap;'
                f'padding:1px 4px">{self._fmt_duration(duration)}</td>'
                f"</tr>"
            )
        label_cls = "c4md-log-label c4md-log-fail" if is_fail else "c4md-log-label"
        return (
            f"<tr>"
            f'<td class="c4md-log-time">{ts_str}</td>'
            f'<td class="c4md-log-icon">{icon}</td>'
            f'<td class="{label_cls}">{display_label}</td>'
            f'<td class="c4md-log-dur">{self._fmt_duration(duration)}</td>'
            f"</tr>"
        )

    def _repr_html_(self) -> str:
        if self.colab:
            return self._repr_html_colab()
        pct = int(self.current / self.total * 100) if self.total else 0

        # --- Phase-based gradient + pct color ---
        bar_grad = self._bar_gradient(pct)
        bar_grad_dark = self._bar_gradient(pct, dark=True)
        pct_color = self._pct_color(pct)
        pct_color_dark = self._pct_color(pct, dark=True)

        # --- Milestone message ---
        milestone_msg = self._milestone_message(pct)
        milestone_span = ""
        if milestone_msg:
            milestone_span = f'<span class="c4md-milestone-msg">{milestone_msg}</span>'

        # --- Header ---
        header_parts = []
        if self.round_label:
            header_parts.append(self.round_label)
        header_parts.append(f"Page {self.current} / {self.total}")
        header = _HEADER_SEPARATOR.join(header_parts)

        # --- Explainer (first render only) ---
        explainer_html = ""
        if self.current == 0:
            explainer_html = f'<div class="c4md-explainer">{_EXPLAINER_TEXT}</div>'

        # --- Activity row (with activity-aware pulse color) ---
        activity_html = ""
        if self.activity:
            icon = self._activity_icon(self.activity)
            display_label = self.activity
            if len(display_label) > _ACTIVITY_LABEL_MAX_LEN:
                display_label = display_label[:_ACTIVITY_LABEL_TRUNC] + "…"
            time_span = ""
            if self.activity_est_duration:
                time_span = f'<span class="c4md-dur"> (~{self.activity_est_duration})</span>'
            pulse_col = self._pulse_color(self.activity_category)
            activity_html = (
                f'<div class="c4md-activity">'
                f'<span class="c4md-pulse" style="background:{pulse_col}"></span>'
                f" {icon} {display_label}"
                f"{time_span}"
                f"</div>"
            )

        # --- Activity log (collapsible) ---
        log_html = ""
        if self.activity_log:
            rows = ""
            for ts, label, dur in reversed(self.activity_log):
                rows += self._activity_log_row_html(
                    ts,
                    label,
                    dur,
                    colab=False,
                    colors=_LIGHT_COLORS,
                )
            log_html = (
                f'<div class="c4md-log">'
                f"<details>"
                f'<summary class="c4md-log-heading">'
                f"Activity Log ({len(self.activity_log)} entries)</summary>"
                f'<table class="c4md-log-table">{rows}</table>'
                f"</details>"
                f"</div>"
            )

        # --- Stats pills ---
        pills_html = self._pills_html(pct=pct, colab=False, dark=False)

        # --- Footer (pills + rate + eta) ---
        footer_parts = [pills_html]
        if self.pages_per_min:
            footer_parts.append(self.pages_per_min)
        if self.eta:
            footer_parts.append(self.eta)
        footer = " &nbsp;·&nbsp; ".join(footer_parts)

        # --- Milestone markers (tick marks at 25/50/75%) ---
        milestone_marks = ""
        for m in _MILESTONES:
            done = pct >= m
            cls = "c4md-mark c4md-mark-done" if done else "c4md-mark"
            label = "✓" if done else ""
            milestone_marks += f'<div class="{cls}" style="left:{m}%">{label}</div>'

        lt = _LIGHT_COLORS
        dk = _DARK_COLORS

        return (
            f'<div class="c4md-widget">'
            f"<style>"
            f".c4md-widget {{"
            f"  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            f"  font-size: 13px; color: {lt['text']}; max-width: 680px;"
            f"}}"
            f".c4md-header {{"
            f"  font-weight: 600; font-size: 14px; margin-bottom: 8px; color: {lt['header']};"
            f"}}"
            # Milestone message next to header
            f".c4md-milestone-msg {{"
            f"  font-weight: 400; font-size: 12px; margin-left: 8px;"
            f"  color: {lt['duration']}; font-style: italic;"
            f"}}"
            # Progress bar container
            f".c4md-bar-wrap {{"
            f"  position: relative; background: {lt['bar_bg']}; border-radius: 10px;"
            f"  height: 22px; overflow: visible; margin-bottom: 6px;"
            f"}}"
            f".c4md-bar {{"
            f"  position: relative;"
            f"  background: {bar_grad};"
            f"  height: 100%; border-radius: 10px;"
            f"  transition: width 0.4s ease, background 0.6s ease;"
            f"  overflow: hidden;"
            f"}}"
            # Candy stripes on filled bar
            f".c4md-bar::before {{"
            f"  content: ''; position: absolute; inset: 0;"
            f"  border-radius: 10px;"
            f"  background: repeating-linear-gradient("
            f"    45deg,"
            f"    rgba(255,255,255,0.12) 0px,"
            f"    rgba(255,255,255,0.12) 10px,"
            f"    transparent 10px,"
            f"    transparent 20px"
            f"  );"
            f"  background-size: 28px 28px;"
            f"  animation: c4md-stripe 0.8s linear infinite;"
            f"}}"
            # Pulsating glow overlay on the filled bar
            f".c4md-bar::after {{"
            f"  content: ''; position: absolute; inset: 0;"
            f"  border-radius: 10px;"
            f"  background: {lt['bar_glow']};"
            f"  animation: c4md-glow 2s ease-in-out infinite;"
            f"}}"
            # Spider web SVG decoration at top-left of bar
            f".c4md-web {{"
            f"  position: absolute; top: -1px; left: -1px; z-index: 1;"
            f"  opacity: 0.18; pointer-events: none;"
            f"}}"
            f".c4md-web svg {{ display: block; }}"
            # Spider track: spans the filled portion of the bar for wander range
            f".c4md-spider-track {{"
            f"  position: absolute; top: -{_SPIDER_FONT_SIZE_PX // 2}px; left: 0; height: {_SPIDER_FONT_SIZE_PX}px;"
            f"  pointer-events: none;"
            f"}}"
            # Spider walks back and forth inside the track
            f".c4md-spider {{"
            f"  position: absolute; top: 0;"
            f"  font-size: {_SPIDER_FONT_SIZE_PX}px; line-height: 1;"
            f"  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));"
            f"  animation: c4md-crawl {max(_SPIDER_WANDER_MIN_DURATION_S, pct / 100 * _SPIDER_WANDER_MAX_DURATION_S):.1f}s ease-in-out infinite;"
            f"}}"
            # Web thread (dashed line from left edge to spider)
            f".c4md-thread {{"
            f"  position: absolute; top: 0px; left: 0; height: 2px;"
            f"  border-top: 1.5px dashed {lt['thread']};"
            f"  transition: width 0.4s ease;"
            f"}}"
            # Milestone tick marks on bar track
            f".c4md-mark {{"
            f"  position: absolute; top: 0; width: 2px; height: 100%;"
            f"  background: {lt['milestone']}; transform: translateX(-1px);"
            f"  font-size: 0; border-radius: 1px; opacity: 0.5;"
            f"  transition: background 0.3s ease, opacity 0.3s ease;"
            f"}}"
            f".c4md-mark-done {{"
            f"  background: {lt['milestone_done']}; opacity: 0.9;"
            f"  font-size: 9px; color: #fff; text-align: center;"
            f"  line-height: 22px; width: 16px; border-radius: 8px;"
            f"  transform: translateX(-8px);"
            f"}}"
            # Spider crawl animation: walks right (tilted right) then walks left (tilted left)
            f"@keyframes c4md-crawl {{"
            f"  0% {{ left: 0; transform: rotate(-{_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"  24% {{ left: calc(100% - {_SPIDER_FONT_SIZE_PX}px); transform: rotate(-{_SPIDER_TILT_DEG}deg) translateY(-{_SPIDER_BOB_PX}px); }}"
            f"  25% {{ left: calc(100% - {_SPIDER_FONT_SIZE_PX}px); transform: rotate({_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"  49% {{ left: calc(100% - {_SPIDER_FONT_SIZE_PX}px); transform: rotate({_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"  50% {{ left: calc(100% - {_SPIDER_FONT_SIZE_PX}px); transform: rotate({_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"  74% {{ left: 0; transform: rotate({_SPIDER_TILT_DEG}deg) translateY(-{_SPIDER_BOB_PX}px); }}"
            f"  75% {{ left: 0; transform: rotate(-{_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"  100% {{ left: 0; transform: rotate(-{_SPIDER_TILT_DEG}deg) translateY(0); }}"
            f"}}"
            f"@keyframes c4md-glow {{"
            f"  0%, 100% {{ opacity: 0; }}"
            f"  50% {{ opacity: 1; }}"
            f"}}"
            # Candy stripe scrolling animation
            f"@keyframes c4md-stripe {{"
            f"  0% {{ background-position: 0 0; }}"
            f"  100% {{ background-position: 28px 0; }}"
            f"}}"
            # Pulsing dot for current activity
            f".c4md-activity {{"
            f"  margin: 6px 0; color: {lt['activity']}; font-size: 12.5px;"
            f"  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            f"}}"
            f".c4md-pulse {{"
            f"  display: inline-block; width: 7px; height: 7px;"
            f"  background: {lt['pulse']}; border-radius: 50%;"
            f"  animation: c4md-blink 1s ease-in-out infinite;"
            f"  vertical-align: middle; margin-right: 4px;"
            f"}}"
            f"@keyframes c4md-blink {{"
            f"  0%, 100% {{ opacity: 1; }}"
            f"  50% {{ opacity: 0.25; }}"
            f"}}"
            f".c4md-dur {{ color: {lt['duration']}; }}"
            # Activity log
            f".c4md-log {{"
            f"  margin-top: 4px; max-height: 200px; overflow-y: auto;"
            f"}}"
            f".c4md-log-heading {{"
            f"  font-size: 11.5px; font-weight: 600; color: {lt['log_heading']};"
            f"  margin-bottom: 2px;"
            f"}}"
            f".c4md-log-table {{"
            f"  width: 100%; font-size: 11.5px; border-collapse: collapse;"
            f"  color: {lt['log_text']};"
            f"}}"
            f".c4md-log-table td {{ padding: 1px 4px; }}"
            f".c4md-log-time {{"
            f"  white-space: nowrap; font-family: monospace; color: {lt['log_time']};"
            f"  font-size: 11px; width: 58px;"
            f"}}"
            f".c4md-log-icon {{ width: 18px; text-align: center; }}"
            f".c4md-log-label {{"
            f"  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            f"  max-width: 460px;"
            f"}}"
            f".c4md-log-dur {{ text-align: right; color: {lt['log_dur']};"
            f"  white-space: nowrap; }}"
            f".c4md-log-fail {{ color: {lt['log_fail']}; }}"
            # Footer + pills
            f".c4md-footer {{"
            f"  margin-top: 6px; font-size: 12px; color: {lt['footer']};"
            f"}}"
            f".c4md-pct {{"
            f"  float: right; font-weight: 600; color: {pct_color};"
            f"}}"
            f".c4md-pill {{"
            f"  display: inline-block; padding: 1px 8px; border-radius: 10px;"
            f"  font-size: 11.5px; font-weight: 500; margin-right: 4px;"
            f"}}"
            f".c4md-pill-success {{ background: {lt['pill_success_bg']}; }}"
            f".c4md-pill-fail {{ background: {lt['pill_fail_bg']}; }}"
            f".c4md-pill-total {{ background: {lt['pill_total_bg']}; }}"
            # Explainer subtitle
            f".c4md-explainer {{"
            f"  font-size: 11.5px; color: {lt['duration']}; margin-bottom: 6px;"
            f"  font-style: italic;"
            f"}}"
            # Dark-mode overrides
            f"@media (prefers-color-scheme: dark) {{"
            f"  .c4md-widget {{ color: {dk['text']}; }}"
            f"  .c4md-header {{ color: {dk['header']}; }}"
            f"  .c4md-bar-wrap {{ background: {dk['bar_bg']}; }}"
            f"  .c4md-bar {{ background: {bar_grad_dark}; }}"
            f"  .c4md-thread {{ border-color: {dk['thread']}; }}"
            f"  .c4md-web svg {{ stroke: {dk['web']}; }}"
            f"  .c4md-bar::after {{ background: {dk['bar_glow']}; }}"
            f"  .c4md-activity {{ color: {dk['activity']}; }}"
            f"  .c4md-pulse {{ background: {dk['pulse']}; }}"
            f"  .c4md-dur {{ color: {dk['duration']}; }}"
            f"  .c4md-log-heading {{ color: {dk['log_heading']}; }}"
            f"  .c4md-log-table {{ color: {dk['log_text']}; }}"
            f"  .c4md-log-time {{ color: {dk['log_time']}; }}"
            f"  .c4md-log-dur {{ color: {dk['log_dur']}; }}"
            f"  .c4md-log-fail {{ color: {dk['log_fail']}; }}"
            f"  .c4md-footer {{ color: {dk['footer']}; }}"
            f"  .c4md-pct {{ color: {pct_color_dark}; }}"
            f"  .c4md-explainer {{ color: {dk['duration']}; }}"
            f"  .c4md-milestone-msg {{ color: {dk['duration']}; }}"
            f"  .c4md-mark {{ background: {dk['milestone']}; }}"
            f"  .c4md-mark-done {{ background: {dk['milestone_done']}; }}"
            f"  .c4md-pill-success {{ background: {dk['pill_success_bg']}; }}"
            f"  .c4md-pill-fail {{ background: {dk['pill_fail_bg']}; }}"
            f"  .c4md-pill-total {{ background: {dk['pill_total_bg']}; }}"
            f"}}"
            f"</style>"
            # Header + milestone message
            f'<div class="c4md-header">{header} {milestone_span}'
            f'<span class="c4md-pct">{pct}%</span></div>'
            # Explainer (first render only)
            f"{explainer_html}"
            # Bar + spider + thread + web decoration + milestone marks
            f'<div class="c4md-bar-wrap">'
            f'<div class="c4md-web">'
            f"{self._web_svg(lt['web'])}</div>"
            f"{milestone_marks}"
            f'<div class="c4md-thread" style="width:{max(pct, 0)}%;"></div>'
            f'<div class="c4md-bar" style="width:{pct}%;"></div>'
            f'<div class="c4md-spider-track" style="width:{max(pct, 0)}%;">'
            f'<div class="c4md-spider">🕷️</div>'
            f"</div>"
            f"</div>"
            # Activity + log
            f"{activity_html}"
            f"{log_html}"
            # Footer
            f'<div class="c4md-footer">{footer}</div>'
            f"</div>"
        )

    def _pills_html(self, *, pct: int, colab: bool, dark: bool) -> str:
        """Render stats as rounded pill badges."""
        c = _DARK_COLORS if dark else _LIGHT_COLORS
        if colab:
            pill = (
                "display:inline-block;padding:1px 8px;border-radius:10px;"
                "font-size:11.5px;font-weight:500;margin-right:4px"
            )
            return (
                f'<span style="{pill};background:{c["pill_success_bg"]}">'
                f"\u2705 {self.success_count}</span>"
                f'<span style="{pill};background:{c["pill_fail_bg"]}">'
                f"\u274c {self.fail_count}</span>"
                f'<span style="{pill};background:{c["pill_total_bg"]}">'
                f"\U0001f4c4 {self.total_count} total</span>"
            )
        return (
            f'<span class="c4md-pill c4md-pill-success">'
            f"\u2705 {self.success_count}</span>"
            f'<span class="c4md-pill c4md-pill-fail">'
            f"\u274c {self.fail_count}</span>"
            f'<span class="c4md-pill c4md-pill-total">'
            f"\U0001f4c4 {self.total_count} total</span>"
        )

    def _repr_html_colab(self) -> str:
        """Colab-safe HTML rendering using only inline styles (no <style> block)."""
        pct = int(self.current / self.total * 100) if self.total else 0
        c = _DARK_COLORS if self.dark else _LIGHT_COLORS

        # Phase-based gradient + pct color
        bar_grad = self._bar_gradient(pct, dark=self.dark)
        pct_color = self._pct_color(pct, dark=self.dark)

        # Milestone message
        milestone_msg = self._milestone_message(pct)
        milestone_span = ""
        if milestone_msg:
            milestone_span = (
                f'<span style="font-weight:400;font-size:12px;margin-left:8px;'
                f'color:{c["duration"]};font-style:italic">{milestone_msg}</span>'
            )

        # Shared inline style fragments
        font = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif"

        # --- Header ---
        header_parts = []
        if self.round_label:
            header_parts.append(self.round_label)
        header_parts.append(f"Page {self.current} / {self.total}")
        header = _HEADER_SEPARATOR.join(header_parts)

        # --- Explainer (first render only) ---
        explainer_html = ""
        if self.current == 0:
            explainer_html = (
                f'<div style="font-size:11.5px;color:{c["duration"]};'
                f'margin-bottom:6px;font-style:italic">{_EXPLAINER_TEXT}</div>'
            )

        # --- Activity row (with activity-aware pulse color) ---
        activity_html = ""
        if self.activity:
            icon = self._activity_icon(self.activity)
            display_label = self.activity
            if len(display_label) > _ACTIVITY_LABEL_MAX_LEN:
                display_label = display_label[:_ACTIVITY_LABEL_TRUNC] + "\u2026"
            time_span = ""
            if self.activity_est_duration:
                time_span = (
                    f'<span style="color:{c["duration"]}"> (~{self.activity_est_duration})</span>'
                )
            pulse_col = self._pulse_color(self.activity_category, dark=self.dark)
            activity_html = (
                f'<div style="margin:6px 0;color:{c["activity"]};font-size:12.5px;{font}">'
                f'<span style="display:inline-block;width:8px;height:8px;'
                f"background:{pulse_col};border-radius:50%;vertical-align:middle;"
                f'margin-right:5px"></span>'
                f" {icon} {display_label}"
                f"{time_span}"
                f"</div>"
            )

        # --- Activity log (always visible in Colab — no <details>) ---
        log_html = ""
        if self.activity_log:
            rows = ""
            for ts, label, dur in reversed(self.activity_log):
                rows += self._activity_log_row_html(ts, label, dur, colab=True, colors=c)
            log_html = (
                f'<div style="margin-top:4px;max-height:200px;overflow-y:auto">'
                f'<div style="font-size:11.5px;font-weight:600;color:{c["log_heading"]};'
                f'margin-bottom:2px">Activity Log ({len(self.activity_log)} entries)</div>'
                f'<table style="width:100%;font-size:11.5px;border-collapse:collapse;'
                f'color:{c["log_text"]}">{rows}</table>'
                f"</div>"
            )

        # --- Stats pills + ETA ---
        pills = self._pills_html(pct=pct, colab=True, dark=self.dark)
        footer_parts = [pills]
        if self.pages_per_min:
            footer_parts.append(self.pages_per_min)
        if self.eta:
            footer_parts.append(self.eta)
        footer = " &nbsp;\u00b7&nbsp; ".join(footer_parts)

        # Spider wander: deterministic sine-wave position within [0, pct].
        # Each re-render places the spider at a different spot in the filled region.
        if pct > 0:
            phase = (time.time() % _SPIDER_WANDER_CYCLE_S) / _SPIDER_WANDER_CYCLE_S
            sine_val = 0.5 + 0.5 * math.sin(2 * math.pi * phase - math.pi / 2)
            spider_pos = max(_SPIDER_MIN_WIDTH_PCT, pct * sine_val)
            # Flip spider when heading left (negative derivative of sine)
            heading_left = math.cos(2 * math.pi * phase - math.pi / 2) < 0
        else:
            spider_pos = _SPIDER_MIN_WIDTH_PCT
            heading_left = False
        spider_flip = (
            f"display:inline-block;transform:rotate({_SPIDER_TILT_DEG}deg)"
            if heading_left
            else f"display:inline-block;transform:rotate(-{_SPIDER_TILT_DEG}deg)"
        )
        # Spider web SVG (inline, overlaps bar via negative margin)
        web_svg = self._web_svg(c["web"], display_block=True)

        # Milestone markers below bar (flex row — Colab-safe, no position:absolute)
        milestone_row = ""
        if _MILESTONES:
            cells = ""
            prev = 0
            for m in _MILESTONES:
                spacer_w = m - prev
                done = pct >= m
                marker_color = c["milestone_done"] if done else c["milestone"]
                marker_label = "✓" if done else "┊"
                cells += (
                    f'<div style="width:{spacer_w}%;text-align:right;font-size:9px;'
                    f"color:{marker_color};font-weight:{'600' if done else '400'}"
                    f'">{marker_label}</div>'
                )
                prev = m
            milestone_row = (
                f'<div style="display:flex;margin-top:-4px;margin-bottom:2px">{cells}</div>'
            )

        # Static candy stripes overlay (Colab-safe, no animation)
        stripe_bg = (
            "repeating-linear-gradient("
            "45deg,"
            "rgba(255,255,255,0.10) 0px,"
            "rgba(255,255,255,0.10) 10px,"
            "transparent 10px,"
            "transparent 20px)"
        )

        return (
            f'<div style="{font};font-size:13px;color:{c["text"]};max-width:680px">'
            # Header + milestone message
            f'<div style="font-weight:600;font-size:14px;margin-bottom:8px;'
            f'color:{c["header"]}">'
            f"{header} {milestone_span}"
            f'<span style="float:right;font-weight:600;color:{pct_color}">{pct}%</span>'
            f"</div>"
            # Explainer (first render only)
            f"{explainer_html}"
            # Spider row (table layout: spider wanders within filled portion)
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:0;'
            f'table-layout:fixed"><tr>'
            f'<td style="width:{spider_pos:.1f}%;text-align:right;padding:0;'
            f'vertical-align:bottom;line-height:1">'
            f'<span style="font-size:{_SPIDER_FONT_SIZE_PX}px;{spider_flip}">\U0001f577\ufe0f</span></td>'
            f'<td style="padding:0"></td>'
            f"</tr></table>"
            # Web thread (dashed line from left to progress edge)
            f'<div style="width:{max(pct, _SPIDER_MIN_WIDTH_PCT)}%;border-top:1.5px dashed {c["thread"]};'
            f'margin-bottom:2px"></div>'
            # Spider web decoration (overlaps bar via negative margin)
            f'<div style="opacity:0.18;margin-bottom:-22px;pointer-events:none">'
            f"{web_svg}</div>"
            # Progress bar (with static glow + static candy stripes)
            f'<div style="background:{c["bar_bg"]};border-radius:10px;height:22px;'
            f'margin-bottom:6px;overflow:hidden">'
            f'<div style="background:{bar_grad};'
            f"height:100%;border-radius:10px;width:{pct}%;"
            f'box-shadow:inset 0 1px 3px {c["bar_glow"]}">'
            f'<div style="width:100%;height:100%;border-radius:10px;'
            f'background:{stripe_bg};opacity:0.8"></div>'
            f"</div>"
            f"</div>"
            # Milestone markers
            f"{milestone_row}"
            # Activity + log
            f"{activity_html}"
            f"{log_html}"
            # Footer
            f'<div style="margin-top:6px;font-size:12px;color:{c["footer"]}">'
            f"{footer}</div>"
            f"</div>"
        )
