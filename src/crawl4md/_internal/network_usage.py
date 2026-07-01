"""Proxy / fallback-API usage logging for crawl cost tracking.

Proxies and the fallback scraping API are paid resources. To help a user track
what a crawl may have cost, the crawler records one CSV row per URL attempted in
a round that enabled a paid resource (see ``SiteCrawler._paid_resource_rounds``).
Only those rounds are logged, so the file directly reflects potential spend.

Proxy credentials are never written here — only the neutral method label
(``proxy`` / ``api``) is recorded.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["NETWORK_USAGE_FILE", "NetworkUsageRecorder"]

NETWORK_USAGE_FILE = "network_usage.csv"
_NETWORK_USAGE_HEADER = ("timestamp", "round", "method", "url", "status", "size_kb")


class NetworkUsageRecorder:
    """Append per-URL proxy/fallback-API usage rows to a CSV for cost tracking."""

    def __init__(self) -> None:
        self.path: Path | None = None

    def reset(self, log_dir: Path) -> None:
        """Point the recorder at ``<log_dir>/network_usage.csv`` for a new crawl."""
        self.path = log_dir / NETWORK_USAGE_FILE

    def record(
        self,
        *,
        method: str,
        round_num: int,
        url: str,
        status: str,
        size_kb: float | None,
    ) -> None:
        """Append one usage row; writes the CSV header when the file is new."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        size_text = "" if size_kb is None else f"{size_kb:.2f}"
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if write_header:
                writer.writerow(_NETWORK_USAGE_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    round_num,
                    method,
                    url,
                    status,
                    size_text,
                ]
            )
