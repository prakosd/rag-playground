"""Final and per-round output orchestration."""

from __future__ import annotations

from pathlib import Path

from crawl4md.config import CrawlResult
from crawl4md.sorter import ContentSorter
from crawl4md.writer import FileWriter, PageIndexEntry, PageSidecar, rename_files_with_total

__all__ = ["FinalOutputWriter"]

_FINAL_DIR_NAME = "final"
_INITIAL_DIR_NAME = "initial"
_ROUND_DIR_PREFIX = "round_"


def round_dir_name(round_num: int) -> str:
    """Map a 1-based round number to its on-disk folder name.

    Round 1 is the initial crawl ("initial"); each later round is a retry,
    labelled from the user's perspective as round_1.. (so ``max_retries`` retries
    yield ``initial`` + ``round_1``..``round_N`` + ``final``).
    """
    return _INITIAL_DIR_NAME if round_num <= 1 else f"{_ROUND_DIR_PREFIX}{round_num - 1}"


def round_num_from_dir(name: str) -> int | None:
    """Reverse of :func:`round_dir_name`; return None for non-round folders."""
    if name == _INITIAL_DIR_NAME:
        return 1
    if name.startswith(_ROUND_DIR_PREFIX):
        try:
            return int(name[len(_ROUND_DIR_PREFIX) :]) + 1
        except ValueError:
            return None
    return None


_SUCCESS_SUFFIX = "success_"
_FAIL_SUFFIX = "fail_"
_SUCCESS_URLS_FILE = "success_urls.txt"
_FAIL_URLS_FILE = "fail_urls.txt"
_SORTED_SUCCESS_URLS_FILE = "sorted_success_urls.txt"
_SORTED_FAIL_URLS_FILE = "sorted_fail_urls.txt"
# When True (default), three classes of intermediate files are removed after final
# sorted output is written:
#   1. Per-round sorted files  (round_N/sorted_*) — superseded by final/sorted_*
#   2. Unsorted final content  (final/success_content_*, final/fail_content_*) — superseded by sorted
#   3. Sidecar JSONL files     (round_N/*_pages.jsonl) — no longer needed once sorted files exist
# Set to False to keep every intermediate file on disk (useful for debugging).
_CLEANUP_INTERMEDIATE_FILES = True
_ENABLE_SORTED_ROUND_FILES = not _CLEANUP_INTERMEDIATE_FILES
_SORTED_SUCCESS_PREFIX = "sorted_success_"
_SORTED_FAIL_PREFIX = "sorted_fail_"
_SUCCESS_SIDECAR_SUFFIX = "success_pages.jsonl"
_FAIL_SIDECAR_SUFFIX = "fail_pages.jsonl"


