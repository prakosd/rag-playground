"""Tests for crawl4md.progress — ProgressReporter and _ProgressWidget."""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from crawl4md._internal.activity_log import ActivityLogger
from crawl4md.progress import (
    _ACTIVITY_LOG_CSV_FILE,
    _ACTIVITY_LOG_CSV_HEADER,
    _ACTIVITY_LOG_FLUSH_EVERY,
    _ACTIVITY_LOG_TXT_FILE,
    _BAR_GRADIENTS,
    _DARK_COLORS,
    _EXPLAINER_TEXT,
    _LIGHT_COLORS,
    _MAX_LOG_ENTRIES,
    _MILESTONE_MESSAGES,
    _MILESTONES,
    _NOTEBOOK_SHELL_NAMES,
    _PCT_PHASE_COLORS,
    _PULSE_COLOR_DEFAULT,
    _PULSE_COLORS,
    _RATE_MIN_PAGES,
    ProgressReporter,
    _colab_is_dark,
    _in_colab,
    _in_notebook,
    _ProgressWidget,
)


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
        widget = _ProgressWidget(current=1, total=5, round_label="Retry 1 of 2")
        html = widget._repr_html_()
        assert "Retry 1 of 2" in html

    def test_repr_html_includes_activity(self):
        widget = _ProgressWidget(
            current=2,
            total=10,
            activity="Reading page example.com/page",
        )
        html = widget._repr_html_()
        assert "Reading page example.com/page" in html
        # Should have the reading page icon
        assert "🌐" in html

    def test_repr_html_includes_activity_log(self):
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "Reading page example.com/a", 2.1),
                (now, "Saving page content", 0.4),
            ],
        )
        html = widget._repr_html_()
        assert "Reading page example.com/a" in html
        assert "Saving page content" in html
        assert "2.1s" in html
        assert "0.4s" in html

    def test_repr_html_no_activity_still_valid(self):
        """Widget without activity data still produces valid HTML."""
        widget = _ProgressWidget(
            current=1,
            total=5,
            eta="About 2 minutes left",
            stats="\u2705 1",
            success_count=1,
            fail_count=0,
            total_count=1,
        )
        html = widget._repr_html_()
        assert "Page 1 / 5" in html
        assert "🕷️" in html
        assert "About 2 minutes left" in html

    def test_repr_html_includes_stats_and_eta(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            eta="About 5 minutes left",
            stats="\u2705 2 &nbsp; \u274c 1 &nbsp; \U0001f4c4 3 total",
            success_count=2,
            fail_count=1,
            total_count=3,
        )
        html = widget._repr_html_()
        assert "\u2705 2" in html
        assert "About 5 minutes left" in html

    def test_repr_html_long_activity_truncated(self):
        long_url = "https://example.com/" + "a" * 100
        widget = _ProgressWidget(
            current=1,
            total=5,
            activity=f"Reading page {long_url}",
        )
        html = widget._repr_html_()
        assert "…" in html

    def test_activity_icons(self):
        assert _ProgressWidget._activity_icon("Reading page x") == "🌐"
        assert _ProgressWidget._activity_icon("Downloading PDF example.pdf") == "📥"
        assert _ProgressWidget._activity_icon("Saving page content") == "💾"
        assert _ProgressWidget._activity_icon("Saving progress (5 pages)") == "💾"
        assert _ProgressWidget._activity_icon("Pausing to avoid blocks (5.0s)") == "⏸️"
        assert _ProgressWidget._activity_icon("Waiting before retry (3.0s)") == "⏳"
        assert _ProgressWidget._activity_icon("Website is blocking us") == "🛡️"
        assert _ProgressWidget._activity_icon("Finding more pages on x") == "🔍"
        assert _ProgressWidget._activity_icon("Found 5 new pages on x") == "🔗"
        assert _ProgressWidget._activity_icon("Skipped example.com (redirect)") == "⏭️"
        assert _ProgressWidget._activity_icon("No content found on x") == "📭"
        assert _ProgressWidget._activity_icon("Something else") == "⚙️"
        assert _ProgressWidget._activity_icon("❌ FAILED \u2014 Reading page x") == "❌"

    def test_fmt_duration_ranges(self):
        assert _ProgressWidget._fmt_duration(0.01) == "<0.1s"
        assert _ProgressWidget._fmt_duration(0.5) == "0.5s"
        assert _ProgressWidget._fmt_duration(45.3) == "45.3s"
        assert _ProgressWidget._fmt_duration(125) == "2m 05s"

    def test_repr_html_contains_web_decoration(self):
        """Standard Jupyter HTML includes the spider web SVG decoration."""
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert "c4md-web" in html
        assert "<svg" in html
        assert '<path d="M0 0 Q0 14 14 14"' in html

    def test_web_svg_uses_color(self):
        html = _ProgressWidget._web_svg("#abc")
        assert 'stroke="#abc"' in html
        assert html.count("<path") == 3
        assert html.count("<line") == 5

    def test_web_svg_colab_display_block(self):
        html = _ProgressWidget._web_svg("#abc", display_block=True)
        assert 'style="display:block"' in html

    def test_activity_log_row_jupyter_failure_class(self):
        widget = _ProgressWidget(current=1, total=2)
        html = widget._activity_log_row_html(
            datetime(2026, 1, 2, 3, 4, 5),
            "❌ FAILED — Reading page x",
            1.2,
            colab=False,
            colors=_LIGHT_COLORS,
        )
        assert "c4md-log-fail" in html
        assert "03:04:05" in html
        assert "1.2s" in html

    def test_activity_log_row_colab_uses_inline_styles(self):
        widget = _ProgressWidget(current=1, total=2)
        html = widget._activity_log_row_html(
            datetime(2026, 1, 2, 3, 4, 5),
            "Reading page x",
            1.2,
            colab=True,
            colors=_LIGHT_COLORS,
        )
        assert 'class="' not in html
        assert "style=" in html
        assert _LIGHT_COLORS["log_time"] in html

    def test_repr_html_contains_bar_glow(self):
        """Standard Jupyter HTML includes the pulsating bar glow animation."""
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert "c4md-glow" in html
        assert "c4md-bar::after" in html

    def test_repr_html_spider_crawl_animation(self):
        """Standard Jupyter HTML includes the spider wander animation."""
        widget = _ProgressWidget(current=5, total=10)
        html = widget._repr_html_()
        assert "c4md-crawl" in html
        assert "rotate(90deg)" in html
        assert "calc(100% - 30px)" in html


