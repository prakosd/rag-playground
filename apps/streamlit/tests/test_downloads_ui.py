from __future__ import annotations

from app_support import downloads_ui


# Risk: the preview modal shows file timestamps; a bad epoch must not crash the
# dialog. Verify the UTC formatter returns a stable string. Type: unit.
def test_format_preview_timestamp_utc_formats_epoch() -> None:
    assert downloads_ui._format_preview_timestamp_utc(0) == "1970-01-01 00:00:00 UTC"


# Risk: a missing timestamp must render as "no value" rather than raising.
# Type: unit.
def test_format_preview_timestamp_utc_none_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(None) is None


# Risk: an out-of-range timestamp (e.g. corrupt stat) must be swallowed, not
# crash the preview dialog. Type: unit.
def test_format_preview_timestamp_utc_out_of_range_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(1e300) is None


# Risk: after a browser reset clears the session, the session folder does not yet
# exist and holds no files; the panel must still show so Import is reachable.
# Type: unit.
def test_should_show_files_panel_idle_shows_even_without_files() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=False) is True
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=True) is True


# Risk: an empty panel must not flash mid-write; while a job runs, show the panel
# only once it holds files. Type: unit.
def test_should_show_files_panel_hides_empty_panel_during_active_job() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=False) is False
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=True) is True
