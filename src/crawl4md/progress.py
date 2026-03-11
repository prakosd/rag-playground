"""Real-time progress reporting for Jupyter and terminal."""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

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
    "empty extraction": "📭",
    "crawl": "🌐",
    "extract": "📝",
    "flush": "💾",
    "delay": "⏳",
    "discover": "🔗",
}
# Fallback icon when no keyword matches.
_ACTIVITY_ICON_DEFAULT = "⚙️"

# ---------------------------------------------------------------------------
# Activity log disk files
# ---------------------------------------------------------------------------
# Filename for the human-readable activity log written to the output directory.
_ACTIVITY_LOG_TXT_FILE = "activity_log.txt"
# Filename for the machine-readable CSV activity log.
_ACTIVITY_LOG_CSV_FILE = "activity_log.csv"
# CSV header row (written once when the file is created).
_ACTIVITY_LOG_CSV_HEADER = "timestamp,round,activity,duration_seconds"

# Separator string used to join header parts (e.g. "Round 1 · Page 5 / 10")
_HEADER_SEPARATOR = " · "
# Minimum spider column width percentage to keep it visible at 0% progress
_SPIDER_MIN_WIDTH_PCT = 2

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
        self._activity_log: list[tuple[datetime, str, float]] = []

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
            if len(self._activity_log) > self._max_log_entries:
                self._activity_log = self._activity_log[-self._max_log_entries :]
        self._current_activity = ""
        self._activity_start = 0.0

    def _append_to_disk(self, ts: datetime, label: str, duration: float) -> None:
        """Append one activity entry to the TXT and CSV log files on disk."""
        if self._log_dir is None:
            return

        icon = _ProgressWidget._activity_icon(label)
        dur_str = _ProgressWidget._fmt_duration(duration)
        round_part = f" [{self._round_label}]" if self._round_label else ""
        txt_line = f"[{ts:%H:%M:%S}]{round_part} {icon} {label} ({dur_str})\n"

        txt_path = self._log_dir / _ACTIVITY_LOG_TXT_FILE
        with txt_path.open("a", encoding="utf-8") as fh:
            fh.write(txt_line)

        csv_path = self._log_dir / _ACTIVITY_LOG_CSV_FILE
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if write_header:
                writer.writerow(_ACTIVITY_LOG_CSV_HEADER.split(","))
            writer.writerow(
                [
                    ts.isoformat(timespec="seconds"),
                    self._round_label,
                    label,
                    f"{duration:.3f}",
                ]
            )

    def update_activity_label(self, label: str) -> None:
        """Update the label of the current activity without closing it."""
        self._current_activity = label
        if self._use_notebook:
            self._refresh_display()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _refresh_display(self) -> None:
        """Refresh the Jupyter widget (notebook mode only)."""
        if not self._use_notebook:
            return
        from IPython.display import HTML, clear_output, display  # type: ignore[import-untyped]

        clear_output(wait=True)
        widget = self._build_widget()
        if self._use_colab:
            display(HTML(widget._repr_html_()))
        else:
            display(widget)

    def _build_widget(self) -> _ProgressWidget:
        """Construct the widget with current state."""
        eta = f"~{self._eta_remaining()} left, done ~{self._eta_finish_time()}"
        total_crawled = (
            self._prior_success + self._prior_fail + self._round_success + self._round_fail
        )
        total_success = self._prior_success + self._round_success
        total_fail = self._prior_fail + self._round_fail
        stats = f"{total_crawled} crawled, {total_success} succeeded, {total_fail} failed"

        activity_start_time = ""
        activity_eta = ""
        activity_est_duration = ""
        if self._current_activity and self._activity_start > 0:
            activity_start_time = datetime.fromtimestamp(self._activity_start).strftime("%H:%M:%S")
            # Estimate finish from avg duration of same-category activities
            cat = _ProgressWidget._activity_category(self._current_activity)
            durations = [
                d
                for _, lbl, d in self._activity_log
                if _ProgressWidget._activity_category(lbl) == cat
            ]
            if durations:
                avg = sum(durations) / len(durations)
                est_finish = datetime.fromtimestamp(self._activity_start) + timedelta(seconds=avg)
                activity_eta = est_finish.strftime("%H:%M:%S")
                activity_est_duration = _ProgressWidget._fmt_duration(avg)

        return _ProgressWidget(
            current=self.count,
            total=self.total,
            eta=eta,
            stats=stats,
            round_label=self._round_label,
            activity=self._current_activity,
            activity_start_time=activity_start_time,
            activity_eta=activity_eta,
            activity_est_duration=activity_est_duration,
            activity_log=list(self._activity_log),
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
            eta = f"~{self._eta_remaining()} left, done ~{self._eta_finish_time()}"
            msg = f"[{self.count}/{self.total}] ({self._elapsed()}) {self.action}: {url}"
            total_crawled = (
                self._prior_success + self._prior_fail + self._round_success + self._round_fail
            )
            total_success = self._prior_success + self._round_success
            total_fail = self._prior_fail + self._round_fail
            stats = (
                f"Total: {total_crawled} crawled, {total_success} succeeded, {total_fail} failed"
            )
            print(f"{msg}  |  {eta}")
            print(stats)

    def finish(self, output_dir: str | None = None) -> None:
        """Report that processing is complete."""
        self._close_activity()
        msg = f"\nDone! {self.action} {self.count} page(s) in {self._elapsed()}."
        if output_dir:
            msg += f"\nOutput folder: {output_dir}"
        if self._use_notebook:
            from IPython.display import clear_output  # type: ignore[import-untyped]

            clear_output(wait=True)
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
        round_label: str = "",
        activity: str = "",
        activity_start_time: str = "",
        activity_eta: str = "",
        activity_est_duration: str = "",
        activity_log: list[tuple[datetime, str, float]] | None = None,
        *,
        colab: bool = False,
        dark: bool = False,
    ) -> None:
        self.current = current
        self.total = total
        self.eta = eta
        self.stats = stats
        self.round_label = round_label
        self.activity = activity
        self.activity_start_time = activity_start_time
        self.activity_eta = activity_eta
        self.activity_est_duration = activity_est_duration
        self.activity_log = activity_log or []
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
        if "crawl" in low:
            return "crawl"
        if "extract" in low:
            return "extract"
        if "flush" in low:
            return "flush"
        if "delay" in low:
            return "delay"
        if "discover" in low:
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

    def _repr_html_(self) -> str:
        if self.colab:
            return self._repr_html_colab()
        pct = int(self.current / self.total * 100) if self.total else 0

        # --- Header ---
        header_parts = []
        if self.round_label:
            header_parts.append(self.round_label)
        header_parts.append(f"Page {self.current} / {self.total}")
        header = _HEADER_SEPARATOR.join(header_parts)

        # --- Activity row ---
        activity_html = ""
        if self.activity:
            icon = self._activity_icon(self.activity)
            # Truncate long URLs in the label for display
            display_label = self.activity
            if len(display_label) > _ACTIVITY_LABEL_MAX_LEN:
                display_label = display_label[:_ACTIVITY_LABEL_TRUNC] + "…"
            time_info = f"since {self.activity_start_time}" if self.activity_start_time else ""
            if self.activity_eta:
                time_info += f" \u2192 ~{self.activity_eta}"
            if self.activity_est_duration:
                time_info += f" (~{self.activity_est_duration})"
            time_span = f'<span class="c4md-dur"> \u2014 {time_info}</span>' if time_info else ""
            activity_html = (
                f'<div class="c4md-activity">'
                f'<span class="c4md-pulse"></span>'
                f" {icon} {display_label}"
                f"{time_span}"
                f"</div>"
            )

        # --- Activity log ---
        log_html = ""
        if self.activity_log:
            rows = ""
            for ts, label, dur in reversed(self.activity_log):
                icon = self._activity_icon(label)
                display_label = (
                    label if len(label) <= _LOG_LABEL_MAX_LEN else label[:_LOG_LABEL_TRUNC] + "…"
                )
                ts_str = ts.strftime("%H:%M:%S")
                is_fail = label.startswith("\u274c")
                label_cls = "c4md-log-label c4md-log-fail" if is_fail else "c4md-log-label"
                rows += (
                    f"<tr>"
                    f'<td class="c4md-log-time">{ts_str}</td>'
                    f'<td class="c4md-log-icon">{icon}</td>'
                    f'<td class="{label_cls}">{display_label}</td>'
                    f'<td class="c4md-log-dur">{self._fmt_duration(dur)}</td>'
                    f"</tr>"
                )
            log_html = (
                f'<div class="c4md-log">'
                f'<div class="c4md-log-heading">Activity Log</div>'
                f'<table class="c4md-log-table">{rows}</table>'
                f"</div>"
            )

        # --- Stats + ETA ---
        footer = f"{self.stats}"
        if self.eta:
            footer += f" &nbsp;·&nbsp; {self.eta}"

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
            # Progress bar container
            f".c4md-bar-wrap {{"
            f"  position: relative; background: {lt['bar_bg']}; border-radius: 10px;"
            f"  height: 22px; overflow: visible; margin-bottom: 6px;"
            f"}}"
            f".c4md-bar {{"
            f"  position: relative;"
            f"  background: {lt['bar_gradient']};"
            f"  height: 100%; border-radius: 10px;"
            f"  transition: width 0.4s ease;"
            f"  overflow: hidden;"
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
            # Spider sitting at the leading edge of the bar
            f".c4md-spider {{"
            f"  position: absolute; top: -10px;"
            f"  font-size: 20px; line-height: 1;"
            f"  transition: left 0.4s ease;"
            f"  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));"
            f"  animation: c4md-crawl 3s ease-in-out infinite;"
            f"}}"
            # Web thread (dashed line from left edge to spider)
            f".c4md-thread {{"
            f"  position: absolute; top: 0px; left: 0; height: 2px;"
            f"  border-top: 1.5px dashed {lt['thread']};"
            f"  transition: width 0.4s ease;"
            f"}}"
            # Spider crawl animation: combines horizontal patrol + vertical bob
            f"@keyframes c4md-crawl {{"
            f"  0% {{ transform: translateX(0) translateY(0); }}"
            f"  25% {{ transform: translateX(-18px) translateY(-3px); }}"
            f"  50% {{ transform: translateX(-35px) translateY(0); }}"
            f"  75% {{ transform: translateX(-18px) translateY(-3px); }}"
            f"  100% {{ transform: translateX(0) translateY(0); }}"
            f"}}"
            f"@keyframes c4md-glow {{"
            f"  0%, 100% {{ opacity: 0; }}"
            f"  50% {{ opacity: 1; }}"
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
            # Footer
            f".c4md-footer {{"
            f"  margin-top: 6px; font-size: 12px; color: {lt['footer']};"
            f"}}"
            f".c4md-pct {{"
            f"  float: right; font-weight: 600; color: {lt['pct']};"
            f"}}"
            # Dark-mode overrides
            f"@media (prefers-color-scheme: dark) {{"
            f"  .c4md-widget {{ color: {dk['text']}; }}"
            f"  .c4md-header {{ color: {dk['header']}; }}"
            f"  .c4md-bar-wrap {{ background: {dk['bar_bg']}; }}"
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
            f"  .c4md-pct {{ color: {dk['pct']}; }}"
            f"}}"
            f"</style>"
            # Header
            f'<div class="c4md-header">{header}'
            f'<span class="c4md-pct">{pct}%</span></div>'
            # Bar + spider + thread + web decoration
            f'<div class="c4md-bar-wrap">'
            f'<div class="c4md-web">'
            f'<svg width="28" height="28" viewBox="0 0 28 28" fill="none"'
            f' xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M0 0 Q0 14 14 14" stroke="{lt["web"]}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 21 21 21" stroke="{lt["web"]}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 28 28 28" stroke="{lt["web"]}" stroke-width="0.8" fill="none"/>'
            f'<line x1="0" y1="0" x2="14" y2="0" stroke="{lt["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="0" y2="14" stroke="{lt["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="10" y2="10" stroke="{lt["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="4" y2="13" stroke="{lt["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="13" y2="4" stroke="{lt["web"]}" stroke-width="0.8"/>'
            f"</svg></div>"
            f'<div class="c4md-thread" style="width:{max(pct, 0)}%;"></div>'
            f'<div class="c4md-bar" style="width:{pct}%;"></div>'
            f'<div class="c4md-spider" style="left:calc({pct}% - 10px);">🕷️</div>'
            f"</div>"
            # Activity + log
            f"{activity_html}"
            f"{log_html}"
            # Footer
            f'<div class="c4md-footer">{footer}</div>'
            f"</div>"
        )

    def _repr_html_colab(self) -> str:
        """Colab-safe HTML rendering using only inline styles (no <style> block)."""
        pct = int(self.current / self.total * 100) if self.total else 0
        c = _DARK_COLORS if self.dark else _LIGHT_COLORS

        # Shared inline style fragments
        font = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif"

        # --- Header ---
        header_parts = []
        if self.round_label:
            header_parts.append(self.round_label)
        header_parts.append(f"Page {self.current} / {self.total}")
        header = _HEADER_SEPARATOR.join(header_parts)

        # --- Activity row ---
        activity_html = ""
        if self.activity:
            icon = self._activity_icon(self.activity)
            display_label = self.activity
            if len(display_label) > _ACTIVITY_LABEL_MAX_LEN:
                display_label = display_label[:_ACTIVITY_LABEL_TRUNC] + "\u2026"
            time_info = f"since {self.activity_start_time}" if self.activity_start_time else ""
            if self.activity_eta:
                time_info += f" \u2192 ~{self.activity_eta}"
            if self.activity_est_duration:
                time_info += f" (~{self.activity_est_duration})"
            time_span = (
                f'<span style="color:{c["duration"]}"> \u2014 {time_info}</span>'
                if time_info
                else ""
            )
            activity_html = (
                f'<div style="margin:6px 0;color:{c["activity"]};font-size:12.5px;{font}">'
                f'<span style="display:inline-block;width:8px;height:8px;'
                f"background:{c['pulse']};border-radius:50%;vertical-align:middle;"
                f'margin-right:5px"></span>'
                f" {icon} {display_label}"
                f"{time_span}"
                f"</div>"
            )

        # --- Activity log ---
        log_html = ""
        if self.activity_log:
            rows = ""
            for ts, label, dur in reversed(self.activity_log):
                icon = self._activity_icon(label)
                display_label = (
                    label
                    if len(label) <= _LOG_LABEL_MAX_LEN
                    else label[:_LOG_LABEL_TRUNC] + "\u2026"
                )
                ts_str = ts.strftime("%H:%M:%S")
                is_fail = label.startswith("\u274c")
                label_color = f"color:{c['log_fail']}" if is_fail else ""
                rows += (
                    f"<tr>"
                    f'<td style="white-space:nowrap;font-family:monospace;'
                    f"color:{c['log_time']};"
                    f'font-size:11px;width:58px;padding:1px 4px">{ts_str}</td>'
                    f'<td style="width:18px;text-align:center;padding:1px 4px">{icon}</td>'
                    f'<td style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                    f'max-width:460px;padding:1px 4px;{label_color}">{display_label}</td>'
                    f'<td style="text-align:right;color:{c["log_dur"]};white-space:nowrap;'
                    f'padding:1px 4px">{self._fmt_duration(dur)}</td>'
                    f"</tr>"
                )
            log_html = (
                f'<div style="margin-top:4px;max-height:200px;overflow-y:auto">'
                f'<div style="font-size:11.5px;font-weight:600;color:{c["log_heading"]};'
                f'margin-bottom:2px">Activity Log</div>'
                f'<table style="width:100%;font-size:11.5px;border-collapse:collapse;'
                f'color:{c["log_text"]}">{rows}</table>'
                f"</div>"
            )

        # --- Stats + ETA ---
        footer = f"{self.stats}"
        if self.eta:
            footer += f" &nbsp;\u00b7&nbsp; {self.eta}"

        # Spider + thread: use a table so the spider sits at the leading edge
        # of the filled portion, mimicking the VS Code animated spider.
        spider_pct = max(pct, _SPIDER_MIN_WIDTH_PCT)  # ensure spider column is visible even at 0%
        # Spider web SVG (inline, overlaps bar via negative margin)
        web_svg = (
            f'<svg width="28" height="28" viewBox="0 0 28 28" fill="none"'
            f' style="display:block"'
            f' xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M0 0 Q0 14 14 14" stroke="{c["web"]}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 21 21 21" stroke="{c["web"]}" stroke-width="0.8" fill="none"/>'
            f'<path d="M0 0 Q0 28 28 28" stroke="{c["web"]}" stroke-width="0.8" fill="none"/>'
            f'<line x1="0" y1="0" x2="14" y2="0" stroke="{c["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="0" y2="14" stroke="{c["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="10" y2="10" stroke="{c["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="4" y2="13" stroke="{c["web"]}" stroke-width="0.8"/>'
            f'<line x1="0" y1="0" x2="13" y2="4" stroke="{c["web"]}" stroke-width="0.8"/>'
            f"</svg>"
        )
        return (
            f'<div style="{font};font-size:13px;color:{c["text"]};max-width:680px">'
            # Header
            f'<div style="font-weight:600;font-size:14px;margin-bottom:8px;'
            f'color:{c["header"]}">'
            f"{header}"
            f'<span style="float:right;font-weight:600;color:{c["pct"]}">{pct}%</span>'
            f"</div>"
            # Spider row (table layout: spider tracks progress)
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:0;'
            f'table-layout:fixed"><tr>'
            f'<td style="width:{spider_pct}%;text-align:right;padding:0;'
            f'vertical-align:bottom;line-height:1">'
            f'<span style="font-size:18px">\U0001f577\ufe0f</span></td>'
            f'<td style="padding:0"></td>'
            f"</tr></table>"
            # Web thread (dashed line from left to spider)
            f'<div style="width:{spider_pct}%;border-top:1.5px dashed {c["thread"]};'
            f'margin-bottom:2px"></div>'
            # Spider web decoration (overlaps bar via negative margin)
            f'<div style="opacity:0.18;margin-bottom:-22px;pointer-events:none">'
            f"{web_svg}</div>"
            # Progress bar (with static glow via box-shadow)
            f'<div style="background:{c["bar_bg"]};border-radius:10px;height:22px;'
            f'margin-bottom:6px;overflow:hidden">'
            f'<div style="background:{c["bar_gradient"]};'
            f"height:100%;border-radius:10px;width:{pct}%;"
            f'box-shadow:inset 0 1px 3px {c["bar_glow"]}"></div>'
            f"</div>"
            # Activity + log
            f"{activity_html}"
            f"{log_html}"
            # Footer
            f'<div style="margin-top:6px;font-size:12px;color:{c["footer"]}">'
            f"{footer}</div>"
            f"</div>"
        )