class FinalOutputWriter:
    """Write round snapshots and final files from page sidecars."""

    def __init__(
        self,
        *,
        output_dir: Path,
        output_extension: str,
        max_file_size_mb: float,
        run_metadata: dict[str, object],
    ) -> None:
        self.output_dir = output_dir
        self.output_extension = output_extension
        self.max_file_size_mb = max_file_size_mb
        self.run_metadata = run_metadata

    def save_url_lists(
        self, success: list[CrawlResult], fail: list[CrawlResult], path: Path
    ) -> None:
        if success:
            (path / _SUCCESS_URLS_FILE).write_text(
                "\n".join(result.url for result in success), encoding="utf-8"
            )
        if fail:
            (path / _FAIL_URLS_FILE).write_text(
                "\n".join(result.url for result in fail), encoding="utf-8"
            )

    def write_round_success_files(self, round_num: int, round_dir: Path) -> None:
        pattern = f"{_SUCCESS_SUFFIX}content_*{self.output_extension}"
        for existing in round_dir.glob(pattern):
            existing.unlink()

        entries = self.index_success(round_num)
        if entries:
            self.stream_entries_to_writer(entries, prefix=_SUCCESS_SUFFIX, output_dir=round_dir)

    def write_sorted_round_files(self, round_num: int, round_dir: Path) -> None:
        if not _ENABLE_SORTED_ROUND_FILES:
            return

        success_entries = ContentSorter.sort_keys(self.index_success(round_num))
        if success_entries:
            for file_path in round_dir.glob(
                f"{_SORTED_SUCCESS_PREFIX}content_*{self.output_extension}"
            ):
                file_path.unlink()
            self.stream_entries_to_writer(
                success_entries, prefix=_SORTED_SUCCESS_PREFIX, output_dir=round_dir
            )
            path = round_dir / _SORTED_SUCCESS_URLS_FILE
            path.write_text("\n".join(entry.url for entry in success_entries), encoding="utf-8")

        fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX
        fail_seen: set[str] = set()
        fail_entries: list[PageIndexEntry] = []
        for entry in PageSidecar.iter_index(fail_sidecar):
            if entry.url not in fail_seen:
                fail_seen.add(entry.url)
                fail_entries.append(entry)
        fail_entries = ContentSorter.sort_keys(fail_entries)
        if fail_entries:
            self.stream_entries_to_writer(
                fail_entries, prefix=_SORTED_FAIL_PREFIX, output_dir=round_dir
            )
            path = round_dir / _SORTED_FAIL_URLS_FILE
            path.write_text("\n".join(entry.url for entry in fail_entries), encoding="utf-8")

    def clear_final_content_files(self, *, sorted_files: bool) -> None:
        final_dir = self.output_dir / _FINAL_DIR_NAME
        if not final_dir.exists():
            return
        prefixes = (
            (_SORTED_SUCCESS_PREFIX, _SORTED_FAIL_PREFIX)
            if sorted_files
            else (_SUCCESS_SUFFIX, _FAIL_SUFFIX)
        )
        for prefix in prefixes:
            for file_path in final_dir.glob(f"{prefix}content_*{self.output_extension}"):
                if file_path.is_file():
                    file_path.unlink()

    def saved_results_from_sidecars(self) -> tuple[list[CrawlResult], list[CrawlResult]]:
        success_results = [
            CrawlResult(url=entry.url, html="", markdown="", success=True)
            for entry in self.index_success()
        ]
        fail_results = [
            CrawlResult(url=entry.url, html="", markdown="", success=False)
            for entry in self.index_fail()
        ]
        return success_results, fail_results

    @staticmethod
    def write_url_file(path: Path, urls: list[str]) -> None:
        if urls:
            path.write_text("\n".join(urls), encoding="utf-8")
            return
        path.unlink(missing_ok=True)

    def write_final_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
        *,
        write_content: bool,
    ) -> None:
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_dir.mkdir(parents=True, exist_ok=True)
        self.clear_final_content_files(sorted_files=False)

        unique_urls: list[str] = []
        if all_success:
            seen: set[str] = set()
            for result in all_success:
                if result.url not in seen:
                    seen.add(result.url)
                    unique_urls.append(result.url)
        self.write_url_file(final_dir / _SUCCESS_URLS_FILE, unique_urls)

        remaining_fail_urls = [result.url for result in all_fail]
        unique_fail = list(dict.fromkeys(remaining_fail_urls))
        self.write_url_file(final_dir / _FAIL_URLS_FILE, unique_fail)

        # When cleanup is on (the default), write_sorted_files immediately writes
        # the sorted content and deletes this unsorted copy — so skip writing it
        # to avoid a redundant full pass over every page at finalization (lower
        # peak CPU/memory and transient disk). With cleanup off (debug), keep it.
        if write_content and not _CLEANUP_INTERMEDIATE_FILES:
            success_entries = self.index_success()
            if success_entries:
                self.stream_entries_to_writer(
                    success_entries, prefix=_SUCCESS_SUFFIX, output_dir=final_dir
                )

            fail_entries = self.index_fail()
            if fail_entries:
                self.stream_entries_to_writer(
                    fail_entries, prefix=_FAIL_SUFFIX, output_dir=final_dir
                )

    def delete_sidecars(self) -> None:
        """Delete per-round JSONL sidecar files after final output is written."""
        for pattern in (_SUCCESS_SIDECAR_SUFFIX, _FAIL_SIDECAR_SUFFIX):
            for sidecar in self._round_sidecars(pattern):
                sidecar.unlink(missing_ok=True)

    def _round_sidecars(self, suffix: str) -> list[Path]:
        """Return all round sidecars (initial + retries) sorted by round order."""
        sidecars = [
            d / suffix
            for d in self.output_dir.iterdir()
            if d.is_dir() and round_num_from_dir(d.name) is not None and (d / suffix).exists()
        ]
        return sorted(sidecars, key=lambda p: round_num_from_dir(p.parent.name) or 0)

    def write_sorted_files(self) -> None:
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_dir.mkdir(parents=True, exist_ok=True)
        self.clear_final_content_files(sorted_files=True)

        success_entries = ContentSorter.sort_keys(self.index_success())
        self.write_url_file(
            final_dir / _SORTED_SUCCESS_URLS_FILE,
            [entry.url for entry in success_entries],
        )
        if success_entries:
            files = self.stream_entries_to_writer(
                success_entries, prefix=_SORTED_SUCCESS_PREFIX, output_dir=final_dir
            )
            rename_files_with_total(files)

        fail_entries = ContentSorter.sort_keys(self.index_fail())
        self.write_url_file(
            final_dir / _SORTED_FAIL_URLS_FILE,
            [entry.url for entry in fail_entries],
        )
        if fail_entries:
            files = self.stream_entries_to_writer(
                fail_entries, prefix=_SORTED_FAIL_PREFIX, output_dir=final_dir
            )
            rename_files_with_total(files)

        if _CLEANUP_INTERMEDIATE_FILES:
            self.clear_final_content_files(sorted_files=False)
            self.delete_sidecars()

    def get_final_content_files(self) -> list[Path]:
        final_dir = self.output_dir / _FINAL_DIR_NAME
        pattern = f"{_SORTED_SUCCESS_PREFIX}content_*{self.output_extension}"
        return sorted(final_dir.glob(pattern)) if final_dir.exists() else []

    def index_success(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        sidecar_files = self._round_sidecars(_SUCCESS_SIDECAR_SUFFIX)
        seen: set[str] = set()
        entries: list[PageIndexEntry] = []
        for sidecar_file in sidecar_files:
            if up_to_round is not None:
                round_num = round_num_from_dir(sidecar_file.parent.name)
                if round_num is None or round_num > up_to_round:
                    continue
            for entry in PageSidecar.iter_index(sidecar_file):
                if entry.url not in seen:
                    seen.add(entry.url)
                    entries.append(entry)
        return entries

    def index_fail(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        success_urls: set[str] = set()
        for sidecar_file in self._round_sidecars(_SUCCESS_SIDECAR_SUFFIX):
            for entry in PageSidecar.iter_index(sidecar_file):
                success_urls.add(entry.url)

        sidecar_files = self._round_sidecars(_FAIL_SIDECAR_SUFFIX)
        seen: set[str] = set()
        entries: list[PageIndexEntry] = []
        for sidecar_file in sidecar_files:
            if up_to_round is not None:
                round_num = round_num_from_dir(sidecar_file.parent.name)
                if round_num is None or round_num > up_to_round:
                    continue
            for entry in PageSidecar.iter_index(sidecar_file):
                if entry.url not in seen and entry.url not in success_urls:
                    seen.add(entry.url)
                    entries.append(entry)
        return entries

    def stream_entries_to_writer(
        self,
        entries: list[PageIndexEntry],
        prefix: str,
        output_dir: Path | None = None,
    ) -> list[Path]:
        target_dir = output_dir if output_dir is not None else self.output_dir
        writer = FileWriter(
            output_dir=target_dir,
            max_file_size_mb=self.max_file_size_mb,
            file_extension=self.output_extension,
            prefix=prefix,
            run_metadata=self.run_metadata,
        )
        for entry in entries:
            page = PageSidecar.read_page_at(
                entry.sidecar_path, entry.byte_offset, entry.byte_length
            )
            writer.add(page)
        return writer.flush()
