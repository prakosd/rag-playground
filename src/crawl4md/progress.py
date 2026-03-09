"""Real-time progress reporting for Jupyter and terminal."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

# Maximum number of recent activities shown in the activity log.
_MAX_LOG_ENTRIES = 10


def _in_notebook() -> bool:
    """Detect whether we are running inside a Jupyter/IPython notebook."""
    try:
        from IPython import get_ipython  # type: ignore[import-untyped]

        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ == "ZMQInteractiveShell"
    except ImportError:
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
    ) -> None:
        self.total = total
        self.count = 0
        self.action = action
        self._start_time = time.time()
        self._use_notebook = _in_notebook()
        self._prior_success = prior_success
        self._prior_fail = prior_fail
        self._round_success = 0
        self._round_fail = 0
        self._round_label = round_label
        self._max_log_entries = max_log_entries

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
            return "estimating..."
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
            return "estimating..."
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
            self._activity_log.append((datetime.now(), self._current_activity, duration))
            if len(self._activity_log) > self._max_log_entries:
                self._activity_log = self._activity_log[-self._max_log_entries :]
        self._current_activity = ""
        self._activity_start = 0.0

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
        from IPython.display import clear_output, display  # type: ignore[import-untyped]

        clear_output(wait=True)
        display(self._build_widget())

    def _build_widget(self) -> _ProgressWidget:
        """Construct the widget with current state."""
        eta = f"~{self._eta_remaining()} left, done ~{self._eta_finish_time()}"
        total_crawled = (
            self._prior_success + self._prior_fail + self._round_success + self._round_fail
        )
        total_success = self._prior_success + self._round_success
        total_fail = self._prior_fail + self._round_fail
        stats = f"{total_crawled} crawled, {total_success} succeeded, {total_fail} failed"

        activity_elapsed = 0.0
        if self._current_activity and self._activity_start > 0:
            activity_elapsed = time.time() - self._activity_start

        return _ProgressWidget(
            current=self.count,
            total=self.total,
            eta=eta,
            stats=stats,
            round_label=self._round_label,
            activity=self._current_activity,
            activity_elapsed=activity_elapsed,
            activity_log=list(self._activity_log),
        )

    def update(self, url: str, *, success: bool = True) -> None:
        """Report that a page has been processed."""
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
        activity_elapsed: float = 0.0,
        activity_log: list[tuple[datetime, str, float]] | None = None,
    ) -> None:
        self.current = current
        self.total = total
        self.eta = eta
        self.stats = stats
        self.round_label = round_label
        self.activity = activity
        self.activity_elapsed = activity_elapsed
        self.activity_log = activity_log or []

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        """Format a duration as a compact human-readable string."""
        if seconds < 0.1:
            return "<0.1s"
        if seconds < 60:
            return f"{seconds:.1f}s"
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs:02d}s"

    @staticmethod
    def _activity_icon(label: str) -> str:
        """Pick a small icon for the activity label."""
        low = label.lower()
        if "crawl" in low:
            return "🌐"
        if "extract" in low:
            return "📝"
        if "flush" in low:
            return "💾"
        if "delay" in low:
            return "⏳"
        if "discover" in low:
            return "🔗"
        return "⚙️"

    def _repr_html_(self) -> str:
        pct = int(self.current / self.total * 100) if self.total else 0

        # --- Header ---
        header_parts = []
        if self.round_label:
            header_parts.append(self.round_label)
        header_parts.append(f"Page {self.current} / {self.total}")
        header = " · ".join(header_parts)

        # --- Activity row ---
        activity_html = ""
        if self.activity:
            icon = self._activity_icon(self.activity)
            dur = self._fmt_duration(self.activity_elapsed)
            # Truncate long URLs in the label for display
            display_label = self.activity
            if len(display_label) > 80:
                display_label = display_label[:77] + "…"
            activity_html = (
                f'<div class="c4md-activity">'
                f'<span class="c4md-pulse"></span>'
                f" {icon} {display_label}"
                f'<span class="c4md-dur"> — {dur}</span>'
                f"</div>"
            )

        # --- Activity log ---
        log_html = ""
        if self.activity_log:
            rows = ""
            for ts, label, dur in reversed(self.activity_log):
                icon = self._activity_icon(label)
                display_label = label if len(label) <= 70 else label[:67] + "…"
                ts_str = ts.strftime("%H:%M:%S")
                rows += (
                    f"<tr>"
                    f'<td class="c4md-log-time">{ts_str}</td>'
                    f'<td class="c4md-log-icon">{icon}</td>'
                    f'<td class="c4md-log-label">{display_label}</td>'
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

        return (
            f'<div class="c4md-widget">'
            f"<style>"
            f".c4md-widget {{"
            f"  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            f"  font-size: 13px; color: #333; max-width: 680px;"
            f"}}"
            f".c4md-header {{"
            f"  font-weight: 600; font-size: 14px; margin-bottom: 8px;"
            f"}}"
            # Progress bar container
            f".c4md-bar-wrap {{"
            f"  position: relative; background: #e8eaed; border-radius: 10px;"
            f"  height: 22px; overflow: visible; margin-bottom: 6px;"
            f"}}"
            f".c4md-bar {{"
            f"  background: linear-gradient(90deg, #43a047, #66bb6a);"
            f"  height: 100%; border-radius: 10px;"
            f"  transition: width 0.4s ease;"
            f"}}"
            # Spider sitting at the leading edge of the bar
            f".c4md-spider {{"
            f"  position: absolute; top: -10px;"
            f"  font-size: 20px; line-height: 1;"
            f"  transition: left 0.4s ease;"
            f"  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));"
            f"  animation: c4md-bob 1.2s ease-in-out infinite;"
            f"}}"
            # Web thread (dashed line from left edge to spider)
            f".c4md-thread {{"
            f"  position: absolute; top: 0px; left: 0; height: 2px;"
            f"  border-top: 1.5px dashed #999;"
            f"  transition: width 0.4s ease;"
            f"}}"
            f"@keyframes c4md-bob {{"
            f"  0%, 100% {{ transform: translateY(0); }}"
            f"  50% {{ transform: translateY(-3px); }}"
            f"}}"
            # Pulsing dot for current activity
            f".c4md-activity {{"
            f"  margin: 6px 0; color: #1a73e8; font-size: 12.5px;"
            f"  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            f"}}"
            f".c4md-pulse {{"
            f"  display: inline-block; width: 7px; height: 7px;"
            f"  background: #1a73e8; border-radius: 50%;"
            f"  animation: c4md-blink 1s ease-in-out infinite;"
            f"  vertical-align: middle; margin-right: 4px;"
            f"}}"
            f"@keyframes c4md-blink {{"
            f"  0%, 100% {{ opacity: 1; }}"
            f"  50% {{ opacity: 0.25; }}"
            f"}}"
            f".c4md-dur {{ color: #888; }}"
            # Activity log
            f".c4md-log {{"
            f"  margin-top: 4px; max-height: 200px; overflow-y: auto;"
            f"}}"
            f".c4md-log-heading {{"
            f"  font-size: 11.5px; font-weight: 600; color: #888;"
            f"  margin-bottom: 2px;"
            f"}}"
            f".c4md-log-table {{"
            f"  width: 100%; font-size: 11.5px; border-collapse: collapse; color: #555;"
            f"}}"
            f".c4md-log-table td {{ padding: 1px 4px; }}"
            f".c4md-log-time {{"
            f"  white-space: nowrap; font-family: monospace; color: #999;"
            f"  font-size: 11px; width: 58px;"
            f"}}"
            f".c4md-log-icon {{ width: 18px; text-align: center; }}"
            f".c4md-log-label {{"
            f"  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            f"  max-width: 460px;"
            f"}}"
            f".c4md-log-dur {{ text-align: right; color: #888; white-space: nowrap; }}"
            # Footer
            f".c4md-footer {{"
            f"  margin-top: 6px; font-size: 12px; color: #666;"
            f"}}"
            f".c4md-pct {{"
            f"  float: right; font-weight: 600; color: #43a047;"
            f"}}"
            f"</style>"
            # Header
            f'<div class="c4md-header">{header}'
            f'<span class="c4md-pct">{pct}%</span></div>'
            # Bar + spider + thread
            f'<div class="c4md-bar-wrap">'
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
