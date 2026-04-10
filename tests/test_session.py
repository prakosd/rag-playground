"""Tests for session save/resume — config models, file writing, loading, and resume flow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from crawl4md.config import (
    CrawlerConfig,
    ExtractedPage,
    PageConfig,
    RoundRecord,
    SessionComplete,
    SessionHeader,
)
from crawl4md.crawler import (
    _SESSION_CHECKPOINT_FILE,
    _SESSION_FILE,
    SiteCrawler,
)
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter, PageSidecar
from tests.conftest import _make_mock_result

# ------------------------------------------------------------------
# Phase 1: Model tests
# ------------------------------------------------------------------


class TestSessionModels:
    def test_session_header_roundtrip(self):
        header = SessionHeader(
            crawler_config={"urls": ["https://example.com"]},
            page_config={"extract_main_content": True},
            output_dir="2026-03-09_23-32-29",
            created_at="2026-03-09T23:32:29+00:00",
        )
        json_str = header.model_dump_json()
        restored = SessionHeader.model_validate_json(json_str)
        assert restored.version == 1
        assert restored.type == "header"
        assert restored.crawler_config["urls"] == ["https://example.com"]

    def test_round_record_roundtrip(self):
        record = RoundRecord(
            round_num=1,
            all_generated=["https://example.com/a", "https://example.com/b"],
            url_depths={"https://example.com/a": 1, "https://example.com/b": 2},
            succeeded_urls=["https://example.com/a"],
            failed_urls=["https://example.com/b"],
            timestamp="2026-03-09T23:33:15+00:00",
        )
        json_str = record.model_dump_json()
        restored = RoundRecord.model_validate_json(json_str)
        assert restored.round_num == 1
        assert restored.type == "round"
        assert len(restored.all_generated) == 2

    def test_session_complete_roundtrip(self):
        complete = SessionComplete(
            total_succeeded=5,
            total_failed=1,
            timestamp="2026-03-09T23:34:02+00:00",
        )
        json_str = complete.model_dump_json()
        restored = SessionComplete.model_validate_json(json_str)
        assert restored.type == "complete"
        assert restored.total_succeeded == 5


# ------------------------------------------------------------------
# Phase 2/3: Session file writing and loading tests
# ------------------------------------------------------------------


def _write_session_file(
    session_dir: Path,
    urls: list[str] | None = None,
    rounds: list[RoundRecord] | None = None,
    complete: bool = False,
) -> None:
    """Helper: write a session.jsonl for testing."""
    session_dir.mkdir(parents=True, exist_ok=True)
    header = SessionHeader(
        crawler_config=CrawlerConfig(urls=urls or ["https://example.com"]).model_dump(),
        page_config=PageConfig().model_dump(),
        output_dir=session_dir.name,
        created_at="2026-03-09T23:32:29+00:00",
    )
    path = session_dir / _SESSION_FILE
    with path.open("w", encoding="utf-8") as fh:
        fh.write(header.model_dump_json() + "\n")
        if rounds:
            for r in rounds:
                fh.write(r.model_dump_json() + "\n")
        if complete:
            fh.write(
                SessionComplete(
                    total_succeeded=2,
                    total_failed=0,
                    timestamp="2026-03-09T23:34:02+00:00",
                ).model_dump_json()
                + "\n"
            )


def _make_round_record(
    round_num: int = 1,
    all_generated: list[str] | None = None,
    url_depths: dict[str, int] | None = None,
    succeeded_urls: list[str] | None = None,
    failed_urls: list[str] | None = None,
    timestamp: str = "2026-03-09T23:33:15+00:00",
) -> RoundRecord:
    return RoundRecord(
        round_num=round_num,
        all_generated=all_generated or ["https://example.com/a"],
        url_depths=url_depths or {"https://example.com/a": 1},
        succeeded_urls=succeeded_urls or ["https://example.com/a"],
        failed_urls=failed_urls or [],
        timestamp=timestamp,
    )


class TestSessionFileWriting:
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_session_file_created_on_crawl(self, mock_crawler_cls, tmp_path: Path):
        """A crawl produces session.jsonl with header + round + complete."""
        ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok content")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok"], limit=1, max_retries=2, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        session_path = crawler.output_dir / _SESSION_FILE
        assert session_path.exists()

        lines = [
            json.loads(line)
            for line in session_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        assert lines[0]["type"] == "header"
        assert lines[1]["type"] == "round"
        assert lines[1]["round_num"] == 1
        # Complete sentinel present since all succeeded
        assert lines[-1]["type"] == "complete"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_session_round_record_state(self, mock_crawler_cls, tmp_path: Path):
        """Round record contains correct URL state after crawl."""
        ok_result = _make_mock_result("https://example.com/a", "<p>a</p>", "content a")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a"], limit=1, max_retries=2, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        session_path = crawler.output_dir / _SESSION_FILE
        lines = [
            json.loads(line)
            for line in session_path.read_text(encoding="utf-8").strip().split("\n")
        ]
        round_rec = lines[1]
        assert round_rec["type"] == "round"
        assert "https://example.com/a" in round_rec["succeeded_urls"]
        assert len(round_rec["failed_urls"]) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_session_checkpoint_deleted_after_round(self, mock_crawler_cls, tmp_path: Path):
        """Checkpoint file is removed after a round completes."""
        ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok content")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok"], limit=1, max_retries=2, flush_interval=1
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        assert crawler.output_dir is not None
        checkpoint = crawler.output_dir / _SESSION_CHECKPOINT_FILE
        assert not checkpoint.exists()


class TestSessionLoading:
    def test_load_session_basic(self, tmp_path: Path):
        """Round-trip: write session → load → verify snapshot."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            succeeded_urls=["https://example.com/a"],
            failed_urls=["https://example.com/b"],
            all_generated=["https://example.com/a", "https://example.com/b"],
        )
        _write_session_file(session_dir, rounds=[record])

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.header.version == 1
        assert snapshot.last_round.round_num == 1
        assert "https://example.com/a" in snapshot.succeeded_urls
        assert "https://example.com/b" in snapshot.failed_urls
        assert not snapshot.is_complete

    def test_load_session_uses_last_round(self, tmp_path: Path):
        """With 3 round records, the last one is used."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        rounds = [
            _make_round_record(round_num=1, timestamp="2026-03-09T23:33:00+00:00"),
            _make_round_record(round_num=2, timestamp="2026-03-09T23:34:00+00:00"),
            _make_round_record(
                round_num=3,
                succeeded_urls=["https://example.com/a", "https://example.com/c"],
                timestamp="2026-03-09T23:35:00+00:00",
            ),
        ]
        _write_session_file(session_dir, rounds=rounds)

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.last_round.round_num == 3

    def test_load_session_prefers_checkpoint_when_newer(self, tmp_path: Path):
        """Checkpoint with newer timestamp is used over JSONL round record."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(round_num=1, timestamp="2026-03-09T23:33:00+00:00")
        _write_session_file(session_dir, rounds=[record])

        # Write a newer checkpoint (mid-round 2)
        cp_record = _make_round_record(
            round_num=2,
            all_generated=[
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            ],
            succeeded_urls=["https://example.com/a", "https://example.com/b"],
            failed_urls=["https://example.com/c"],
            timestamp="2026-03-09T23:35:00+00:00",
        )
        cp_path = session_dir / _SESSION_CHECKPOINT_FILE
        cp_path.write_text(cp_record.model_dump_json(), encoding="utf-8")

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.last_round.round_num == 2
        assert len(snapshot.succeeded_urls) == 2

    def test_load_session_ignores_checkpoint_when_stale(self, tmp_path: Path):
        """Checkpoint older than last JSONL record is ignored."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(round_num=2, timestamp="2026-03-09T23:35:00+00:00")
        _write_session_file(session_dir, rounds=[record])

        # Stale checkpoint (older timestamp)
        cp_record = _make_round_record(
            round_num=1,
            timestamp="2026-03-09T23:33:00+00:00",
        )
        cp_path = session_dir / _SESSION_CHECKPOINT_FILE
        cp_path.write_text(cp_record.model_dump_json(), encoding="utf-8")

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.last_round.round_num == 2

    def test_load_session_missing_file(self, tmp_path: Path):
        """FileNotFoundError when session.jsonl is missing."""
        with pytest.raises(FileNotFoundError, match="No session file"):
            SiteCrawler._load_session(tmp_path / "nonexistent")

    def test_load_session_corrupt_last_line(self, tmp_path: Path):
        """Gracefully uses previous valid round when last line is corrupt."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(round_num=1)
        _write_session_file(session_dir, rounds=[record])

        # Append corrupt line
        session_path = session_dir / _SESSION_FILE
        with session_path.open("a", encoding="utf-8") as fh:
            fh.write("{invalid json\n")

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.last_round.round_num == 1

    def test_load_session_complete_status(self, tmp_path: Path):
        """Complete sentinel is detected."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(round_num=1)
        _write_session_file(session_dir, rounds=[record], complete=True)

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.is_complete is True

    def test_load_session_incomplete_status(self, tmp_path: Path):
        """Without complete sentinel, is_complete is False."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(round_num=1)
        _write_session_file(session_dir, rounds=[record], complete=False)

        snapshot = SiteCrawler._load_session(session_dir)
        assert snapshot.is_complete is False


