"""Site graph recording for crawl runs."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

from crawl4md._internal.url_filter import normalize_url
from crawl4md.config import CrawlResult, ExtractedPage

__all__ = ["SiteGraphRecorder"]

_SITE_GRAPH_FILE = "site_graph.jsonl"
_PAGES_REGISTRY_TMP_SUFFIX = ".tmp"
_PAGE_RECORD_URL = "url"
_PAGE_RECORD_DISCOVERED_FROM = "discovered_from"
_PAGE_RECORD_PAGE_SIZE_KB = "page_size_kb"
_PAGE_RECORD_STATUS = "status"
_PAGE_RECORD_DEPTH = "depth"
_PAGE_RECORD_ROUND_NUM = "round_num"
_PAGE_SIZE_DECIMAL_PLACES = 2
_PAGE_STATUS_DISCOVERED = "discovered"
_PAGE_STATUS_SUCCESS = "success"
_PAGE_STATUS_FAIL = "fail"
_PAGE_STATUS_SKIPPED = "skipped"


class SiteGraphRecorder:
    """Track discovered and terminal page records for a crawl run."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.records: dict[str, dict[str, object]] = {}
        self.dirty = False

    def reset(self, output_dir: Path) -> None:
        self.path = output_dir / _SITE_GRAPH_FILE
        self.records = {}
        self.dirty = False

    @staticmethod
    def graph_depth(crawl_depth: int) -> int:
        return max(crawl_depth - 1, 0)

    def record_discovered(
        self,
        *,
        normalized_url: str,
        url: str,
        discovered_from: str | None,
        crawl_depth: int,
    ) -> None:
        if normalized_url in self.records:
            return
        self.upsert_record(
            normalized_url=normalized_url,
            url=url,
            discovered_from=discovered_from,
            status=_PAGE_STATUS_DISCOVERED,
            page_size_kb=None,
            graph_depth=self.graph_depth(crawl_depth),
            round_num=None,
        )

    def upsert_record(
        self,
        *,
        normalized_url: str,
        url: str,
        discovered_from: str | None,
        status: str,
        page_size_kb: float | None,
        graph_depth: int,
        round_num: int | None,
    ) -> None:
        existing = self.records.get(normalized_url, {})
        parent = existing.get(_PAGE_RECORD_DISCOVERED_FROM, discovered_from)
        depth = existing.get(_PAGE_RECORD_DEPTH, graph_depth)
        self.records[normalized_url] = {
            _PAGE_RECORD_URL: url,
            _PAGE_RECORD_DISCOVERED_FROM: parent,
            _PAGE_RECORD_PAGE_SIZE_KB: page_size_kb,
            _PAGE_RECORD_STATUS: status,
            _PAGE_RECORD_DEPTH: depth,
            _PAGE_RECORD_ROUND_NUM: round_num,
        }
        self.dirty = True

    def remove_record(self, normalized_url: str, *, statuses: set[str] | None = None) -> None:
        existing = self.records.get(normalized_url)
        if existing is None:
            return
        if statuses is not None and existing.get(_PAGE_RECORD_STATUS) not in statuses:
            return
        del self.records[normalized_url]
        self.dirty = True

    def move_record_for_redirect(
        self,
        *,
        source_normalized_url: str,
        target_normalized_url: str,
        target_url: str,
    ) -> None:
        if source_normalized_url == target_normalized_url:
            return
        source_record = self.records.pop(source_normalized_url, None)
        if source_record is None:
            return
        if target_normalized_url in self.records:
            self.dirty = True
            return
        source_record[_PAGE_RECORD_URL] = target_url
        self.records[target_normalized_url] = source_record
        self.dirty = True

    def record_terminal(
        self,
        *,
        source_url: str,
        crawl_result: CrawlResult,
        page: ExtractedPage | None,
        round_num: int,
        crawl_depth: int,
        strip_www: bool,
    ) -> None:
        normalized_source = normalize_url(source_url, strip_www=strip_www)
        normalized_result = normalize_url(crawl_result.url, strip_www=strip_www)
        self.move_record_for_redirect(
            source_normalized_url=normalized_source,
            target_normalized_url=normalized_result,
            target_url=crawl_result.url,
        )
        existing = self.records.get(normalized_result, {})
        parent_value = existing.get(_PAGE_RECORD_DISCOVERED_FROM)
        discovered_from = parent_value if isinstance(parent_value, str) else None
        depth_value = existing.get(_PAGE_RECORD_DEPTH)
        graph_depth = depth_value if isinstance(depth_value, int) else self.graph_depth(crawl_depth)
        markdown = page.markdown if page is not None else crawl_result.markdown
        page_size_kb = (
            round(len(markdown.encode("utf-8")) / 1024, _PAGE_SIZE_DECIMAL_PLACES)
            if crawl_result.success and markdown.strip()
            else None
        )
        self.upsert_record(
            normalized_url=normalized_result,
            url=crawl_result.url,
            discovered_from=discovered_from,
            status=_PAGE_STATUS_SUCCESS if crawl_result.success else _PAGE_STATUS_FAIL,
            page_size_kb=page_size_kb,
            graph_depth=graph_depth,
            round_num=round_num,
        )

    def flush(self) -> None:
        if not self.dirty or self.path is None:
            return
        temp_path = self.path.with_name(f"{self.path.name}{_PAGES_REGISTRY_TMP_SUFFIX}")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records = sorted(
                self.records.values(), key=lambda record: str(record[_PAGE_RECORD_URL])
            )
            with temp_path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False))
                    handle.write("\n")
            temp_path.replace(self.path)
            self.dirty = False
        except Exception as exc:  # noqa: BLE001 - registry is best-effort output.
            temp_path.unlink(missing_ok=True)
            warnings.warn(
                f"Could not write {_SITE_GRAPH_FILE}: {type(exc).__name__}: {exc}",
                stacklevel=2,
            )
