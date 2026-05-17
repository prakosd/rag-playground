"""Activity log disk writer for ProgressReporter."""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO

__all__ = [
    "_ACTIVITY_LOG_CSV_FILE",
    "_ACTIVITY_LOG_CSV_HEADER",
    "_ACTIVITY_LOG_FLUSH_EVERY",
    "_ACTIVITY_LOG_TXT_FILE",
    "ActivityLogger",
]

_ACTIVITY_LOG_TXT_FILE = "activity_log.txt"
_ACTIVITY_LOG_CSV_FILE = "activity_log.csv"
_ACTIVITY_LOG_CSV_HEADER = "timestamp,round,activity,duration_seconds"
_ACTIVITY_LOG_FLUSH_EVERY = 10


class ActivityLogger:
    def __init__(
        self,
        *,
        log_dir: Path | None,
        round_label: str,
        icon_for_label: Callable[[str], str],
        format_duration: Callable[[float], str],
    ) -> None:
        self.log_dir = log_dir
        self.round_label = round_label
        self.icon_for_label = icon_for_label
        self.format_duration = format_duration
        self.csv_header_written = False
        self.txt_fh: TextIO | None = None
        self.csv_fh: TextIO | None = None
        self.pending_entries = 0

    def append(self, ts: datetime, label: str, duration: float) -> None:
        handles = self.ensure_handles()
        if handles is None:
            return
        txt_fh, csv_fh = handles

        icon = self.icon_for_label(label)
        duration_text = self.format_duration(duration)
        round_part = f" [{self.round_label}]" if self.round_label else ""
        txt_fh.write(f"[{ts:%H:%M:%S}]{round_part} {icon} {label} ({duration_text})\n")

        writer = csv.writer(csv_fh)
        writer.writerow(
            [
                ts.isoformat(timespec="seconds"),
                self.round_label,
                label,
                f"{duration:.3f}",
            ]
        )

        self.pending_entries += 1
        if self.pending_entries >= _ACTIVITY_LOG_FLUSH_EVERY:
            self.flush()

    def ensure_handles(self) -> tuple[TextIO, TextIO] | None:
        if self.log_dir is None:
            return None

        self.log_dir.mkdir(parents=True, exist_ok=True)
        txt_path = self.log_dir / _ACTIVITY_LOG_TXT_FILE
        if self.txt_fh is None or self.txt_fh.closed:
            self.txt_fh = txt_path.open("a", encoding="utf-8")

        csv_path = self.log_dir / _ACTIVITY_LOG_CSV_FILE
        if self.csv_fh is None or self.csv_fh.closed:
            write_header = False
            if not self.csv_header_written:
                write_header = not csv_path.exists() or csv_path.stat().st_size == 0
                self.csv_header_written = True
            self.csv_fh = csv_path.open("a", encoding="utf-8", newline="")
            if write_header:
                csv.writer(self.csv_fh).writerow(_ACTIVITY_LOG_CSV_HEADER.split(","))
        return self.txt_fh, self.csv_fh

    def flush(self) -> None:
        for handle in (self.txt_fh, self.csv_fh):
            if handle is not None and not handle.closed:
                handle.flush()
        self.pending_entries = 0

    def close(self) -> None:
        self.flush()
        for attr in ("txt_fh", "csv_fh"):
            handle = getattr(self, attr)
            if handle is not None and not handle.closed:
                handle.close()
            setattr(self, attr, None)