# ------------------------------------------------------------------
# Phase 4: Resume flow tests
# ------------------------------------------------------------------


class TestResumeFlow:
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_resume_restores_state(self, mock_crawler_cls, tmp_path: Path):
        """Resumed crawl only targets failed + new URLs."""
        ok_result = _make_mock_result("https://example.com/b", "<p>b</p>", "content b")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        # Set up a session with one failed URL
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            all_generated=["https://example.com/a", "https://example.com/b"],
            url_depths={"https://example.com/a": 1, "https://example.com/b": 1},
            succeeded_urls=["https://example.com/a"],
            failed_urls=["https://example.com/b"],
        )
        _write_session_file(
            session_dir,
            urls=["https://example.com/a", "https://example.com/b"],
            rounds=[record],
        )
        # Write success sidecar for round 1 (existing content)
        sidecar_path = session_dir / "round_1_success_pages.jsonl"
        PageSidecar.append(
            ExtractedPage(url="https://example.com/a", title="A", markdown="# A\n\ncontent a"),
            sidecar_path,
        )

        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=2,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )

        crawler.resume(session_dir)

        # The resumed crawl should have re-crawled only the failed URL
        assert crawler.output_dir == session_dir
        crawled_urls = [call.kwargs["url"] for call in mock_instance.arun.call_args_list]
        assert "https://example.com/b" in crawled_urls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_resume_with_new_urls(self, mock_crawler_cls, tmp_path: Path):
        """New seed URLs are added to the resume queue."""
        ok_result = _make_mock_result("https://example.com/new", "<p>new</p>", "new content")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            all_generated=["https://example.com/a"],
            succeeded_urls=["https://example.com/a"],
            failed_urls=[],
        )
        _write_session_file(session_dir, urls=["https://example.com/a"], rounds=[record])
        # Write sidecar
        sidecar_path = session_dir / "round_1_success_pages.jsonl"
        PageSidecar.append(
            ExtractedPage(url="https://example.com/a", title="A", markdown="# A\n\ncontent"),
            sidecar_path,
        )

        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/new"],
            limit=10,
            max_retries=2,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )

        crawler.resume(session_dir)
        crawled_urls = [call.kwargs["url"] for call in mock_instance.arun.call_args_list]
        assert "https://example.com/new" in crawled_urls

    def test_resume_by_index(self, tmp_path: Path):
        """resume(1) resolves the correct directory via list_sessions."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            succeeded_urls=["https://example.com/a"],
            failed_urls=[],
        )
        _write_session_file(session_dir, rounds=[record])

        config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=2)
        crawler = SiteCrawler(config, output_base=tmp_path)

        # resume(1) should find the session — will print "Nothing to resume"
        # since all URLs already succeeded and no new ones added
        results = crawler.resume(1)
        assert results == []

    def test_resume_extension_mismatch_warning(self, tmp_path: Path):
        """UserWarning emitted when output extension differs."""
        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            succeeded_urls=["https://example.com/a"],
            failed_urls=[],
        )
        _write_session_file(session_dir, rounds=[record])

        config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=2)
        page_config = PageConfig(output_extension=".md")
        crawler = SiteCrawler(config, page_config, output_base=tmp_path)

        with pytest.warns(UserWarning, match="Output extension changed"):
            crawler.resume(session_dir)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_resume_skips_succeeded_urls(self, mock_crawler_cls, tmp_path: Path):
        """Succeeded URLs are not re-crawled on resume."""
        ok_result = _make_mock_result("https://example.com/b", "<p>b</p>", "content b")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            all_generated=["https://example.com/a", "https://example.com/b"],
            url_depths={"https://example.com/a": 1, "https://example.com/b": 1},
            succeeded_urls=["https://example.com/a"],
            failed_urls=["https://example.com/b"],
        )
        _write_session_file(session_dir, rounds=[record])
        # Write sidecar
        sidecar_path = session_dir / "round_1_success_pages.jsonl"
        PageSidecar.append(
            ExtractedPage(url="https://example.com/a", title="A", markdown="# A\n\ncontent a"),
            sidecar_path,
        )

        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=2,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.resume(session_dir)

        crawled_urls = [call.kwargs["url"] for call in mock_instance.arun.call_args_list]
        # /a was already succeeded — should not be re-crawled
        assert "https://example.com/a" not in crawled_urls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_resume_fail_sidecar_excludes_succeeded_urls(self, mock_crawler_cls, tmp_path: Path):
        """URL that failed in round 1 but succeeds on resume is excluded from final fail."""
        ok_result = _make_mock_result("https://example.com/b", "<p>b</p>", "content b")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        session_dir = tmp_path / "2026-03-09_23-32-29"
        record = _make_round_record(
            round_num=1,
            all_generated=["https://example.com/a", "https://example.com/b"],
            url_depths={"https://example.com/a": 1, "https://example.com/b": 1},
            succeeded_urls=["https://example.com/a"],
            failed_urls=["https://example.com/b"],
        )
        _write_session_file(session_dir, rounds=[record])

        # Pre-populate sidecars from round 1
        sidecar_path = session_dir / "round_1_success_pages.jsonl"
        PageSidecar.append(
            ExtractedPage(url="https://example.com/a", title="A", markdown="# A\n\ncontent a"),
            sidecar_path,
        )
        fail_sidecar = session_dir / "round_1_fail_pages.jsonl"
        PageSidecar.append(
            ExtractedPage(
                url="https://example.com/b",
                title="FAILED — timeout",
                markdown="**Error:** timeout",
            ),
            fail_sidecar,
        )

        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=2,
            flush_interval=1,
        )
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.resume(session_dir)

        # Check that sorted_final_fail doesn't contain /b (it succeeded on resume)
        fail_files = list(session_dir.glob("sorted_final_fail_content_*"))
        if fail_files:
            content = fail_files[0].read_text(encoding="utf-8")
            assert "https://example.com/b" not in content


# ------------------------------------------------------------------
# Phase 5: Session listing tests
# ------------------------------------------------------------------


class TestListSessions:
    def test_list_sessions_multiple(self, tmp_path: Path, capsys):
        """Multiple sessions are listed in descending order."""
        for name in ["2026-03-07_00-45-05", "2026-03-08_14-06-21", "2026-03-09_23-32-29"]:
            d = tmp_path / name
            record = _make_round_record(round_num=1, timestamp=f"{name[:10]}T{name[11:]}+00:00")
            _write_session_file(d, rounds=[record])

        result = SiteCrawler.list_sessions(tmp_path)
        assert len(result) == 3
        # Descending by last-saved
        assert result[0][1].name == "2026-03-09_23-32-29"
        assert result[2][1].name == "2026-03-07_00-45-05"

        out = capsys.readouterr().out
        assert "#" in out
        assert "Pages" in out

    def test_list_sessions_empty(self, tmp_path: Path, capsys):
        """Clean message when no sessions exist."""
        result = SiteCrawler.list_sessions(tmp_path)
        assert result == []
        out = capsys.readouterr().out
        assert "No sessions found" in out

    def test_list_sessions_ignores_dirs_without_session_file(self, tmp_path: Path, capsys):
        """Old directories without session.jsonl are skipped."""
        (tmp_path / "2026-03-07_00-45-05").mkdir()  # No session file
        d = tmp_path / "2026-03-08_14-06-21"
        record = _make_round_record(round_num=1)
        _write_session_file(d, rounds=[record])

        result = SiteCrawler.list_sessions(tmp_path)
        assert len(result) == 1
        assert result[0][1].name == "2026-03-08_14-06-21"
