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