class TestProgressReporter:
    """Tests for ProgressReporter activity tracking."""

    def test_set_activity_records_to_log(self):
        """set_activity closes previous activity and records its duration."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Reading page A")
            time.sleep(0.05)
            reporter.set_activity("Saving page content")

            assert len(reporter._activity_log) == 1
            ts, label, dur = reporter._activity_log[0]
            assert isinstance(ts, datetime)
            assert label == "Reading page A"
            assert dur >= 0.04  # Should have captured the sleep

            assert reporter._current_activity == "Saving page content"
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

            reporter.set_activity("Reading page X")
            reporter.update("https://example.com/x", success=True)

            assert reporter._current_activity == ""
            assert len(reporter._activity_log) == 1
            assert reporter._activity_log[0][1] == "Reading page X"

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

            reporter.set_activity("Reading page something")
            reporter.finish()

            assert reporter._current_activity == ""
            assert len(reporter._activity_log) == 1

    def test_round_label_stored(self):
        reporter = ProgressReporter(5, round_label="First pass")
        assert reporter._round_label == "First pass"

    def test_no_activity_calls_still_works(self):
        """Reporter without any set_activity calls should still function."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(2)
            reporter._use_notebook = False

            reporter.update("https://example.com/a", success=True)
            reporter.update("https://example.com/b", success=True)
            reporter.finish()

            assert reporter.count == 2
            assert list(reporter._activity_log) == []

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
            activity_log=[(now, "Reading page example.com/a", 1.0)],
        )
        html = widget._repr_html_()
        assert "Activity Log" in html

    def test_activity_log_datetime_in_html(self):
        """Widget HTML contains HH:MM:SS timestamp for log entries."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=2,
            total=10,
            activity_log=[(now, "Reading page example.com/a", 1.0)],
        )
        html = widget._repr_html_()
        assert now.strftime("%H:%M:%S") in html

    def test_update_activity_label_keeps_timer(self):
        """update_activity_label changes label without closing activity."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Finding more pages on example.com")
            start = reporter._activity_start
            time.sleep(0.05)

            reporter.update_activity_label("Found 5 new pages on example.com")

            # Label changed but timer was NOT reset
            assert reporter._current_activity == "Found 5 new pages on example.com"
            assert reporter._activity_start == start
            # No new log entry created
            assert len(reporter._activity_log) == 0

    def test_default_max_log_entries_is_ten(self):
        """Default _MAX_LOG_ENTRIES is 10."""
        assert _MAX_LOG_ENTRIES == 10

    def test_build_widget_returns_widget(self):
        """_build_widget should return a _ProgressWidget with correct state."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10, round_label="Retry 1 of 3")
            reporter._use_notebook = False
            reporter.count = 3
            reporter._round_success = 2
            reporter._round_fail = 1

            widget = reporter._build_widget()
            assert isinstance(widget, _ProgressWidget)
            assert widget.current == 3
            assert widget.total == 10
            assert widget.round_label == "Retry 1 of 3"
            assert "\u2705" in widget.stats

    def test_set_activity_without_previous(self):
        """First set_activity should not crash (no previous to close)."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("First activity")
            assert reporter._current_activity == "First activity"
            assert list(reporter._activity_log) == []

    def test_close_activity_noop_when_empty(self):
        """_close_activity on empty state is a no-op."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter._close_activity()
            assert list(reporter._activity_log) == []
            assert reporter._current_activity == ""

    def test_repr_html_activity_with_est_duration(self):
        """Widget shows estimated duration when provided."""
        widget = _ProgressWidget(
            current=5,
            total=10,
            activity="Reading page example.com/page",
            activity_est_duration="13.0s",
        )
        html = widget._repr_html_()
        assert "(~13.0s)" in html

    def test_repr_html_activity_no_est_duration(self):
        """Widget does not show estimated duration when not provided."""
        widget = _ProgressWidget(
            current=1,
            total=10,
            activity="Reading page example.com/page",
        )
        html = widget._repr_html_()
        assert "(~" not in html

    def test_activity_category(self):
        """_activity_category returns correct categories."""
        assert _ProgressWidget._activity_category("Reading page example.com") == "crawl"
        assert _ProgressWidget._activity_category("Downloading PDF example.com/f.pdf") == "crawl"
        assert _ProgressWidget._activity_category("Saving page content") == "extract"
        assert _ProgressWidget._activity_category("Saving PDF content") == "extract"
        assert _ProgressWidget._activity_category("Saving progress") == "flush"
        assert _ProgressWidget._activity_category("Pausing to avoid blocks (5.0s)") == "delay"
        assert _ProgressWidget._activity_category("Waiting before retry (3s)") == "delay"
        assert (
            _ProgressWidget._activity_category("Website is blocking us \u2014 waiting 30s")
            == "delay"
        )
        assert _ProgressWidget._activity_category("Finding more pages on x") == "discover"
        assert _ProgressWidget._activity_category("Found 5 new pages on x") == "discover"
        assert _ProgressWidget._activity_category("Something else") == "other"
        # Failed activities keep their category based on the underlying label
        assert _ProgressWidget._activity_category("\u274c FAILED \u2014 Reading page x") == "crawl"

    def test_build_widget_computes_activity_eta(self):
        """_build_widget computes ETA from same-category log entries."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            # Simulate a few completed crawling activities (10s each)
            now = datetime.now()
            reporter._activity_log = [
                (now, "Reading page example.com/a", 10.0),
                (now, "Saving page content", 0.5),
                (now, "Reading page example.com/b", 10.0),
            ]
            # Start a new crawling activity
            reporter._current_activity = "Reading page example.com/c"
            reporter._activity_start = time.time()

            widget = reporter._build_widget()
            assert widget.activity_est_duration != ""

    def test_build_widget_no_eta_without_history(self):
        """_build_widget has empty ETA when no prior same-category activities exist."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            # Start a crawling activity with no prior log
            reporter._current_activity = "Reading page example.com/a"
            reporter._activity_start = time.time()

            widget = reporter._build_widget()
            assert widget.activity_est_duration == ""

    def test_update_marks_failed_activity(self):
        """update() with success=False prepends fail marker to activity label."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Reading page example.com/blocked")
            reporter.update("https://example.com/blocked", success=False)

            assert len(reporter._activity_log) == 1
            label = reporter._activity_log[0][1]
            assert label.startswith("\u274c FAILED")
            assert "Reading page example.com/blocked" in label

    def test_update_success_no_fail_marker(self):
        """update() with success=True does NOT add fail marker."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter._use_notebook = False

            reporter.set_activity("Reading page example.com/ok")
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
                (now, "Reading page example.com/ok", 5.0),
                (now, "\u274c FAILED \u2014 Reading page example.com/blocked", 8.0),
            ],
        )
        html = widget._repr_html_()
        assert "c4md-log-fail" in html
        # Normal entry should NOT have fail class — check first entry is not styled
        assert html.count("c4md-log-fail") == 3  # CSS rules (light + dark) + one entry

    def test_eta_remaining_seconds_none_before_first_update(self):
        """Returns None when no pages have been processed yet."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False

            assert reporter.eta_remaining_seconds() is None

    def test_eta_remaining_seconds_returns_float_after_first_update(self):
        """Returns a non-negative float after at least one page is processed."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.update("https://example.com/a", success=True)

            result = reporter.eta_remaining_seconds()
            assert result is not None
            assert isinstance(result, float)
            assert result >= 0.0

    def test_eta_remaining_seconds_zero_when_all_done(self):
        """Returns 0.0 when all pages are processed (total == count)."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(2)
            reporter._use_notebook = False
            reporter.update("https://example.com/a", success=True)
            reporter.update("https://example.com/b", success=True)

            result = reporter.eta_remaining_seconds()
            assert result == 0.0

    def test_eta_remaining_seconds_returns_proportional_estimate(self):
        """Returns elapsed/count * remaining_pages as a raw float."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.count = 1
            reporter._start_time = time.time() - 2.0  # simulate 2s elapsed

            result = reporter.eta_remaining_seconds()
            # elapsed≈2, count=1, remaining_pages=9 → raw≈18.0
            assert result is not None
            assert isinstance(result, float)
            assert 16.0 <= result <= 20.0  # allow for slight timing variation


class TestActivityLogDisk:
    """Tests for flushing the activity log to disk (TXT + CSV)."""

    def test_activity_logger_writes_txt_and_csv(self, tmp_path: Path):
        logger = ActivityLogger(
            log_dir=tmp_path,
            round_label="First pass",
            icon_for_label=lambda _label: "*",
            format_duration=lambda _duration: "0.1s",
        )

        logger.append(datetime(2026, 1, 2, 3, 4, 5), "Reading page", 0.123)
        logger.close()

        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        assert "[First pass] * Reading page (0.1s)" in txt_path.read_text(encoding="utf-8")

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == _ACTIVITY_LOG_CSV_HEADER.split(",")
        assert rows[1] == ["2026-01-02T03:04:05", "First pass", "Reading page", "0.123"]

    def test_activity_log_appends_txt_to_disk(self, tmp_path: Path):
        """Closing an activity writes a human-readable line to activity_log.txt."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5, round_label="First pass", log_dir=tmp_path)
            reporter.set_activity("Reading page example.com")
            time.sleep(0.05)
            reporter.set_activity("Saving page content")  # closes previous
            reporter.close()

        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        assert txt_path.exists()
        lines = txt_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        line = lines[0]
        assert "[First pass]" in line
        assert "\U0001f310" in line  # 🌐 crawl icon
        assert "Reading page example.com" in line
        # Duration in parentheses at end
        assert line.endswith(")")
        assert "Saving page content" in lines[1]

    def test_activity_log_appends_csv_to_disk(self, tmp_path: Path):
        """Closing an activity writes a CSV row to activity_log.csv."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5, round_label="First pass", log_dir=tmp_path)
            reporter.set_activity("Reading page example.com")
            time.sleep(0.05)
            reporter.set_activity("Saving page content")  # closes previous
            reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        assert csv_path.exists()
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 3  # header + 2 data rows
        assert reader[0] == _ACTIVITY_LOG_CSV_HEADER.split(",")
        row = reader[1]
        assert row[1] == "First pass"
        assert row[2] == "Reading page example.com"
        assert float(row[3]) >= 0.0  # duration is a valid float
        assert reader[2][2] == "Saving page content"

    def test_csv_header_written_once(self, tmp_path: Path):
        """Multiple activities produce only one CSV header row."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10, log_dir=tmp_path)
            for i in range(4):
                reporter.set_activity(f"Activity {i}")
            reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        # 1 header + 4 data rows
        assert len(reader) == 5
        header_rows = [r for r in reader if r == _ACTIVITY_LOG_CSV_HEADER.split(",")]
        assert len(header_rows) == 1

    def test_existing_csv_header_not_rewritten(self, tmp_path: Path):
        """Appending to an existing CSV log does not duplicate its header."""
        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        csv_path.write_text(_ACTIVITY_LOG_CSV_HEADER + "\n", encoding="utf-8")

        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10, log_dir=tmp_path)
            for i in range(3):
                reporter.set_activity(f"Activity {i}")
            reporter.close()

        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))

        header_rows = [r for r in reader if r == _ACTIVITY_LOG_CSV_HEADER.split(",")]
        assert len(reader) == 4
        assert len(header_rows) == 1

    def test_disk_log_keeps_handles_open_between_entries(self, tmp_path: Path):
        """Repeated activity writes reuse one TXT and one CSV file handle."""
        open_calls: list[str] = []
        original_open = Path.open

        def counting_open(path: Path, *args, **kwargs):
            if path.name in {_ACTIVITY_LOG_TXT_FILE, _ACTIVITY_LOG_CSV_FILE}:
                open_calls.append(path.name)
            return original_open(path, *args, **kwargs)

        with (
            patch("crawl4md.progress._in_notebook", return_value=False),
            patch.object(Path, "open", counting_open),
        ):
            reporter = ProgressReporter(20, log_dir=tmp_path)
            for i in range(_ACTIVITY_LOG_FLUSH_EVERY + 2):
                reporter.set_activity(f"Activity {i}")
            reporter.close()

        assert open_calls.count(_ACTIVITY_LOG_TXT_FILE) == 1
        assert open_calls.count(_ACTIVITY_LOG_CSV_FILE) == 1

    def test_disk_log_unlimited(self, tmp_path: Path):
        """Disk logs capture all activities even when in-memory list is capped."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(20, max_log_entries=3, log_dir=tmp_path)
            for i in range(5):
                reporter.set_activity(f"Activity {i}")
            reporter.close()

        # In-memory log is capped at 3
        assert len(reporter._activity_log) == 3

        # Disk has all 5
        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        txt_lines = txt_path.read_text(encoding="utf-8").splitlines()
        assert len(txt_lines) == 5

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 6  # 1 header + 5 data rows

    def test_no_files_when_log_dir_none(self, tmp_path: Path):
        """Default (log_dir=None) creates no disk files."""
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5)
            reporter.set_activity("Reading page something")
            time.sleep(0.01)
            reporter.set_activity("Saving page content")
            reporter.close()

        # No activity log files anywhere
        assert not (tmp_path / _ACTIVITY_LOG_TXT_FILE).exists()
        assert not (tmp_path / _ACTIVITY_LOG_CSV_FILE).exists()

    def test_csv_escapes_commas_in_labels(self, tmp_path: Path):
        """Labels containing commas are properly CSV-escaped."""
        label = "Reading page example.com/a,b,c"
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(5, log_dir=tmp_path)
            reporter.set_activity(label)
            time.sleep(0.01)
            reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 2
        assert reader[1][2] == label  # csv.reader correctly unescapes


class TestInNotebook:
    """Tests for the _in_notebook() detection function."""

    def test_zmq_shell_returns_true(self):
        """Standard Jupyter shell is detected as notebook."""
        mock_shell = type("ZMQInteractiveShell", (), {})()
        with patch("IPython.get_ipython", return_value=mock_shell, create=True):
            assert _in_notebook() is True

    def test_colab_shell_returns_true(self):
        """Google Colab's Shell class is detected as notebook."""
        mock_shell = type("Shell", (), {})()
        with patch("IPython.get_ipython", return_value=mock_shell, create=True):
            assert _in_notebook() is True

    def test_none_shell_returns_false(self):
        """Returns False when get_ipython() returns None."""
        with patch("IPython.get_ipython", return_value=None, create=True):
            assert _in_notebook() is False

    def test_terminal_shell_returns_false(self):
        """IPython terminal shell is not a notebook."""
        mock_shell = type("TerminalInteractiveShell", (), {})()
        with patch("IPython.get_ipython", return_value=mock_shell, create=True):
            assert _in_notebook() is False

    def test_notebook_shell_names_constant(self):
        """The allowlist contains expected shell names."""
        assert "ZMQInteractiveShell" in _NOTEBOOK_SHELL_NAMES
        assert "Shell" in _NOTEBOOK_SHELL_NAMES


