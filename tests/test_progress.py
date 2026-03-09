"""Tests for crawl4md.progress — ProgressReporter and _ProgressWidget."""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import patch

from crawl4md.progress import _MAX_LOG_ENTRIES, ProgressReporter, _ProgressWidget


class TestProgressWidget:
    """Tests for the HTML widget rendering."""

    def test_repr_html_contains_spider(self):
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert "🕷️" in html

    def test_repr_html_contains_progress_percentage(self):
        widget = _ProgressWidget(current=5, total=10)
        html = widget._repr_html_()
        assert "50%" in html

    def test_repr_html_zero_total(self):
        widget = _ProgressWidget(current=0, total=0)
        html = widget._repr_html_()
        assert "0%" in html

    def test_repr_html_includes_round_label(self):
        widget = _ProgressWidget(current=1, total=5, round_label="Round 2/3")
        html = widget._repr_html_()
        assert "Round 2/3" in html

    def test_repr_html_includes_activity(self):
        widget = _ProgressWidget(
            current=2,
            total=10,
            activity="Crawling https://example.com/page",
            activity_start_time="14:23:05",
        )
        html = widget._repr_html_()
        assert "Crawling https://example.com/page" in html
        assert "since 14:23:05" in html
        # Should have the crawling icon
        assert "🌐" in html

    def test_repr_html_includes_activity_log(self):
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "Crawling https://example.com/a", 2.1),
                (now, "Extracting content", 0.4),
            ],
        )
        html = widget._repr_html_()
        assert "Crawling https://example.com/a" in html
        assert "Extracting content" in html
        assert "2.1s" in html
        assert "0.4s" in html

    def test_repr_html_no_activity_still_valid(self):
        """Widget without activity data still produces valid HTML."""
        widget = _ProgressWidget(current=1, total=5, eta="~02:00 left", stats="1 crawled")
        html = widget._repr_html_()
        assert "Page 1 / 5" in html
        assert "🕷️" in html
        assert "~02:00 left" in html

    def test_repr_html_includes_stats_and_eta(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            eta="~05:00 left, done ~12:30:00",
            stats="3 crawled, 2 succeeded, 1 failed",
        )
        html = widget._repr_html_()
        assert "3 crawled" in html
        assert "~05:00 left" in html

    def test_repr_html_long_activity_truncated(self):
        long_url = "https://example.com/" + "a" * 100
        widget = _ProgressWidget(
            current=1,
            total=5,
            activity=f"Crawling {long_url}",
            activity_start_time="14:23:05",
        )
        html = widget._repr_html_()
        assert "…" in html

    def test_activity_icons(self):
        assert _ProgressWidget._activity_icon("Crawling x") == "🌐"
        assert _ProgressWidget._activity_icon("Extracting content") == "📝"
        assert _ProgressWidget._activity_icon("Flushing to disk (5 pages processed)") == "💾"
        assert _ProgressWidget._activity_icon("Delay 5.0s") == "⏳"
        assert _ProgressWidget._activity_icon("Discovered 10 links from x") == "🔗"
        assert _ProgressWidget._activity_icon("Something else") == "⚙️"
        assert _ProgressWidget._activity_icon("❌ FAILED \u2014 Crawling x") == "❌"

    def test_fmt_duration_ranges(self):
        assert _ProgressWidget._fmt_duration(0.01) == "<0.1s"
        assert _ProgressWidget._fmt_duration(0.5) == "0.5s"
        assert _ProgressWidget._fmt_duration(45.3) == "45.3s"
        assert _ProgressWidget._fmt_duration(125) == "2m 05s"


