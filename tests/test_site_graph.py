"""Tests for site graph recording helpers."""

from __future__ import annotations

import json
from pathlib import Path

from crawl4md._internal.site_graph import (
    _PAGE_STATUS_DISCOVERED,
    _PAGE_STATUS_FAIL,
    _PAGE_STATUS_SUCCESS,
    SiteGraphRecorder,
)
from crawl4md.config import CrawlResult, ExtractedPage


def test_record_discovered_adds_first_seen_record() -> None:
    recorder = SiteGraphRecorder()

    recorder.record_discovered(
        normalized_url="https://example.com/a",
        url="https://example.com/a",
        discovered_from="https://example.com",
        crawl_depth=2,
    )

    assert recorder.records["https://example.com/a"] == {
        "url": "https://example.com/a",
        "discovered_from": "https://example.com",
        "page_size_kb": None,
        "status": _PAGE_STATUS_DISCOVERED,
        "depth": 1,
        "round_num": None,
    }


def test_upsert_record_preserves_existing_parent_and_depth() -> None:
    recorder = SiteGraphRecorder()
    recorder.upsert_record(
        normalized_url="https://example.com/a",
        url="https://example.com/a",
        discovered_from="https://example.com",
        status=_PAGE_STATUS_DISCOVERED,
        page_size_kb=None,
        graph_depth=1,
        round_num=None,
    )

    recorder.upsert_record(
        normalized_url="https://example.com/a",
        url="https://example.com/a",
        discovered_from="https://other.example.com",
        status=_PAGE_STATUS_SUCCESS,
        page_size_kb=1.0,
        graph_depth=4,
        round_num=2,
    )

    record = recorder.records["https://example.com/a"]
    assert record["discovered_from"] == "https://example.com"
    assert record["depth"] == 1
    assert record["status"] == _PAGE_STATUS_SUCCESS


def test_move_record_for_redirect_keeps_source_record_data() -> None:
    recorder = SiteGraphRecorder()
    recorder.record_discovered(
        normalized_url="https://example.com/a",
        url="https://example.com/a",
        discovered_from="https://example.com",
        crawl_depth=2,
    )

    recorder.move_record_for_redirect(
        source_normalized_url="https://example.com/a",
        target_normalized_url="https://example.com/b",
        target_url="https://example.com/b",
    )

    assert "https://example.com/a" not in recorder.records
    assert recorder.records["https://example.com/b"]["url"] == "https://example.com/b"
    assert recorder.records["https://example.com/b"]["depth"] == 1


def test_record_terminal_computes_success_size() -> None:
    recorder = SiteGraphRecorder()
    page = ExtractedPage(
        url="https://example.com/a",
        title="A",
        markdown="content",
    )

    recorder.record_terminal(
        source_url="https://example.com/a",
        crawl_result=CrawlResult(url="https://example.com/a", markdown="content", success=True),
        page=page,
        round_num=3,
        crawl_depth=2,
        strip_www=True,
    )

    record = recorder.records["https://example.com/a"]
    assert record["status"] == _PAGE_STATUS_SUCCESS
    assert record["page_size_kb"] == round(len(b"content") / 1024, 2)
    assert record["round_num"] == 3


def test_record_terminal_marks_fail_without_size() -> None:
    recorder = SiteGraphRecorder()

    recorder.record_terminal(
        source_url="https://example.com/a",
        crawl_result=CrawlResult(url="https://example.com/a", markdown="content", success=False),
        page=None,
        round_num=1,
        crawl_depth=1,
        strip_www=True,
    )

    record = recorder.records["https://example.com/a"]
    assert record["status"] == _PAGE_STATUS_FAIL
    assert record["page_size_kb"] is None


def test_flush_writes_sorted_jsonl(tmp_path: Path) -> None:
    recorder = SiteGraphRecorder()
    recorder.reset(tmp_path)
    recorder.upsert_record(
        normalized_url="https://example.com/b",
        url="https://example.com/b",
        discovered_from=None,
        status=_PAGE_STATUS_SUCCESS,
        page_size_kb=1.0,
        graph_depth=0,
        round_num=1,
    )
    recorder.upsert_record(
        normalized_url="https://example.com/a",
        url="https://example.com/a",
        discovered_from=None,
        status=_PAGE_STATUS_SUCCESS,
        page_size_kb=1.0,
        graph_depth=0,
        round_num=1,
    )

    recorder.flush()

    assert recorder.dirty is False
    lines = (tmp_path / "site_graph.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["url"] for line in lines] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