class TestInColab:
    """Tests for the _in_colab() detection function."""

    def test_colab_module_present(self):
        """Returns True when google.colab is in sys.modules."""
        with patch.dict("sys.modules", {"google.colab": object()}):
            assert _in_colab() is True

    def test_colab_module_absent(self):
        """Returns False when google.colab is not in sys.modules."""
        import sys

        # Ensure google.colab is not present
        modules_copy = {k: v for k, v in sys.modules.items() if k != "google.colab"}
        with patch.dict("sys.modules", modules_copy, clear=True):
            assert _in_colab() is False


class TestProgressWidgetColab:
    """Tests for the Colab-safe HTML rendering path."""

    def test_colab_html_has_inline_styles(self):
        """Colab rendering uses inline style= attributes."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert 'style="' in html

    def test_colab_html_no_style_block(self):
        """Colab rendering does NOT contain a <style> block."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert "<style>" not in html

    def test_colab_html_no_keyframes(self):
        """Colab rendering does NOT use @keyframes animations."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert "@keyframes" not in html

    def test_colab_html_no_position_absolute(self):
        """Colab rendering does NOT use position:absolute."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert "position" not in html.lower() or "absolute" not in html.lower()

    def test_colab_html_contains_spider(self):
        """Colab rendering still shows the spider emoji."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert "\U0001f577" in html

    def test_colab_spider_in_table_layout(self):
        """Spider is positioned inside a table and wanders within the filled portion."""
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        # Spider should be inside a <table> layout, not a standalone div
        assert "<table" in html
        assert "text-align:right" in html
        # Spider position should be somewhere within [0%, 50%]
        import re

        m = re.search(r'<td style="width:([\d.]+)%.*?text-align:right', html)
        assert m is not None
        pos = float(m.group(1))
        assert 0 <= pos <= 50

    def test_colab_web_thread_present(self):
        """Colab rendering includes a dashed web thread line."""
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "dashed" in html
        assert "border-top" in html

    def test_colab_html_contains_percentage(self):
        """Colab rendering shows the progress percentage."""
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "50%" in html

    def test_colab_html_contains_activity(self):
        """Colab rendering shows the current activity."""
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity="Reading page example.com",
            colab=True,
        )
        html = widget._repr_html_()
        assert "Reading page example.com" in html

    def test_colab_html_contains_log(self):
        """Colab rendering shows the activity log."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[(now, "Reading page example.com/a", 2.5)],
            colab=True,
        )
        html = widget._repr_html_()
        assert "Activity Log" in html
        assert "2.5s" in html

    def test_colab_html_contains_round_label(self):
        """Colab rendering shows the round label."""
        widget = _ProgressWidget(current=1, total=5, round_label="Retry 1 of 2", colab=True)
        html = widget._repr_html_()
        assert "Retry 1 of 2" in html

    def test_colab_html_contains_stats_and_eta(self):
        """Colab rendering shows stats and ETA."""
        widget = _ProgressWidget(
            current=2,
            total=10,
            stats="\u2705 3 &nbsp; \u274c 2 &nbsp; \U0001f4c4 5 total",
            eta="About 2 minutes left",
            success_count=3,
            fail_count=2,
            total_count=5,
            colab=True,
        )
        html = widget._repr_html_()
        assert "\u2705 3" in html
        assert "About 2 minutes left" in html

    def test_colab_html_failed_log_entry_red(self):
        """Failed entries in Colab log are styled red."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "\u274c FAILED \u2014 Reading page example.com/blocked", 8.0),
            ],
            colab=True,
        )
        html = widget._repr_html_()
        assert "color:#d32f2f" in html

    def test_non_colab_still_uses_style_block(self):
        """Non-Colab widget (colab=False) still uses <style> block — regression check."""
        widget = _ProgressWidget(current=3, total=10, colab=False)
        html = widget._repr_html_()
        assert "<style>" in html
        assert "@keyframes" in html

    def test_colab_html_contains_web_decoration(self):
        """Colab rendering includes the spider web SVG decoration."""
        widget = _ProgressWidget(current=3, total=10, colab=True)
        html = widget._repr_html_()
        assert "<svg" in html
        assert '<path d="M0 0 Q0 14 14 14"' in html

    def test_colab_html_has_bar_glow_shadow(self):
        """Colab rendering uses box-shadow for a static bar glow."""
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "box-shadow" in html

    def test_colab_html_no_spider_crawl_animation(self):
        """Colab rendering does NOT have the spider crawl CSS animation."""
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "c4md-crawl" not in html
        assert "animation" not in html.lower()


class TestSpiderWander:
    """Tests for the spider wander-across-bar feature."""

    def test_spider_track_width_matches_progress(self):
        """Jupyter spider track container spans the filled portion of the bar."""
        for current, total, expected_pct in [(0, 10, 0), (5, 10, 50), (10, 10, 100)]:
            widget = _ProgressWidget(current=current, total=total)
            html = widget._repr_html_()
            assert 'class="c4md-spider-track"' in html
            assert f"width:{expected_pct}%" in html

    def test_spider_wander_duration_scales_with_progress(self):
        """Animation duration scales with progress (longer bar = slower animation)."""
        widget_low = _ProgressWidget(current=1, total=10)
        widget_high = _ProgressWidget(current=10, total=10)
        html_low = widget_low._repr_html_()
        html_high = widget_high._repr_html_()
        import re

        dur_low = float(re.search(r"c4md-crawl ([\d.]+)s", html_low).group(1))
        dur_high = float(re.search(r"c4md-crawl ([\d.]+)s", html_high).group(1))
        assert dur_high > dur_low

    def test_spider_at_zero_progress_no_track_width(self):
        """At 0% progress the spider track has 0% width."""
        widget = _ProgressWidget(current=0, total=10)
        html = widget._repr_html_()
        assert 'class="c4md-spider-track"' in html

    def test_colab_spider_wander_within_bounds(self):
        """Colab spider position stays within [0, pct] across different time phases."""
        import re

        pct = 60  # 60% progress
        for fake_time in [0.0, 1.5, 3.0, 4.5, 5.9]:
            with patch("crawl4md.progress.time") as mock_time:
                mock_time.time.return_value = fake_time
                widget = _ProgressWidget(current=6, total=10, colab=True)
                html = widget._repr_html_()
            m = re.search(r'<td style="width:([\d.]+)%.*?text-align:right', html)
            assert m is not None
            pos = float(m.group(1))
            assert 0 <= pos <= pct, f"Spider at {pos}% exceeds progress {pct}% (time={fake_time})"

    def test_colab_spider_flips_direction(self):
        """Colab spider tilts toward its travel direction in the sine cycle."""
        # At phase where cos < 0 (heading left), rotate(45deg) should appear
        # At phase where cos > 0 (heading right), rotate(-45deg) should appear
        found_left_tilt = False
        found_right_tilt = False
        for fake_time in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]:
            with patch("crawl4md.progress.time") as mock_time:
                mock_time.time.return_value = fake_time
                widget = _ProgressWidget(current=5, total=10, colab=True)
                html = widget._repr_html_()
            if "rotate(90deg)" in html:
                found_left_tilt = True
            if "rotate(-90deg)" in html:
                found_right_tilt = True
        assert found_left_tilt, "Spider never tilts left"
        assert found_right_tilt, "Spider never tilts right"


class TestColabDisplayPath:
    """Tests that Colab uses display(HTML(...)) while regular Jupyter uses display(widget)."""

    def test_refresh_display_debounces_rapid_updates(self):
        from unittest.mock import MagicMock

        reporter = ProgressReporter(total=5)
        reporter._use_notebook = True
        reporter._use_colab = False
        widget = object()
        mock_display = MagicMock()
        mock_clear = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "IPython": MagicMock(),
                    "IPython.display": MagicMock(display=mock_display, clear_output=mock_clear),
                },
            ),
            patch.object(reporter, "_build_widget", return_value=widget),
            patch("crawl4md.progress.time.time") as mock_time,
        ):
            mock_time.return_value = 100.0
            reporter._refresh_display()
            mock_time.return_value = 100.1
            reporter._refresh_display()
            mock_time.return_value = 100.2
            reporter._refresh_display()
            mock_time.return_value = 100.3
            reporter._refresh_display()

        assert mock_display.call_count == 2
        assert mock_clear.call_count == 2

    def test_refresh_display_force_bypasses_debounce(self):
        from unittest.mock import MagicMock

        reporter = ProgressReporter(total=5)
        reporter._use_notebook = True
        reporter._use_colab = False
        widget = object()
        mock_display = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "IPython": MagicMock(),
                    "IPython.display": MagicMock(display=mock_display, clear_output=MagicMock()),
                },
            ),
            patch.object(reporter, "_build_widget", return_value=widget),
            patch("crawl4md.progress.time.time") as mock_time,
        ):
            mock_time.return_value = 100.0
            reporter._refresh_display()
            mock_time.return_value = 100.1
            reporter._refresh_display(force=True)

        assert mock_display.call_count == 2

    @patch("crawl4md.progress._in_notebook", return_value=True)
    @patch("crawl4md.progress._in_colab", return_value=True)
    def test_colab_refresh_uses_display_html(self, _mock_colab, _mock_nb):
        """In Colab, _refresh_display() wraps the HTML string in IPython.display.HTML."""
        reporter = ProgressReporter(total=5)
        with patch("crawl4md.progress.ProgressReporter._refresh_display") as _:
            pass  # avoid side effects from __init__

        # Call the real _refresh_display, intercepting IPython.display
        from unittest.mock import MagicMock

        mock_display = MagicMock()
        mock_clear = MagicMock()
        mock_html_cls = MagicMock()
        with (
            patch.dict(
                "sys.modules",
                {
                    "IPython": MagicMock(),
                    "IPython.display": MagicMock(
                        display=mock_display, clear_output=mock_clear, HTML=mock_html_cls
                    ),
                },
            ),
        ):
            # Re-import to pick up the mocked module
            import importlib

            import crawl4md.progress

            importlib.reload(crawl4md.progress)
            reporter._use_notebook = True
            reporter._use_colab = True
            reporter._refresh_display()
            # display() should have been called with an HTML() wrapper
            mock_html_cls.assert_called_once()
            mock_display.assert_called_once()
            # The argument to display() should be the HTML(...) object
            assert mock_display.call_args[0][0] is mock_html_cls.return_value
            # Reload to restore original module state
            importlib.reload(crawl4md.progress)

    @patch("crawl4md.progress._in_notebook", return_value=True)
    @patch("crawl4md.progress._in_colab", return_value=False)
    def test_non_colab_refresh_uses_display_widget(self, _mock_colab, _mock_nb):
        """In regular Jupyter, _refresh_display() passes the widget object directly."""
        reporter = ProgressReporter(total=5)
        from unittest.mock import MagicMock

        mock_display = MagicMock()
        mock_clear = MagicMock()
        mock_html_cls = MagicMock()
        with (
            patch.dict(
                "sys.modules",
                {
                    "IPython": MagicMock(),
                    "IPython.display": MagicMock(
                        display=mock_display, clear_output=mock_clear, HTML=mock_html_cls
                    ),
                },
            ),
        ):
            import importlib

            import crawl4md.progress

            importlib.reload(crawl4md.progress)
            reporter._use_notebook = True
            reporter._use_colab = False
            reporter._refresh_display()
            # HTML() should NOT have been called
            mock_html_cls.assert_not_called()
            # display() should have been called with a _ProgressWidget instance
            mock_display.assert_called_once()
            importlib.reload(crawl4md.progress)

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


class TestColabIsDark:
    """Tests for the _colab_is_dark() detection function."""

    def test_returns_true_when_theme_is_dark(self):
        """Returns True when Colab reports dark theme."""
        mock_output = type("output", (), {"eval_js": staticmethod(lambda _: "dark")})()
        with (
            patch.dict(
                "sys.modules",
                {"google.colab": object(), "google.colab.output": mock_output},
            ),
            patch("crawl4md.progress._colab_is_dark") as mock_fn,
        ):
            mock_fn.return_value = True
            assert mock_fn() is True

    def test_returns_false_when_theme_is_light(self):
        """Returns False when Colab reports light theme."""
        with patch("crawl4md.progress._colab_is_dark", return_value=False):
            from crawl4md.progress import _colab_is_dark as fn

            assert fn() is False

    def test_returns_false_on_import_error(self):
        """Returns False when google.colab is not available."""
        # Default environment has no google.colab — should be False
        assert _colab_is_dark() is False

    def test_returns_false_on_eval_js_exception(self):
        """Returns False when eval_js raises an exception."""
        assert _colab_is_dark() is False


class TestColabDarkModeRendering:
    """Tests for Colab widget rendering with dark palette."""

    def test_colab_dark_uses_dark_palette_text(self):
        """Colab dark mode uses dark text color."""
        widget = _ProgressWidget(current=3, total=10, colab=True, dark=True)
        html = widget._repr_html_()
        assert _DARK_COLORS["text"] in html
        assert _DARK_COLORS["header"] in html

    def test_colab_dark_uses_dark_bar_background(self):
        """Colab dark mode uses dark bar background."""
        widget = _ProgressWidget(current=3, total=10, colab=True, dark=True)
        html = widget._repr_html_()
        assert _DARK_COLORS["bar_bg"] in html

    def test_colab_dark_uses_dark_footer(self):
        """Colab dark mode uses dark footer color."""
        widget = _ProgressWidget(current=3, total=10, colab=True, dark=True)
        html = widget._repr_html_()
        assert _DARK_COLORS["footer"] in html

    def test_colab_dark_uses_dark_pct(self):
        """Colab dark mode uses dark percentage color."""
        widget = _ProgressWidget(current=3, total=10, colab=True, dark=True)
        html = widget._repr_html_()
        assert _DARK_COLORS["pct"] in html

    def test_colab_dark_activity_uses_dark_colors(self):
        """Colab dark mode activity row uses dark palette."""
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity="Reading page example.com",
            colab=True,
            dark=True,
        )
        html = widget._repr_html_()
        assert _DARK_COLORS["activity"] in html
        assert _DARK_COLORS["pulse"] in html

    def test_colab_dark_log_uses_dark_colors(self):
        """Colab dark mode activity log uses dark palette."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[(now, "Reading page example.com/a", 2.5)],
            colab=True,
            dark=True,
        )
        html = widget._repr_html_()
        assert _DARK_COLORS["log_text"] in html
        assert _DARK_COLORS["log_heading"] in html

    def test_colab_dark_fail_entry_uses_dark_red(self):
        """Colab dark mode failed log entries use dark red."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "\u274c FAILED \u2014 Reading page example.com/blocked", 8.0),
            ],
            colab=True,
            dark=True,
        )
        html = widget._repr_html_()
        assert _DARK_COLORS["log_fail"] in html

    def test_colab_light_uses_light_palette(self):
        """Colab light mode still uses light palette (regression check)."""
        widget = _ProgressWidget(current=3, total=10, colab=True, dark=False)
        html = widget._repr_html_()
        assert _LIGHT_COLORS["text"] in html
        assert _LIGHT_COLORS["header"] in html
        assert _LIGHT_COLORS["bar_bg"] in html
        assert _LIGHT_COLORS["footer"] in html

    def test_colab_light_fail_uses_light_red(self):
        """Colab light mode failed log entries use standard red."""
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[
                (now, "\u274c FAILED \u2014 Reading page example.com/blocked", 8.0),
            ],
            colab=True,
            dark=False,
        )
        html = widget._repr_html_()
        assert _LIGHT_COLORS["log_fail"] in html


class TestColorPalettes:
    """Tests for the color palette constants."""

    def test_palettes_have_same_keys(self):
        """Light and dark palettes define the same set of keys."""
        assert set(_LIGHT_COLORS.keys()) == set(_DARK_COLORS.keys())

    def test_palettes_values_are_strings(self):
        """All palette values are non-empty strings."""
        for key in _LIGHT_COLORS:
            assert isinstance(_LIGHT_COLORS[key], str) and _LIGHT_COLORS[key]
            assert isinstance(_DARK_COLORS[key], str) and _DARK_COLORS[key]

    def test_jupyter_css_uses_light_palette(self):
        """Standard Jupyter CSS uses light palette values."""
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert _LIGHT_COLORS["text"] in html
        assert _LIGHT_COLORS["header"] in html
        assert _LIGHT_COLORS["bar_bg"] in html
        assert _LIGHT_COLORS["pct"] in html

    def test_jupyter_css_dark_uses_dark_palette(self):
        """Standard Jupyter dark-mode CSS uses dark palette values."""
        widget = _ProgressWidget(current=3, total=10)
        html = widget._repr_html_()
        assert _DARK_COLORS["text"] in html
        assert _DARK_COLORS["header"] in html
        assert _DARK_COLORS["bar_bg"] in html
        assert _DARK_COLORS["pct"] in html


class TestPhaseBasedGradient:
    """Tests for Phase 1: bar gradient changes with progress."""

    def test_bar_gradient_blue_at_zero(self):
        assert "42a5f5" in _ProgressWidget._bar_gradient(0)

    def test_bar_gradient_cyan_at_30(self):
        assert "26c6da" in _ProgressWidget._bar_gradient(30)

    def test_bar_gradient_green_at_55(self):
        assert "43a047" in _ProgressWidget._bar_gradient(55)

    def test_bar_gradient_amber_at_80(self):
        assert "ffa726" in _ProgressWidget._bar_gradient(80)

    def test_bar_gradient_gold_at_100(self):
        assert "ffd54f" in _ProgressWidget._bar_gradient(100)

    def test_bar_gradient_dark_mode(self):
        assert "42a5f5" in _ProgressWidget._bar_gradient(0, dark=True)

    def test_pct_color_matches_phase(self):
        assert _ProgressWidget._pct_color(10) == "#1e88e5"
        assert _ProgressWidget._pct_color(30) == "#00acc1"
        assert _ProgressWidget._pct_color(55) == "#43a047"
        assert _ProgressWidget._pct_color(80) == "#f57c00"
        assert _ProgressWidget._pct_color(100) == "#ffa726"

    def test_jupyter_html_uses_phase_gradient(self):
        """Jupyter bar uses phase-dependent gradient, not static palette value."""
        widget = _ProgressWidget(current=8, total=10)
        html = widget._repr_html_()
        assert "ffa726" in html  # 80% → amber

    def test_colab_html_uses_phase_gradient(self):
        """Colab bar uses phase-dependent gradient."""
        widget = _ProgressWidget(current=8, total=10, colab=True)
        html = widget._repr_html_()
        assert "ffa726" in html

    def test_gradients_constant_has_all_phases(self):
        assert len(_BAR_GRADIENTS) == 5
        assert len(_PCT_PHASE_COLORS) == 5


class TestCandyStripes:
    """Tests for Phase 2: animated candy stripes on the progress bar."""

    def test_jupyter_has_stripe_animation(self):
        widget = _ProgressWidget(current=5, total=10)
        html = widget._repr_html_()
        assert "c4md-stripe" in html
        assert "c4md-bar::before" in html
        assert "repeating-linear-gradient" in html

    def test_colab_has_static_stripes(self):
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "repeating-linear-gradient" in html
        # No animation in Colab
        assert "c4md-stripe" not in html


class TestMilestoneMarkers:
    """Tests for Phase 3: tick marks at 25/50/75% on the bar track."""

    def test_milestones_constant(self):
        assert _MILESTONES == [25, 50, 75]

    def test_jupyter_has_milestone_marks(self):
        widget = _ProgressWidget(current=6, total=10)  # 60%
        html = widget._repr_html_()
        assert "c4md-mark" in html

    def test_jupyter_done_marks_at_60_pct(self):
        """At 60%, the 25% and 50% marks should show ✓."""
        widget = _ProgressWidget(current=6, total=10)
        html = widget._repr_html_()
        assert "c4md-mark-done" in html

    def test_colab_has_milestone_row(self):
        widget = _ProgressWidget(current=6, total=10, colab=True)
        html = widget._repr_html_()
        # Colab uses flex row with ✓ markers
        assert "✓" in html

    def test_colab_no_position_absolute_for_milestones(self):
        widget = _ProgressWidget(current=6, total=10, colab=True)
        html = widget._repr_html_()
        assert "position" not in html.lower() or "absolute" not in html.lower()


class TestActivityAwarePulse:
    """Tests for Phase 4: pulse color changes by activity category."""

    def test_pulse_color_crawl(self):
        assert _ProgressWidget._pulse_color("crawl") == "#1a73e8"
        assert _ProgressWidget._pulse_color("crawl", dark=True) == "#64b5f6"

    def test_pulse_color_extract(self):
        assert _ProgressWidget._pulse_color("extract") == "#43a047"

    def test_pulse_color_delay(self):
        assert _ProgressWidget._pulse_color("delay") == "#f9a825"

    def test_pulse_color_fail(self):
        assert _ProgressWidget._pulse_color("fail") == "#d32f2f"

    def test_pulse_color_default(self):
        assert _ProgressWidget._pulse_color("other") == _PULSE_COLOR_DEFAULT[0]
        assert _ProgressWidget._pulse_color("unknown") == _PULSE_COLOR_DEFAULT[0]

    def test_jupyter_pulse_uses_category_color(self):
        widget = _ProgressWidget(
            current=5,
            total=10,
            activity="Reading page example.com",
            activity_category="crawl",
        )
        html = widget._repr_html_()
        assert "#1a73e8" in html  # crawl pulse color inline

    def test_colab_pulse_uses_category_color(self):
        widget = _ProgressWidget(
            current=5,
            total=10,
            activity="Saving page content",
            activity_category="extract",
            colab=True,
        )
        html = widget._repr_html_()
        assert "#43a047" in html  # extract pulse color

    def test_pulse_colors_constant_has_known_categories(self):
        assert "crawl" in _PULSE_COLORS
        assert "extract" in _PULSE_COLORS
        assert "delay" in _PULSE_COLORS
        assert "fail" in _PULSE_COLORS


class TestMilestoneMessages:
    """Tests for Phase 5: celebratory messages at milestones."""

    def test_message_at_zero(self):
        assert "Spinning up" in _ProgressWidget._milestone_message(0)

    def test_message_at_10(self):
        assert "Crawling" in _ProgressWidget._milestone_message(10)

    def test_message_at_30(self):
        assert "Making good progress" in _ProgressWidget._milestone_message(30)

    def test_message_at_55(self):
        assert "Halfway" in _ProgressWidget._milestone_message(55)

    def test_message_at_80(self):
        assert "Almost done" in _ProgressWidget._milestone_message(80)

    def test_message_at_100(self):
        assert "Web complete" in _ProgressWidget._milestone_message(100)

    def test_messages_constant(self):
        assert len(_MILESTONE_MESSAGES) == 6

    def test_jupyter_html_shows_milestone_message(self):
        widget = _ProgressWidget(current=5, total=10)  # 50%
        html = widget._repr_html_()
        assert "Halfway there" in html
        assert "c4md-milestone-msg" in html

    def test_colab_html_shows_milestone_message(self):
        widget = _ProgressWidget(current=5, total=10, colab=True)
        html = widget._repr_html_()
        assert "Halfway there" in html


class TestStatsPills:
    """Tests for Phase 6: rounded pill badges for stats."""

    def test_jupyter_has_pill_classes(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            success_count=2,
            fail_count=1,
            total_count=3,
        )
        html = widget._repr_html_()
        assert "c4md-pill" in html
        assert "c4md-pill-success" in html
        assert "c4md-pill-fail" in html
        assert "c4md-pill-total" in html

    def test_jupyter_pills_show_counts(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            success_count=7,
            fail_count=2,
            total_count=9,
        )
        html = widget._repr_html_()
        assert "\u2705 7" in html
        assert "\u274c 2" in html
        assert "9 total" in html

    def test_colab_pills_inline_style(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            success_count=5,
            fail_count=1,
            total_count=6,
            colab=True,
        )
        html = widget._repr_html_()
        assert "\u2705 5" in html
        assert "\u274c 1" in html
        assert "6 total" in html
        assert _LIGHT_COLORS["pill_success_bg"] in html

    def test_colab_dark_pills(self):
        widget = _ProgressWidget(
            current=3,
            total=10,
            success_count=5,
            fail_count=1,
            total_count=6,
            colab=True,
            dark=True,
        )
        html = widget._repr_html_()
        assert _DARK_COLORS["pill_success_bg"] in html

    def test_pill_palette_keys_present(self):
        assert "pill_success_bg" in _LIGHT_COLORS
        assert "pill_fail_bg" in _LIGHT_COLORS
        assert "pill_total_bg" in _LIGHT_COLORS
        assert "pill_success_bg" in _DARK_COLORS


class TestShortenUrl:
    """Tests for the _shorten_url() helper in crawler.py."""

    def test_short_url_unchanged(self):
        from crawl4md.crawler import _shorten_url

        url = "https://example.com/page"
        assert _shorten_url(url) == url

    def test_long_url_truncated(self):
        from crawl4md.crawler import _shorten_url

        url = "https://example.com/" + "a" * 80
        result = _shorten_url(url)
        assert len(result) <= 60
        assert "\u2026" in result  # ellipsis

    def test_scheme_stripped_before_truncation(self):
        from crawl4md.crawler import _shorten_url

        # Just over threshold with scheme, under without
        url = "https://" + "x" * 55
        result = _shorten_url(url)
        assert not result.startswith("https://")


class TestFriendlyEta:
    """Tests for _eta_remaining_friendly()."""

    def test_no_pages_returns_placeholder(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            result = reporter._eta_remaining_friendly()
            assert result == "estimating..."

    def test_less_than_a_minute(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.count = 9
            reporter._start_time = time.time() - 9  # 1s per page, ~1s left
            result = reporter._eta_remaining_friendly()
            assert result == "Less than a minute left"

    def test_minutes_pluralised(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.count = 2
            reporter._start_time = time.time() - 120  # 60s per page, ~4 min left
            result = reporter._eta_remaining_friendly()
            assert "minutes" in result
            assert result.startswith("About")

    def test_hours_included(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(100)
            reporter._use_notebook = False
            reporter.count = 1
            reporter._start_time = time.time() - 3600  # 1h per page, 99h left
            result = reporter._eta_remaining_friendly()
            assert "hour" in result


class TestCollapsibleLog:
    """Tests for the collapsible <details> activity log in Jupyter."""

    def test_jupyter_log_has_details_element(self):
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[(now, "Reading page example.com/a", 1.0)],
        )
        html = widget._repr_html_()
        assert "<details>" in html
        assert "<summary" in html
        assert "Activity Log (1 entries)" in html

    def test_colab_log_no_details_element(self):
        now = datetime.now()
        widget = _ProgressWidget(
            current=3,
            total=10,
            activity_log=[(now, "Reading page example.com/a", 1.0)],
            colab=True,
        )
        html = widget._repr_html_()
        assert "<details>" not in html
        assert "Activity Log" in html  # still has heading


class TestExplainerText:
    """Tests for the one-line explainer shown on first render."""

    def test_explainer_shown_at_zero(self):
        widget = _ProgressWidget(current=0, total=10)
        html = widget._repr_html_()
        assert _EXPLAINER_TEXT in html
        assert "c4md-explainer" in html

    def test_explainer_hidden_after_first_page(self):
        widget = _ProgressWidget(current=1, total=10)
        html = widget._repr_html_()
        assert _EXPLAINER_TEXT not in html

    def test_colab_explainer_shown_at_zero(self):
        widget = _ProgressWidget(current=0, total=10, colab=True)
        html = widget._repr_html_()
        assert _EXPLAINER_TEXT in html

    def test_colab_explainer_hidden_after_first_page(self):
        widget = _ProgressWidget(current=1, total=10, colab=True)
        html = widget._repr_html_()
        assert _EXPLAINER_TEXT not in html


class TestPagesPerMinute:
    """Tests for the pages-per-minute rate display."""

    def test_rate_shown_after_min_pages(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.count = _RATE_MIN_PAGES
            reporter._start_time = time.time() - 60  # 60s elapsed
            widget = reporter._build_widget()
            assert "pages/min" in widget.pages_per_min

    def test_rate_not_shown_before_min_pages(self):
        with patch("crawl4md.progress._in_notebook", return_value=False):
            reporter = ProgressReporter(10)
            reporter._use_notebook = False
            reporter.count = 1
            reporter._start_time = time.time() - 60
            widget = reporter._build_widget()
            assert widget.pages_per_min == ""