class TestProgressReporter:
    """Tests for ProgressReporter activity tracking."""

    def test_set_activity_records_to_log(self):
        """set_activity closes previous activity and records its duration."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Crawling page A")
            time.sleep(0.05)
            reporter.set_activity("Extracting content")

            assert len(reporter._activity_log) == 1
            ts, label, dur = reporter._activity_log[0]
            assert isinstance(ts, datetime)
            assert label == "Crawling page A"
            assert dur >= 0.04  # Should have captured the sleep

            assert reporter._current_activity == "Extracting content"
            assert reporter._activity_start > 0

    def test_activity_log_capped(self):
        """Activity log does not exceed _MAX_LOG_ENTRIES."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            for i in range(_MAX_LOG_ENTRIES + 5):
                reporter.set_activity(f"Activity {i}")

            # Close the last one
            reporter._close_activity()
            assert len(reporter._activity_log) == _MAX_LOG_ENTRIES

    def test_update_closes_activity(self):
        """update() should close the current activity."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Crawling page X")
            reporter.update("https://example.com/x", success=True)

            assert reporter._current_activity == ""
            assert len(reporter._activity_log) == 1
            assert reporter._activity_log[0][1] == "Crawling page X"

    def test_update_increments_counts(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(3)
            reporter._use_notebook = False

            reporter.update("https://example.com/a", success=True)
            reporter.update("https://example.com/b", success=False)

            assert reporter.count == 2
            assert reporter._round_success == 1
            assert reporter._round_fail == 1

    def test_finish_closes_activity(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(2)
            reporter._use_notebook = False

            reporter.set_activity("Crawling something")
            reporter.finish()

            assert reporter._current_activity == ""
            assert len(reporter._activity_log) == 1

    def test_round_label_stored(self):
        reporter = ProgressReporter(5, round_label="Round 1/3")
        assert reporter._round_label == "Round 1/3"

    def test_no_activity_calls_still_works(self):
        """Reporter without any set_activity calls should still function."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(2)
            reporter._use_notebook = False

            reporter.update("https://example.com/a", success=True)
            reporter.update("https://example.com/b", success=True)
            reporter.finish()

            assert reporter.count == 2
            assert reporter._activity_log == []

    def test_custom_max_log_entries(self):
        """Custom max_log_entries is respected."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(20, max_log_entries=3)
            reporter._use_notebook = False

            for i in range(10):
                reporter.set_activity(f"Activity {i}")
            reporter._close_activity()

            assert len(reporter._activity_log) == 3

    def test_activity_log_heading_in_html(self):
        """Widget HTML contains 'Activity Log' heading."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=2,
            total=10,
            activity_log=[(now, "Crawling https://example.com/a", 1.0)],
        )
        html = widget._repr_html_()
        assert "Activity Log" in html

    def test_activity_log_datetime_in_html(self):
        """Widget HTML contains HH:MM:SS timestamp for log entries."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=2,
            total=10,
            activity_log=[(now, "Crawling https://example.com/a", 1.0)],
        )
        html = widget._repr_html_()
        assert now.strftime("%H:%M:%S") in html

    def test_update_activity_label_keeps_timer(self):
        """update_activity_label changes label without closing activity."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Discovering links from https://example.com")
            start = reporter._activity_start
            time.sleep(0.05)

            reporter.update_activity_label("Discovered 5 links from https://example.com")

            # Label changed but timer was NOT reset
            assert reporter._current_activity == "Discovered 5 links from https://example.com"
            assert reporter._activity_start == start
            # No new log entry created
            assert len(reporter._activity_log) == 0

    def test_default_max_log_entries_is_ten(self):
        """Default _MAX_LOG_ENTRIES is 10."""
        assert _MAX_LOG_ENTRIES == 10

    def test_build_widget_returns_widget(self):
        """_build_widget should return a _ProgressWidget with correct state."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10, round_label="Round 2/4")
            reporter._use_notebook = False
            reporter.count = 3
            reporter._round_success = 2
            reporter._round_fail = 1

            widget = reporter._build_widget()
            assert isinstance(widget, _ProgressWidget)
            assert widget.current == 3
            assert widget.total == 10
            assert widget.round_label == "Round 2/4"
            assert "3 crawled" in widget.stats

    def test_set_activity_without_previous(self):
        """First set_activity should not crash (no previous to close)."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("First activity")
            assert reporter._current_activity == "First activity"
            assert reporter._activity_log == []

    def test_close_activity_noop_when_empty(self):
        """_close_activity on empty state is a no-op."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter._close_activity()
            assert reporter._activity_log == []
            assert reporter._current_activity == ""

    def test_repr_html_activity_with_eta(self):
        """Widget shows both start time and ETA when available."""
        widget = _ProgressWidget(
            current=5,
            total=10,
            activity="Crawling https://example.com/page",
            activity_start_time="14:23:05",
            activity_eta="14:23:18",
        )
        html = widget._repr_html_()
        assert "since 14:23:05" in html
        assert "~14:23:18" in html
        assert "\u2192" in html

    def test_repr_html_activity_with_est_duration(self):
        """Widget shows estimated duration when provided."""
        widget = _ProgressWidget(
            current=5,
            total=10,
            activity="Crawling https://example.com/page",
            activity_start_time="14:23:05",
            activity_eta="14:23:18",
            activity_est_duration="13.0s",
        )
        html = widget._repr_html_()
        assert "(~13.0s)" in html

    def test_repr_html_activity_no_est_duration(self):
        """Widget does not show estimated duration when not provided."""
        widget = _ProgressWidget(
            current=1,
            total=10,
            activity="Crawling https://example.com/page",
            activity_start_time="14:23:05",
        )
        html = widget._repr_html_()
        assert "(~" not in html

    def test_repr_html_activity_no_eta(self):
        """Widget shows only start time when no ETA is available."""
        widget = _ProgressWidget(
            current=1,
            total=10,
            activity="Crawling https://example.com/page",
            activity_start_time="14:23:05",
        )
        html = widget._repr_html_()
        assert "since 14:23:05" in html
        assert "\u2192" not in html

    def test_activity_category(self):
        """_activity_category returns correct categories."""
        assert _ProgressWidget._activity_category("Crawling https://x.com") == "crawl"
        assert _ProgressWidget._activity_category("Extracting content") == "extract"
        assert _ProgressWidget._activity_category("Flushing to disk") == "flush"
        assert _ProgressWidget._activity_category("Delay 5.0s") == "delay"
        assert _ProgressWidget._activity_category("Discovering links from x") == "discover"
        assert _ProgressWidget._activity_category("Something else") == "other"
        # Failed activities keep their category based on the underlying label
        assert _ProgressWidget._activity_category("\u274c FAILED \u2014 Crawling x") == "crawl"

    def test_build_widget_computes_activity_eta(self):
        """_build_widget computes ETA from same-category log entries."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            # Simulate a few completed crawling activities (10s each)
            now = datetime.now()
            reporter._activity_log = [
                (now, "Crawling https://example.com/a", 10.0),
                (now, "Extracting content", 0.5),
                (now, "Crawling https://example.com/b", 10.0),
            ]
            # Start a new crawling activity
            reporter._current_activity = "Crawling https://example.com/c"
            reporter._activity_start = time.time()

            widget = reporter._build_widget()
            assert widget.activity_start_time != ""
            assert widget.activity_eta != ""
            assert widget.activity_est_duration != ""

    def test_build_widget_no_eta_without_history(self):
        """_build_widget has empty ETA when no prior same-category activities exist."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            # Start a crawling activity with no prior log
            reporter._current_activity = "Crawling https://example.com/a"
            reporter._activity_start = time.time()

            widget = reporter._build_widget()
            assert widget.activity_start_time != ""
            assert widget.activity_eta == ""
            assert widget.activity_est_duration == ""

    def test_update_marks_failed_activity(self):
        """update() with success=False prepends fail marker to activity label."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Crawling https://example.com/blocked")
            reporter.update("https://example.com/blocked", success=False)

            assert len(reporter._activity_log) == 1
            label = reporter._activity_log[0][1]
            assert label.startswith("\u274c FAILED")
            assert "Crawling https://example.com/blocked" in label

    def test_update_success_no_fail_marker(self):
        """update() with success=True does NOT add fail marker."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Crawling https://example.com/ok")
            reporter.update("https://example.com/ok", success=True)

            assert len(reporter._activity_log) == 1
            label = reporter._activity_log[0][1]
            assert not label.startswith("\u274c")

    def test_failed_log_entry_styled_red(self):
        """Failed log entries get the c4md-log-fail CSS class."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "Crawling https://example.com/ok", 5.0),
                (now, "\u274c FAILED \u2014 Crawling https://example.com/blocked", 8.0),
            ],
        )
        html = widget._repr_html_()
        assert "c4md-log-fail" in html
        # Normal entry should NOT have fail class — check first entry is not styled
        assert html.count("c4md-log-fail") == 3  # CSS rules (light + dark) + one entry

    def test_repr_html_dark_mode_styles(self):
        """Widget HTML includes dark-mode CSS media query."""
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert "prefers-color-scheme: dark" in html
        # Key dark-mode color overrides
        assert "#f0f0f0" in html  # header
        assert "#d0d0d0" in html  # footer
        assert "#64b5f6" in html  # activity
        assert "#81c784" in html  # percentage
        assert "#ef5350" in html  # fail
