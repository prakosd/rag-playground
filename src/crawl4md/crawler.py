"""SiteCrawler — synchronous wrapper around Crawl4AI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import random
import re
import sys
import warnings
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import httpx
import nest_asyncio
import pymupdf
import pymupdf4llm
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from crawl4md.config import (
    _FALLBACK_WAIT_UNTIL,
    CrawlerConfig,
    CrawlResult,
    ExtractedPage,
    PageConfig,
)
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.sorter import ContentSorter
from crawl4md.writer import FileWriter, PageIndexEntry, PageSidecar, rename_files_with_total

# Allow asyncio.run() inside Jupyter's already-running event loop
nest_asyncio.apply()

# Seconds to pause between retry rounds so the WAF can cool down
_ROUND_COOLDOWN = 30

# ------------------------------------------------------------------
# Jitter constants — all tunable values in one place
# ------------------------------------------------------------------

# Per-page jitter multiplier ranges (applied to config.delay)
_JITTER_ROUND1_MIN = 0.1  # Round 1: light delay to avoid WAF triggers
_JITTER_ROUND1_MAX = 1.0
_JITTER_RETRY_MIN = 0.3  # Retry rounds: heavier delay for WAF cooldown
_JITTER_RETRY_MAX = 3.0

# WAF back-off: sleep after detecting a block (applied even when delay=0)
_WAF_BACKOFF_MIN = 2.0  # Multiplier lower bound (applied to config.delay)
_WAF_BACKOFF_MAX = 5.0  # Multiplier upper bound
_WAF_BACKOFF_FLOOR = 3.0  # Minimum seconds (ensures a pause even when delay=0)
_WAF_BACKOFF_CAP = 15.0  # Maximum seconds (ceiling for escalated back-off)
_WAF_CONSECUTIVE_THRESHOLD = 3  # Consecutive blocks before escalating

# Round cooldown jitter multiplier range
_ROUND_COOLDOWN_JITTER_MIN = 0.8
_ROUND_COOLDOWN_JITTER_MAX = 1.5


# Known WAF / bot-protection block signatures (matched case-insensitively)
_BLOCK_SIGNATURES = (
    "incapsula incident",
    "access denied</title>",
    "attention required! | cloudflare",
    "please turn javascript on and reload the page",
    "checking your browser before accessing",
    "javascript is required",
)

# If the extracted markdown exceeds this length (in characters), the page
# contains real content and should not be classified as a WAF block even
# when a block signature is present in the raw HTML.
_BLOCK_MAX_CONTENT_LENGTH = 500

# ------------------------------------------------------------------
# Content-length measurement: tags stripped before counting visible text
# ------------------------------------------------------------------
_CHROME_STRIP_TAGS = ["nav", "script", "style", "form", "header", "footer", "noscript"]

# ------------------------------------------------------------------
# Browser configuration defaults
# ------------------------------------------------------------------

# User-agent generation settings used when stealth mode is enabled
_USER_AGENT_MODE = "random"
_USER_AGENT_PLATFORMS = ["desktop"]
_USER_AGENT_BROWSERS = ["Chrome", "Edge"]

# ------------------------------------------------------------------
# Output directory and file naming
# ------------------------------------------------------------------

# Subdirectory name for final merged output files
_FINAL_DIR_NAME = "final"

# Prefix for per-round subdirectory names (e.g. "round_1")
_ROUND_DIR_PREFIX = "round_"
_SESSION_DIR_PREFIX = "session_"

# Suffix for successful-page file names (e.g. "success_content_001.txt")
_SUCCESS_SUFFIX = "success_"
# Suffix for failed-page file names (e.g. "fail_content_001.txt")
_FAIL_SUFFIX = "fail_"

# Final URL list filenames.
_SUCCESS_URLS_FILE = "success_urls.txt"
_FAIL_URLS_FILE = "fail_urls.txt"
_SORTED_SUCCESS_URLS_FILE = "sorted_success_urls.txt"
_SORTED_FAIL_URLS_FILE = "sorted_fail_urls.txt"

# ------------------------------------------------------------------
# Round file naming components
# ------------------------------------------------------------------

# Set to False to skip per-round sorted file generation (saves extraction time)
_ENABLE_SORTED_ROUND_FILES = True

# Prefix for sorted output files within a round or final folder
_SORTED_SUCCESS_PREFIX = "sorted_success_"
_SORTED_FAIL_PREFIX = "sorted_fail_"

# ------------------------------------------------------------------
# JSONL sidecar file naming (memory-efficient extracted-page storage)
# ------------------------------------------------------------------

# Suffix for per-round sidecar files that store extracted success pages as JSONL
_SUCCESS_SIDECAR_SUFFIX = "success_pages.jsonl"
# Suffix for per-round sidecar files that store extracted fail pages as JSONL
_FAIL_SIDECAR_SUFFIX = "fail_pages.jsonl"

# ------------------------------------------------------------------
# Link extraction patterns
# ------------------------------------------------------------------

# Regex to extract href attribute values from HTML anchor tags
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']')
# Regex to detect template placeholders (${var}, {{var}}, {%var%})
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\$\{|%7B%7B|\{\{|\{%")
# Valid URL scheme prefixes for discovered links
_URL_SCHEMES = ("http://", "https://")

# ------------------------------------------------------------------
# Timestamp format
# ------------------------------------------------------------------

# strftime format for timestamped output directory names
_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

# ------------------------------------------------------------------
# Failed-page content templates
# ------------------------------------------------------------------

# Title prefix for pages that failed to crawl
_FAILED_TITLE_PREFIX = "FAILED \u2014"
# Fallback error message when the actual error is None
_UNKNOWN_ERROR_MSG = "Unknown error"
# Markdown label for the error description section
_ERROR_SECTION_HEADER = "**Error:**"
# Markdown label for the raw response section
_RAW_RESPONSE_HEADER = "**Raw response:**"

# ------------------------------------------------------------------
# PDF handling constants
# ------------------------------------------------------------------

# File extension used to detect PDF URLs by path
_PDF_EXTENSION = ".pdf"
# Content-Type prefix returned by servers for PDF responses
_PDF_CONTENT_TYPE = "application/pdf"
# Timeout (seconds) for httpx PDF downloads and HEAD requests
_PDF_DOWNLOAD_TIMEOUT = 60
# When a crawled page yields fewer characters than this and is not a WAF
# block, a HEAD request is issued to check whether the URL is actually a PDF.
_PDF_FALLBACK_THRESHOLD = 50

# ------------------------------------------------------------------
# Skip / empty-extraction log labels
# ------------------------------------------------------------------

# Error message assigned when extraction produces empty markdown
_EMPTY_EXTRACTION_ERROR = "No extractable content"

# ------------------------------------------------------------------
# Redirect storm detection
# ------------------------------------------------------------------

# Consecutive redirects to the same already-visited target before
# treating subsequent ones as failures (suspected anti-bot redirect).
_REDIRECT_STORM_THRESHOLD = 3
# Error message for pages caught in a redirect storm
_REDIRECT_STORM_ERROR = "Suspected anti-bot redirect"
# Error message for redirect-skipped pages that never triggered a storm
# (queue ended or pattern broke before threshold was reached)
_UNRESOLVED_REDIRECT_ERROR = "Redirect to already-visited URL (unresolved)"
# Warning emitted once when Tesseract is not installed and OCR is requested
_OCR_UNAVAILABLE_WARNING = (
    "Tesseract OCR is not installed — scanned/image-only PDFs will not be "
    "extracted. Install Tesseract and the required language packs for OCR "
    "support, or set ocr_languages=[] to silence this warning."
)

# Maximum character length for shortened URLs displayed in activity labels
_SHORT_URL_MAX_LEN = 60

# Seconds between cancellation checks during long sleeps.
_CANCEL_POLL_INTERVAL = 0.2

# Progress event names emitted for optional UI integrations.
_PROGRESS_EVENT_COMPLETED = "crawl_completed"
_PROGRESS_EVENT_DISCOVERED = "urls_discovered"
_PROGRESS_EVENT_INTERRUPTED = "crawl_interrupted"
_PROGRESS_EVENT_PAGE = "page_processed"
_PROGRESS_EVENT_STARTED = "crawl_started"


def _shorten_url(url: str) -> str:
    """Shorten a URL for display, keeping domain + trailing path segments."""
    if len(url) <= _SHORT_URL_MAX_LEN:
        return url
    # Strip scheme
    display = re.sub(r"^https?://", "", url)
    if len(display) <= _SHORT_URL_MAX_LEN:
        return display
    # Keep first 25 chars (domain) + … + last 30 chars (path tail)
    return display[:25] + "…" + display[-(_SHORT_URL_MAX_LEN - 26) :]


class SiteCrawler:
    """Crawls websites and collects HTML/Markdown content.

    Provides a synchronous ``crawl()`` method that wraps Crawl4AI's
    asynchronous crawler so non-technical users never see ``async``/``await``.
    """

    def __init__(
        self,
        config: CrawlerConfig,
        page_config: PageConfig | None = None,
        *,
        output_base: Path | str | None = None,
        extractor: ContentExtractor | None = None,
        writer: FileWriter | None = None,
        activity_log_size: int = 10,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config
        self.page_config = page_config or PageConfig()
        self._output_base = Path(output_base) if output_base else Path.cwd()
        self.output_dir: Path | None = None
        self._allowed_domains: set[str] = self._extract_base_domains(
            config.urls, strip_www=config.strip_www
        )
        self._extractor = extractor
        self._writer = writer
        self._activity_log_size = activity_log_size
        self._progress_callback = progress_callback
        self._should_cancel = should_cancel
        self.content_files: list[Path] = []
        # Tracks whether the OCR-unavailable warning has already been emitted
        self._ocr_warned: bool = False
        # Internal writer for failed-page content (symmetrical with _writer)
        self._fail_writer: FileWriter | None = None
        if writer is not None:
            self._fail_writer = FileWriter(
                max_file_size_mb=self.page_config.max_file_size_mb,
                file_extension=writer._file_extension,
            )
        # Per-round JSONL sidecar paths for memory-efficient final file
        # generation.  Set by _run_rounds_async before each round.
        self._success_sidecar: Path | None = None
        self._fail_sidecar: Path | None = None
        self._run_metadata: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self) -> list[CrawlResult]:
        """Crawl the configured URLs and return results.

        Creates a timestamped output folder.  Runs multiple rounds:
        round 1 crawls seed URLs; subsequent rounds retry blocked/failed
        URLs up to ``max_retries`` times.  Each round writes per-round
        files (``round_N_*``).  After all rounds, final merged files
        are produced (``final_success_content_*.ext``,
        ``final_success_urls.txt``, ``final_fail_urls.txt``).

        Extracted content is persisted to per-round JSONL sidecar files
        during the crawl so that heavy ``html`` and ``markdown`` fields
        can be freed from memory.  The returned ``CrawlResult`` objects
        retain only lightweight metadata (``url``, ``success``, ``error``);
        ``html`` and ``markdown`` are empty strings.
        """
        self.output_dir = self._create_output_dir()
        self._run_metadata = self._build_run_metadata()
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_STARTED,
                "output_dir": str(self.output_dir),
                "limit": self.config.limit,
            }
        )
        # Attach output_dir to writer so incremental flushes land there
        if self._writer is not None:
            self._writer._output_dir = self.output_dir
            self._writer.set_run_metadata(self._run_metadata)
        if self._fail_writer is not None:
            self._fail_writer._output_dir = self.output_dir
            self._fail_writer.set_run_metadata(self._run_metadata)
        try:
            if sys.platform == "win32":
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    all_results = pool.submit(self._run_rounds_in_proactor_loop).result()
            else:
                all_results = asyncio.run(self._run_rounds_async())
        except KeyboardInterrupt:
            # _run_rounds_async already flushed and wrote final files;
            # this catches any residual interrupt from asyncio teardown.
            all_results = []
        return all_results

    def print_summary(self, results: list[CrawlResult]) -> None:
        """Print a human-readable summary of crawl results and output files."""
        if self.output_dir is None or not self.output_dir.exists():
            print("No output folder found. Did you run crawl() first?")
            return

        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        print(f"Results: {success_count} succeeded, {fail_count} failed")
        print(f"Output folder: {self.output_dir}\n")

        def _print_files(label: str, paths: list[Path]) -> None:
            if not paths:
                return
            print(f"  {label}:")
            for f in paths:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"    {f.name} ({size_mb:.2f} MB)")
            print()

        # --- Per-round files ---
        round_nums = sorted(
            {
                int(m.group(1))
                for d in self.output_dir.iterdir()
                if d.is_dir() and (m := re.match(r"round_(\d+)$", d.name))
            }
        )
        for rn in round_nums:
            rd = self.output_dir / f"{_ROUND_DIR_PREFIX}{rn}"
            content = sorted(rd.glob(f"{_SUCCESS_SUFFIX}content_*"))
            fail_content = sorted(rd.glob(f"{_FAIL_SUFFIX}content_*"))
            url_files = sorted(rd.glob("*urls*.txt"))
            print(f"--- Round {rn} ---")
            _print_files("Success content", content)
            _print_files("Fail content", fail_content)
            _print_files("URL lists", url_files)

            sorted_content = sorted(rd.glob(f"{_SORTED_SUCCESS_PREFIX}content_*"))
            sorted_fail_content = sorted(rd.glob(f"{_SORTED_FAIL_PREFIX}content_*"))
            sorted_url_files = sorted(rd.glob("sorted_*urls*.txt"))
            if sorted_content or sorted_fail_content:
                print(f"--- Round {rn} (sorted) ---")
                _print_files("Success content", sorted_content)
                _print_files("Fail content", sorted_fail_content)
                _print_files("URL lists", sorted_url_files)

        # --- Final folder ---
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_success = (
            sorted(final_dir.glob(f"{_SUCCESS_SUFFIX}content_*")) if final_dir.exists() else []
        )
        final_fail = (
            sorted(final_dir.glob(f"{_FAIL_SUFFIX}content_*")) if final_dir.exists() else []
        )
        if final_success or final_fail:
            print("--- Final (unsorted, merged across rounds) ---")
            _print_files("Success content", final_success)
            _print_files("Fail content", final_fail)

        # --- Sorted files in final/ (primary output) ---
        sorted_success = (
            sorted(final_dir.glob(f"{_SORTED_SUCCESS_PREFIX}content_*"))
            if final_dir.exists()
            else []
        )
        sorted_fail = (
            sorted(final_dir.glob(f"{_SORTED_FAIL_PREFIX}content_*")) if final_dir.exists() else []
        )
        all_urls = sorted(final_dir.glob("*urls*.txt")) if final_dir.exists() else []
        if sorted_success or sorted_fail:
            print("--- Sorted by URL path (primary output) ---")
            _print_files("Success content", sorted_success)
            _print_files("Fail content", sorted_fail)
            _print_files("URL lists", all_urls)

        if fail_count > 0:
            print(
                f"See final/sorted_fail_urls.txt for the "
                f"{fail_count} URL(s) that could not be crawled."
            )

    def _round_dir(self, round_num: int) -> Path:
        """Return the round subdirectory for *round_num*, creating it if needed."""
        assert self.output_dir is not None
        d = self.output_dir / f"{_ROUND_DIR_PREFIX}{round_num}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_rounds_in_proactor_loop(self) -> list[CrawlResult]:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._run_rounds_async())
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # Round orchestration
    # ------------------------------------------------------------------

    async def _run_rounds_async(self) -> list[CrawlResult]:
        """Run the initial crawl + retry rounds, producing per-round and final files."""
        all_success: list[CrawlResult] = []
        all_fail: list[CrawlResult] = []
        succeeded_urls: set[str] = set()
        all_generated: set[str] = set()
        url_depths: dict[str, int] = {}
        total_rounds = 1 + self.config.max_retries

        browser_kwargs: dict = {
            "headless": True,
            "enable_stealth": self.config.stealth,
        }
        if self.config.stealth:
            browser_kwargs["user_agent_mode"] = _USER_AGENT_MODE
            browser_kwargs["user_agent_generator_config"] = {
                "platforms": list(_USER_AGENT_PLATFORMS),
                "browsers": list(_USER_AGENT_BROWSERS),
            }
        if self.config.headers:
            browser_kwargs["headers"] = dict(self.config.headers)
        browser_cfg = BrowserConfig(**browser_kwargs)
        run_cfg = self._build_run_config(CrawlerRunConfig)
        fallback_run_cfg = self._build_fallback_run_config(CrawlerRunConfig)

        # --- Round 1: full crawl with link discovery ---
        # Use a single browser instance across all rounds so that
        # cookies (including WAF challenge tokens) persist through retries.
        interrupted = False
        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                round_dir = self._round_dir(1)
                if self._writer is not None:
                    self._writer._output_dir = round_dir
                    self._writer.reset(_SUCCESS_SUFFIX)
                if self._fail_writer is not None:
                    self._fail_writer._output_dir = round_dir
                    self._fail_writer.reset(_FAIL_SUFFIX)
                self._success_sidecar = round_dir / _SUCCESS_SIDECAR_SUFFIX
                self._fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX
                print(
                    f"--- Round 1/{total_rounds}: Crawling {len(self.config.urls)} seed URL(s) ---"
                )
                round_results = await self._crawl_urls_async(
                    urls=self.config.urls,
                    crawler=crawler,
                    run_cfg=run_cfg,
                    discover_links=True,
                    round_dir=round_dir,
                    prior_success=0,
                    prior_fail=0,
                    round_label="First pass" if total_rounds > 1 else "",
                    all_generated=all_generated,
                    url_depths=url_depths,
                )
                success, fail = self._split_results(round_results)
                if self._writer is not None:
                    self._writer.flush()
                if self._fail_writer is not None:
                    self._fail_writer.flush()
                all_success.extend(success)
                succeeded_urls.update(r.url for r in success)
                all_fail.extend(fail)
                self._save_url_lists(all_success, fail, round_dir)
                self._write_round_success_files(1, round_dir)
                self._write_sorted_round_files(1, round_dir)

                failed_urls = [r.url for r in all_fail]

                for round_num in range(2, total_rounds + 1):
                    self._raise_if_cancelled()
                    if not failed_urls:
                        print("\nAll pages succeeded — skipping remaining retries.")
                        break

                    round_dir = self._round_dir(round_num)
                    if self._writer is not None:
                        self._writer._output_dir = round_dir
                        self._writer.reset(_SUCCESS_SUFFIX)
                    if self._fail_writer is not None:
                        self._fail_writer._output_dir = round_dir
                        self._fail_writer.reset(_FAIL_SUFFIX)
                    self._success_sidecar = round_dir / _SUCCESS_SIDECAR_SUFFIX
                    self._fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX

                    cooldown = _ROUND_COOLDOWN * random.uniform(
                        _ROUND_COOLDOWN_JITTER_MIN, _ROUND_COOLDOWN_JITTER_MAX
                    )
                    print(
                        f"\n--- Round {round_num}/{total_rounds}: Retrying "
                        f"{len(failed_urls)} failed URL(s) "
                        f"(waiting {cooldown:.0f}s cooldown) ---"
                    )
                    await self._sleep_with_cancel(cooldown)

                    round_results = await self._crawl_urls_async(
                        urls=failed_urls,
                        crawler=crawler,
                        run_cfg=fallback_run_cfg,
                        discover_links=True,
                        is_retry=True,
                        round_dir=round_dir,
                        prior_success=len(all_success),
                        prior_fail=len(all_fail),
                        skip_urls=frozenset(succeeded_urls),
                        round_label=f"Retry {round_num - 1} of {total_rounds - 1}",
                        all_generated=all_generated,
                        url_depths=url_depths,
                    )
                    success, fail = self._split_results(round_results)
                    if self._writer is not None:
                        self._writer.flush()
                    if self._fail_writer is not None:
                        self._fail_writer.flush()
                    # Deduplicate: only add genuinely new successes
                    new_success = [r for r in success if r.url not in succeeded_urls]
                    all_success.extend(new_success)
                    succeeded_urls.update(r.url for r in new_success)
                    # Remove newly-succeeded URLs from all_fail; add new failures (skip dupes)
                    new_success_urls = {r.url for r in new_success}
                    all_fail = [r for r in all_fail if r.url not in new_success_urls]
                    existing_fail_urls = {r.url for r in all_fail}
                    all_fail.extend(r for r in fail if r.url not in existing_fail_urls)
                    failed_urls = [r.url for r in fail]
                    self._save_url_lists(all_success, fail, round_dir)
                    self._write_round_success_files(round_num, round_dir)
                    self._write_sorted_round_files(round_num, round_dir)

        except (KeyboardInterrupt, asyncio.CancelledError):
            interrupted = True
            print("\n\nCrawl stopped! Writing final files...")
            saved_success, saved_fail = self._saved_results_from_sidecars()
            if saved_success or saved_fail:
                all_success = saved_success
                all_fail = saved_fail
                succeeded_urls = {result.url for result in all_success}
            self._emit_progress(
                {
                    "event": _PROGRESS_EVENT_INTERRUPTED,
                    "output_dir": str(self.output_dir) if self.output_dir else "",
                    "successful_pages": len(all_success),
                    "failed_pages": len(all_fail),
                    "processed_pages": len(all_success) + len(all_fail),
                    "limit": self.config.limit,
                }
            )

        # --- Flush any remaining buffered content ---
        if self._writer is not None:
            self._writer.flush()
        if self._fail_writer is not None:
            self._fail_writer.flush()

        # --- Final merged files (unsorted) ---
        self._write_final_files(all_success, all_fail)

        # --- Sorted final files (grouped by URL path) ---
        self._write_sorted_files(all_success, all_fail)
        self.content_files = self._get_final_content_files()

        total_crawled = len(all_success) + len(all_fail)
        label = "Interrupted" if interrupted else "Done"
        # Clear any lingering progress widget from the final round so the
        # summary text below isn't shown beneath a stale (partial-percent)
        # bar in Jupyter / Colab.
        try:
            from IPython import get_ipython  # type: ignore[import-untyped]

            if get_ipython() is not None:
                from IPython.display import clear_output  # type: ignore[import-untyped]

                clear_output(wait=True)
        except ImportError:
            pass
        print(
            f"\n{label}! {len(all_success)} succeeded, {len(all_fail)} failed out of {total_crawled} total."
        )
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_COMPLETED,
                "output_dir": str(self.output_dir) if self.output_dir else "",
                "successful_pages": len(all_success),
                "failed_pages": len(all_fail),
                "processed_pages": total_crawled,
                "limit": self.config.limit,
            }
        )
        if self.output_dir is not None:
            print(f"Output folder: {self.output_dir}")

        # Return all results (success + remaining failures) for API consumers
        return all_success + all_fail

    def _emit_progress(self, event: Mapping[str, object]) -> None:
        """Send a progress event to an optional UI integration."""
        if self._progress_callback is None:
            return
        self._progress_callback(event)

    def _emit_page_progress(
        self,
        results: list[CrawlResult],
        *,
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        current_url: str,
    ) -> None:
        """Emit a compact page-progress event."""
        success_count = sum(1 for result in results if result.success)
        fail_count = len(results) - success_count
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_PAGE,
                "processed_pages": prior_success + prior_fail + len(results),
                "successful_pages": prior_success + success_count,
                "failed_pages": prior_fail + fail_count,
                "queued_discovered_urls": len(generated),
                "current_url": current_url,
                "output_dir": str(self.output_dir) if self.output_dir else "",
                "limit": self.config.limit,
            }
        )

    def _cancel_requested(self) -> bool:
        return bool(self._should_cancel is not None and self._should_cancel())

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested():
            raise asyncio.CancelledError

    async def _sleep_with_cancel(self, seconds: float) -> None:
        """Sleep in short chunks so cooperative cancellation stays responsive."""
        if self._should_cancel is None:
            await asyncio.sleep(seconds)
            return
        remaining = seconds
        while remaining > 0:
            self._raise_if_cancelled()
            interval = min(_CANCEL_POLL_INTERVAL, remaining)
            await asyncio.sleep(interval)
            remaining -= interval
        self._raise_if_cancelled()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _crawl_urls_async(
        self,
        urls: list[str],
        crawler: AsyncWebCrawler,
        run_cfg: object,
        *,
        discover_links: bool = True,
        is_retry: bool = False,
        round_dir: Path | None = None,
        prior_success: int = 0,
        prior_fail: int = 0,
        skip_urls: frozenset[str] = frozenset(),
        round_label: str = "",
        all_generated: set[str] | None = None,
        url_depths: dict[str, int] | None = None,
    ) -> list[CrawlResult]:
        """Crawl a list of URLs and return per-page results.

        When *discover_links* is True, follow links up to ``max_depth``.
        When False, only crawl the given URLs with no link discovery.

        *skip_urls* contains URLs already successfully crawled in prior
        rounds — they are pre-loaded into the visited set so they will
        not be crawled again (including as redirect targets).

        *all_generated* and *url_depths* are shared mutable collections
        that persist across rounds.  ``all_generated`` tracks every URL
        ever queued (for dedup and limit enforcement); ``url_depths``
        maps each URL to its crawl depth so retried pages and their
        discovered links use the correct depth.
        """
        results: list[CrawlResult] = []
        _sw = self.config.strip_www
        visited: set[str] = set(self._normalize_url(u, strip_www=_sw) for u in skip_urls)
        generated: set[str] = all_generated if all_generated is not None else set()
        depths: dict[str, int] = url_depths if url_depths is not None else {}
        queue: list[tuple[str, int]] = []
        for seed_url in urls:
            norm_seed = self._normalize_url(seed_url, strip_www=_sw)
            if norm_seed not in generated:
                if len(generated) >= self.config.limit:
                    break
                if not self._url_allowed(seed_url):
                    continue
            generated.add(norm_seed)
            queue.append((seed_url, depths.get(norm_seed, 1)))
        progress = ProgressReporter(
            max(len(queue), 1),
            prior_success=prior_success,
            prior_fail=prior_fail,
            round_label=round_label,
            max_log_entries=self._activity_log_size,
            log_dir=self.output_dir,
        )
        discovery_limit_reached = len(generated) >= self.config.limit

        consecutive_blocks = 0
        # Redirect storm tracking: count consecutive redirects to the
        # same already-visited target.  Once the threshold is reached,
        # subsequent pages are treated as failures instead of silent
        # skips so they enter the retry pipeline.
        consecutive_redirect_target: str | None = None
        consecutive_redirect_count: int = 0
        skipped_redirect_urls: list[str] = []

        def _flush_skipped_redirects(error: str) -> None:
            """Convert accumulated skipped-redirect URLs into failures.

            A single redirect to an already-visited URL is normal
            navigation (e.g. /old → /new).  Only flush when two or more
            URLs have been skipped, which indicates a suspicious pattern.
            """
            if len(skipped_redirect_urls) < 2:
                for skipped_url in skipped_redirect_urls:
                    generated.discard(self._normalize_url(skipped_url, strip_www=_sw))
                if skipped_redirect_urls:
                    progress.total = max(len(generated), 1)
                    self._emit_progress(
                        {
                            "event": _PROGRESS_EVENT_DISCOVERED,
                            "queued_discovered_urls": len(generated),
                            "current_url": skipped_redirect_urls[0],
                            "limit": self.config.limit,
                        }
                    )
                skipped_redirect_urls.clear()
                return
            for skipped_url in skipped_redirect_urls:
                results.append(
                    CrawlResult(
                        url=skipped_url,
                        html="",
                        markdown="",
                        success=False,
                        error=error,
                    )
                )
                progress.update(skipped_url, success=False)
            skipped_redirect_urls.clear()

        while queue:
            self._raise_if_cancelled()
            url, depth = queue.pop(0)

            norm_url = self._normalize_url(url, strip_www=_sw)
            if norm_url in visited:
                generated.discard(norm_url)
                progress.total = max(len(generated), 1)
                self._emit_progress(
                    {
                        "event": _PROGRESS_EVENT_DISCOVERED,
                        "queued_discovered_urls": len(generated),
                        "current_url": url,
                        "limit": self.config.limit,
                    }
                )
                continue
            visited.add(norm_url)

            if not self._url_allowed(url):
                continue

            # Fast path: download PDFs directly (bypass the browser).
            if self._is_pdf_url(url):
                progress.set_activity(f"Downloading PDF {_shorten_url(url)}")
                crawl_result = await self._download_pdf(url)
                results.append(crawl_result)
                progress.update(crawl_result.url, success=crawl_result.success)
                self._emit_page_progress(
                    results,
                    generated=generated,
                    prior_success=prior_success,
                    prior_fail=prior_fail,
                    current_url=crawl_result.url,
                )

                if crawl_result.success and self._extractor and self._writer:
                    _ocr_tag = " (OCR)" if self.page_config.ocr_languages else ""
                    progress.set_activity(f"Saving PDF content{_ocr_tag}")
                    page = self._extractor._extract_page(crawl_result)
                    if page.markdown.strip():
                        self._writer.add(page)
                        if self._success_sidecar is not None:
                            PageSidecar.append(page, self._success_sidecar)
                    else:
                        progress.set_activity(
                            f"No content found on {_shorten_url(crawl_result.url)}"
                        )
                        crawl_result.success = False
                        crawl_result.error = _EMPTY_EXTRACTION_ERROR
                elif not crawl_result.success and self._fail_writer is not None:
                    fail_page = ExtractedPage(
                        url=crawl_result.url,
                        title=(
                            f"{_FAILED_TITLE_PREFIX} {crawl_result.error or _UNKNOWN_ERROR_MSG}"
                        ),
                        markdown=(
                            f"{_ERROR_SECTION_HEADER} {crawl_result.error or _UNKNOWN_ERROR_MSG}"
                        ),
                    )
                    self._fail_writer.add(fail_page)
                    if self._fail_sidecar is not None:
                        PageSidecar.append(fail_page, self._fail_sidecar)

                # Flush periodically (same cadence as normal pages)
                if len(results) % self.config.flush_interval == 0:
                    if self._writer is not None:
                        self._writer.flush()
                    if self._fail_writer is not None:
                        self._fail_writer.flush()
                    if round_dir is not None:
                        success, fail = self._split_results(results)
                        self._save_url_lists(success, fail, round_dir)

                # Free heavy payload — content is persisted in sidecar / writer
                crawl_result.html = ""
                crawl_result.markdown = ""

                if self.config.delay > 0:
                    jitter = self.config.delay * random.uniform(
                        _JITTER_ROUND1_MIN, _JITTER_ROUND1_MAX
                    )
                    progress.set_activity(f"Pausing to avoid blocks ({jitter:.1f}s)")
                    await self._sleep_with_cancel(jitter)

                continue
            try:
                progress.set_activity(f"Reading page {_shorten_url(url)}")
                result = await crawler.arun(url=url, config=run_cfg)

                # Use the final URL after any redirects
                final_url = getattr(result, "redirected_url", None) or url
                redirected = final_url != url

                norm_final = self._normalize_url(final_url, strip_www=_sw)
                if redirected and norm_final in visited:
                    # Track consecutive same-target redirects
                    if norm_final == consecutive_redirect_target:
                        consecutive_redirect_count += 1
                    else:
                        # Target changed — flush any prior skipped URLs
                        # as unresolved before switching targets.
                        _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)
                        consecutive_redirect_target = norm_final
                        consecutive_redirect_count = 1

                    if consecutive_redirect_count < _REDIRECT_STORM_THRESHOLD:
                        skipped_redirect_urls.append(url)
                        progress.set_activity(f"Skipped {_shorten_url(url)} (already visited)")
                        continue

                    # Storm detected — retroactively fail earlier skipped
                    # pages, then treat the current page as failure too
                    # so the retry pipeline can re-attempt all of them.
                    _flush_skipped_redirects(_REDIRECT_STORM_ERROR)
                    progress.set_activity(
                        f"Possible block detected \u2014 skipping {_shorten_url(url)}"
                    )
                    crawl_result = CrawlResult(
                        url=url,
                        html="",
                        markdown="",
                        success=False,
                        error=_REDIRECT_STORM_ERROR,
                    )
                    results.append(crawl_result)
                    progress.update(url, success=False)

                    # Apply WAF-style back-off
                    backoff = max(
                        _WAF_BACKOFF_FLOOR,
                        self.config.delay * random.uniform(_WAF_BACKOFF_MIN, _WAF_BACKOFF_MAX),
                    )
                    progress.set_activity(f"Website is blocking us \u2014 waiting {backoff:.1f}s")
                    await asyncio.sleep(backoff)
                    continue

                # Non-redirect-skip result — reset storm counter
                consecutive_redirect_target = None
                consecutive_redirect_count = 0

                visited.add(norm_final)
                generated.add(norm_final)
                depths[norm_final] = depth

                if redirected and not self._url_allowed(final_url):
                    # Undo the generated/visited adds above — the redirect target
                    # is outside the filter and neither the original URL nor the
                    # redirect destination should count as discovered.
                    generated.discard(self._normalize_url(url, strip_www=_sw))
                    generated.discard(norm_final)
                    visited.discard(norm_final)
                    self._emit_progress(
                        {
                            "event": _PROGRESS_EVENT_DISCOVERED,
                            "queued_discovered_urls": len(generated),
                            "current_url": url,
                            "limit": self.config.limit,
                        }
                    )
                    progress.set_activity(f"Skipped {_shorten_url(url)} (redirect outside filter)")
                    continue

                error_msg: str | None = None
                if not result.success:
                    raw_err = (
                        getattr(result, "error_message", None)
                        or getattr(result, "error", None)
                        or ""
                    )
                    status = getattr(result, "status_code", None)
                    error_msg = str(raw_err) if raw_err else _UNKNOWN_ERROR_MSG
                    if status is not None:
                        error_msg += f" (HTTP {status})"

                crawl_result = CrawlResult(
                    url=final_url,
                    html=result.html or "",
                    markdown=result.markdown or "",
                    success=result.success,
                    error=error_msg,
                    redirected_url=final_url if redirected else None,
                )
            except Exception as exc:
                crawl_result = CrawlResult(
                    url=url,
                    html="",
                    markdown="",
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )

            # Detect WAF blocks (Incapsula etc. return HTTP 200 with block HTML).
            # Only flag as blocked when the extracted markdown is short —
            # pages with substantial content are not mere challenge pages.
            # We measure content length *after* stripping boilerplate tags
            # (nav, script, form, style) so that navigation chrome doesn't
            # inflate the count and mask a failed JS render.
            raw_markdown = crawl_result.markdown
            waf_blocked = False
            if (
                crawl_result.success
                and self._is_blocked(crawl_result.html)
                and self._content_length_without_chrome(crawl_result.html)
                < _BLOCK_MAX_CONTENT_LENGTH
            ):
                crawl_result.success = False
                crawl_result.error = "Blocked by WAF"
                crawl_result.markdown = ""
                waf_blocked = True

            results.append(crawl_result)
            progress.update(crawl_result.url, success=crawl_result.success)
            self._emit_page_progress(
                results,
                generated=generated,
                prior_success=prior_success,
                prior_fail=prior_fail,
                current_url=crawl_result.url,
            )

            # Extract and buffer content incrementally
            if crawl_result.success and self._extractor and self._writer:
                progress.set_activity("Saving page content")
                page = self._extractor._extract_page(crawl_result)
                # Post-extraction quality gate: if a block signature is
                # present and the *extracted* content is still thin,
                # demote to failure so the URL is retried.
                if (
                    self._is_blocked(crawl_result.html)
                    and len(page.markdown.strip()) < _BLOCK_MAX_CONTENT_LENGTH
                ):
                    crawl_result.success = False
                    crawl_result.error = "Blocked — page returned only boilerplate"
                    crawl_result.markdown = raw_markdown
                    waf_blocked = True
                elif page.markdown.strip():
                    self._writer.add(page)
                    if self._success_sidecar is not None:
                        PageSidecar.append(page, self._success_sidecar)
                else:
                    progress.set_activity(f"No content found on {_shorten_url(crawl_result.url)}")
                    crawl_result.success = False
                    crawl_result.error = _EMPTY_EXTRACTION_ERROR
                    crawl_result.markdown = raw_markdown

            # PDF fallback: when a page returns very little content and is
            # not a WAF block, check whether the URL actually serves a PDF.
            # This catches dynamic URLs (e.g. /download?id=123) that return
            # PDF content without a .pdf extension.
            if (
                crawl_result.success
                and not waf_blocked
                and not crawl_result.is_pdf
                and len(crawl_result.markdown.strip()) < _PDF_FALLBACK_THRESHOLD
                and self._content_length_without_chrome(crawl_result.html) < _PDF_FALLBACK_THRESHOLD
            ):
                is_pdf = await self._is_pdf_response(
                    url, dict(self.config.headers) if self.config.headers else None
                )
                if is_pdf:
                    progress.set_activity(f"Re-downloading as PDF {_shorten_url(url)}")
                    pdf_result = await self._download_pdf(url)
                    # Replace the original result in the list
                    results[-1] = pdf_result
                    crawl_result = pdf_result
                    if pdf_result.success and self._extractor and self._writer:
                        _ocr_tag = " (OCR)" if self.page_config.ocr_languages else ""
                        progress.set_activity(f"Saving PDF content{_ocr_tag}")
                        page = self._extractor._extract_page(pdf_result)
                        if page.markdown.strip():
                            self._writer.add(page)
                            if self._success_sidecar is not None:
                                PageSidecar.append(page, self._success_sidecar)
                        else:
                            progress.set_activity(
                                f"No content found on {_shorten_url(pdf_result.url)}"
                            )
                            pdf_result.success = False
                            pdf_result.error = _EMPTY_EXTRACTION_ERROR

            # WAF back-off: pause after a block so the WAF can cool down.
            # Applies even when delay=0 (floor ensures a minimum pause).
            if waf_blocked:
                consecutive_blocks += 1
                if consecutive_blocks >= _WAF_CONSECUTIVE_THRESHOLD:
                    backoff = _WAF_BACKOFF_CAP
                else:
                    backoff = max(
                        _WAF_BACKOFF_FLOOR,
                        self.config.delay * random.uniform(_WAF_BACKOFF_MIN, _WAF_BACKOFF_MAX),
                    )
                progress.set_activity(f"Website is blocking us \u2014 waiting {backoff:.1f}s")
                await self._sleep_with_cancel(backoff)
            else:
                consecutive_blocks = 0

            # A normal result (success or WAF block) breaks any redirect
            # storm streak — flush skipped URLs and reset the counter.
            _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)
            consecutive_redirect_target = None
            consecutive_redirect_count = 0

            # Buffer failed-page content for the fail content file
            if not crawl_result.success and self._fail_writer is not None:
                raw_body = raw_markdown.strip() or crawl_result.html.strip() or "(no response)"
                fail_page = ExtractedPage(
                    url=crawl_result.url,
                    title=f"{_FAILED_TITLE_PREFIX} {crawl_result.error or _UNKNOWN_ERROR_MSG}",
                    markdown=(
                        f"{_ERROR_SECTION_HEADER} {crawl_result.error or _UNKNOWN_ERROR_MSG}\n\n"
                        f"{_RAW_RESPONSE_HEADER}\n\n{raw_body}"
                    ),
                )
                self._fail_writer.add(fail_page)
                if self._fail_sidecar is not None:
                    PageSidecar.append(fail_page, self._fail_sidecar)

            # Flush content and URL lists periodically
            if len(results) % self.config.flush_interval == 0:
                progress.set_activity(f"Writing files ({len(results)} pages)")
                if self._writer is not None:
                    self._writer.flush()
                if self._fail_writer is not None:
                    self._fail_writer.flush()
                if round_dir is not None:
                    success, fail = self._split_results(results)
                    self._save_url_lists(success, fail, round_dir)

            # Throttle between pages — jitter mimics human browsing.
            # Round 1 applies a light delay; retries apply a heavier one.
            # Both require delay > 0 (default 0 keeps current fast behavior).
            if self.config.delay > 0:
                if is_retry:
                    jitter = self.config.delay * random.uniform(
                        _JITTER_RETRY_MIN, _JITTER_RETRY_MAX
                    )
                    progress.set_activity(f"Waiting before retry ({jitter:.1f}s)")
                else:
                    jitter = self.config.delay * random.uniform(
                        _JITTER_ROUND1_MIN, _JITTER_ROUND1_MAX
                    )
                    progress.set_activity(f"Pausing to avoid blocks ({jitter:.1f}s)")
                await self._sleep_with_cancel(jitter)

            # Discover links for deeper crawling
            if (
                discover_links
                and depth < self.config.max_depth
                and crawl_result.success
                and not discovery_limit_reached
            ):
                progress.set_activity(f"Finding more pages on {_shorten_url(url)}")
                new_links = self._extract_links(crawl_result, crawl_result.url, strip_www=_sw)
                added = 0
                for link in new_links:
                    norm_link = self._normalize_url(link, strip_www=_sw)
                    if norm_link in generated:
                        continue
                    if not self._url_allowed(link):
                        continue
                    if is_retry and len(generated) >= self.config.limit:
                        break
                    generated.add(norm_link)
                    depths[norm_link] = depth + 1
                    queue.append((link, depth + 1))
                    added += 1
                progress.update_activity_label(f"Found {added} new pages on {_shorten_url(url)}")
                self._emit_progress(
                    {
                        "event": _PROGRESS_EVENT_DISCOVERED,
                        "queued_discovered_urls": len(generated),
                        "current_url": url,
                        "limit": self.config.limit,
                    }
                )
                if len(generated) >= self.config.limit:
                    discovery_limit_reached = True
                # Update progress total to reflect discovered pages
                progress.total = max(len(generated), 1)

            # Free heavy payload — content is persisted in sidecar / writer
            crawl_result.html = ""
            crawl_result.markdown = ""

        # Flush any remaining skipped-redirect URLs as failures so they
        # appear in the fail list for manual review.
        _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)

        # Flush the last open activity so it appears in the disk log.
        progress._close_activity()

        # Snap the bar to 100%: silently-skipped URLs (e.g. redirects to
        # already-visited targets, redirects outside the include filter)
        # were counted into ``progress.total`` via ``generated`` but never
        # call ``progress.update``, so the bar would otherwise end below
        # 100%.  Sync ``total`` to the actual number processed.
        progress.total = max(progress.count, 1)
        if progress._use_notebook:
            progress._refresh_display()

        return results

    # ------------------------------------------------------------------
    # Block detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Return True if the HTML looks like a WAF/bot-protection block page."""
        if not html:
            return False
        html_lower = html.lower()
        return any(sig in html_lower for sig in _BLOCK_SIGNATURES)

    @staticmethod
    def _content_length_without_chrome(html: str) -> int:
        """Return the visible-text length after stripping boilerplate tags.

        Removes ``<nav>``, ``<script>``, ``<style>``, ``<form>``, ``<header>``,
        ``<footer>``, and ``<noscript>`` so that navigation chrome does not
        inflate the content measurement used by WAF detection.
        """
        if not html:
            return 0
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(_CHROME_STRIP_TAGS):
            tag.decompose()
        return len(soup.get_text(separator=" ", strip=True))

    # ------------------------------------------------------------------
    # PDF handling
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pdf_url(url: str) -> bool:
        """Return True if the URL path ends with ``.pdf`` (case-insensitive)."""
        from urllib.parse import urlparse

        return urlparse(url).path.lower().endswith(_PDF_EXTENSION)

    @staticmethod
    async def _is_pdf_response(url: str, headers: dict[str, str] | None = None) -> bool:
        """Issue a HEAD request and return True if Content-Type is PDF."""
        try:
            async with httpx.AsyncClient(
                headers=headers or {},
                timeout=_PDF_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.head(url)
                content_type = resp.headers.get("content-type", "")
                return content_type.lower().startswith(_PDF_CONTENT_TYPE)
        except httpx.HTTPError:
            return False

    async def _download_pdf(self, url: str) -> CrawlResult:
        """Download a PDF and convert it to Markdown via pymupdf4llm."""
        try:
            async with httpx.AsyncClient(
                headers=dict(self.config.headers) if self.config.headers else {},
                timeout=_PDF_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            doc = pymupdf.open(stream=resp.content, filetype="pdf")
            md = self._pdf_to_markdown(doc)
            doc.close()

            return CrawlResult(
                url=url,
                markdown=md,
                success=True,
                is_pdf=True,
            )
        except Exception as exc:
            return CrawlResult(
                url=url,
                success=False,
                error=f"PDF download failed: {type(exc).__name__}: {exc}",
                is_pdf=True,
            )

    def _pdf_to_markdown(self, doc: pymupdf.Document) -> str:
        """Convert a PyMuPDF document to Markdown, with optional OCR."""
        langs = self.page_config.ocr_languages
        if not langs:
            return pymupdf4llm.to_markdown(doc)

        try:
            return pymupdf4llm.to_markdown(doc, use_ocr=True, ocr_language="+".join(langs))
        except (RuntimeError, FileNotFoundError, TypeError):
            # RuntimeError / FileNotFoundError: Tesseract not installed.
            # TypeError: pymupdf4llm version too old for use_ocr kwarg.
            if not self._ocr_warned:
                self._ocr_warned = True
                warnings.warn(_OCR_UNAVAILABLE_WARNING, stacklevel=3)
            return pymupdf4llm.to_markdown(doc)

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_results(results: list[CrawlResult]) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Split results into (success, fail) lists."""
        success = [r for r in results if r.success]
        fail = [r for r in results if not r.success]
        return success, fail

    def _save_url_lists(
        self,
        success: list[CrawlResult],
        fail: list[CrawlResult],
        dir: Path,
    ) -> None:
        """Write per-round success and fail URL lists to *dir*."""
        if success:
            (dir / _SUCCESS_URLS_FILE).write_text(
                "\n".join(r.url for r in success), encoding="utf-8"
            )
        if fail:
            (dir / _FAIL_URLS_FILE).write_text("\n".join(r.url for r in fail), encoding="utf-8")

    def _write_round_success_files(self, round_num: int, round_dir: Path) -> None:
        """Write cumulative round success content as a round-end snapshot.

        Streams extracted pages from JSONL sidecar files for rounds
        1..N, deduplicating by URL, and writes content files.
        """
        if self._writer is None or self.output_dir is None:
            return

        ext = self.page_config.output_extension
        pattern = f"{_SUCCESS_SUFFIX}content_*{ext}"
        for existing in round_dir.glob(pattern):
            existing.unlink()

        entries = self._index_success(round_num)
        if not entries:
            return

        self._stream_entries_to_writer(entries, prefix=_SUCCESS_SUFFIX, output_dir=round_dir)

    def _write_sorted_round_files(self, round_num: int, round_dir: Path) -> None:
        """Write sorted content and URL files for one round.

        Streams pages from JSONL sidecar files via lightweight indexes:
        the index list is sorted, then each page is loaded one at a
        time and fed to the writer.  Success files are cumulative
        (rounds 1..N); fail files are current round only.  Controlled
        by the ``_ENABLE_SORTED_ROUND_FILES`` module flag.
        """
        if not _ENABLE_SORTED_ROUND_FILES:
            return
        if self._writer is None or self.output_dir is None:
            return
        ext = self.page_config.output_extension

        # --- Sorted success (cumulative, deduplicated) ---
        success_entries = ContentSorter.sort_keys(self._index_success(round_num))
        if success_entries:
            # Remove stale files from prior writes
            for f in round_dir.glob(f"{_SORTED_SUCCESS_PREFIX}content_*{ext}"):
                f.unlink()
            self._stream_entries_to_writer(
                success_entries, prefix=_SORTED_SUCCESS_PREFIX, output_dir=round_dir
            )
            path = round_dir / _SORTED_SUCCESS_URLS_FILE
            path.write_text("\n".join(e.url for e in success_entries), encoding="utf-8")

        # --- Sorted fail (this round only, deduplicated) ---
        fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX
        fail_seen: set[str] = set()
        fail_entries: list[PageIndexEntry] = []
        for entry in PageSidecar.iter_index(fail_sidecar):
            if entry.url not in fail_seen:
                fail_seen.add(entry.url)
                fail_entries.append(entry)
        fail_entries = ContentSorter.sort_keys(fail_entries)
        if fail_entries:
            self._stream_entries_to_writer(
                fail_entries, prefix=_SORTED_FAIL_PREFIX, output_dir=round_dir
            )
            path = round_dir / _SORTED_FAIL_URLS_FILE
            path.write_text("\n".join(e.url for e in fail_entries), encoding="utf-8")

    def _clear_final_content_files(self, *, sorted_files: bool) -> None:
        """Remove stale final content files before regenerating a final view."""
        assert self.output_dir is not None
        final_dir = self.output_dir / _FINAL_DIR_NAME
        if not final_dir.exists():
            return
        extension = self.page_config.output_extension
        prefixes = (
            (_SORTED_SUCCESS_PREFIX, _SORTED_FAIL_PREFIX)
            if sorted_files
            else (_SUCCESS_SUFFIX, _FAIL_SUFFIX)
        )
        for prefix in prefixes:
            for file_path in final_dir.glob(f"{prefix}content_*{extension}"):
                if file_path.is_file():
                    file_path.unlink()

    def _saved_results_from_sidecars(self) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Return lightweight result metadata for every page already persisted."""
        if self.output_dir is None:
            return [], []
        success_results = [
            CrawlResult(url=entry.url, html="", markdown="", success=True)
            for entry in self._index_success()
        ]
        fail_results = [
            CrawlResult(url=entry.url, html="", markdown="", success=False)
            for entry in self._index_fail()
        ]
        return success_results, fail_results

    @staticmethod
    def _write_url_file(path: Path, urls: list[str]) -> None:
        """Write a URL list, or remove a stale list when no URLs remain."""
        if urls:
            path.write_text("\n".join(urls), encoding="utf-8")
            return
        path.unlink(missing_ok=True)

    def _write_final_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Produce final merged URL lists and unsorted content files.

        URL lists are built from the lightweight ``CrawlResult`` metadata
        (only ``.url`` is needed).  Content files are read from the JSONL
        sidecar files written during each round — no re-extraction needed.
        """
        assert self.output_dir is not None
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_dir.mkdir(parents=True, exist_ok=True)
        self._clear_final_content_files(sorted_files=False)

        # success_urls.txt — all successful URLs across all rounds (deduplicated)
        unique_urls: list[str] = []
        if all_success:
            seen: set[str] = set()
            for r in all_success:
                if r.url not in seen:
                    seen.add(r.url)
                    unique_urls.append(r.url)
        self._write_url_file(final_dir / _SUCCESS_URLS_FILE, unique_urls)

        # fail_urls.txt — URLs that still failed after all retries (deduplicated)
        remaining_fail_urls = [r.url for r in all_fail]
        unique_fail = list(dict.fromkeys(remaining_fail_urls))
        self._write_url_file(final_dir / _FAIL_URLS_FILE, unique_fail)

        # success_content_*.ext — unsorted merged content from sidecars
        if self._writer is not None:
            success_entries = self._index_success()
            if success_entries:
                self._stream_entries_to_writer(
                    success_entries, prefix=_SUCCESS_SUFFIX, output_dir=final_dir
                )

        # fail_content_*.ext — unsorted fail content from sidecars
        if self._writer is not None:
            fail_entries = self._index_fail()
            if fail_entries:
                self._stream_entries_to_writer(
                    fail_entries, prefix=_FAIL_SUFFIX, output_dir=final_dir
                )

    def _write_sorted_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Sort by URL path and write sorted final files.

        Streams pages from JSONL sidecar files via lightweight indexes:
        the index list is sorted, then each page is loaded one at a
        time and fed to the writer — the full corpus never lives in
        RAM at once.
        """
        if self._writer is None:
            return
        assert self.output_dir is not None
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_dir.mkdir(parents=True, exist_ok=True)
        self._clear_final_content_files(sorted_files=True)

        # Sorted success content (deduplicated by URL, keeping first occurrence)
        success_entries = ContentSorter.sort_keys(self._index_success())
        self._write_url_file(
            final_dir / _SORTED_SUCCESS_URLS_FILE,
            [entry.url for entry in success_entries],
        )
        if success_entries:
            files = self._stream_entries_to_writer(
                success_entries, prefix=_SORTED_SUCCESS_PREFIX, output_dir=final_dir
            )
            rename_files_with_total(files)

        # Sorted fail content (deduplicated by URL, keeping first occurrence)
        fail_entries = ContentSorter.sort_keys(self._index_fail())
        self._write_url_file(
            final_dir / _SORTED_FAIL_URLS_FILE,
            [entry.url for entry in fail_entries],
        )
        if fail_entries:
            files = self._stream_entries_to_writer(
                fail_entries, prefix=_SORTED_FAIL_PREFIX, output_dir=final_dir
            )
            rename_files_with_total(files)

    def _get_final_content_files(self) -> list[Path]:
        """Return sorted list of final content files."""
        assert self.output_dir is not None
        final_dir = self.output_dir / _FINAL_DIR_NAME
        pattern = f"{_SORTED_SUCCESS_PREFIX}content_*{self.page_config.output_extension}"
        return sorted(final_dir.glob(pattern)) if final_dir.exists() else []

    # ------------------------------------------------------------------
    # Sidecar helpers — build lightweight indexes for streaming sort
    # ------------------------------------------------------------------

    def _index_success(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        """Build a deduplicated success index across rounds.

        When *up_to_round* is given, only includes rounds 1..N (for
        cumulative round snapshots).  Otherwise includes all rounds.
        """
        assert self.output_dir is not None
        sidecar_files = sorted(
            self.output_dir.glob(f"{_ROUND_DIR_PREFIX}*/{_SUCCESS_SIDECAR_SUFFIX}")
        )
        seen: set[str] = set()
        entries: list[PageIndexEntry] = []
        for sf in sidecar_files:
            if up_to_round is not None:
                # Extract round number from parent directory name like "round_2"
                try:
                    rn = int(sf.parent.name.split("_")[1])
                except (IndexError, ValueError):
                    continue
                if rn > up_to_round:
                    continue
            for entry in PageSidecar.iter_index(sf):
                if entry.url not in seen:
                    seen.add(entry.url)
                    entries.append(entry)
        return entries

    def _index_fail(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        """Build a deduplicated fail index, excluding any URL that succeeded.

        When *up_to_round* is given, only includes rounds 1..N.
        """
        assert self.output_dir is not None

        # Collect success URLs so we can filter them out of fail entries
        success_urls: set[str] = set()
        for sf in self.output_dir.glob(f"{_ROUND_DIR_PREFIX}*/{_SUCCESS_SIDECAR_SUFFIX}"):
            for entry in PageSidecar.iter_index(sf):
                success_urls.add(entry.url)

        sidecar_files = sorted(self.output_dir.glob(f"{_ROUND_DIR_PREFIX}*/{_FAIL_SIDECAR_SUFFIX}"))
        seen: set[str] = set()
        entries: list[PageIndexEntry] = []
        for sf in sidecar_files:
            if up_to_round is not None:
                try:
                    rn = int(sf.parent.name.split("_")[1])
                except (IndexError, ValueError):
                    continue
                if rn > up_to_round:
                    continue
            for entry in PageSidecar.iter_index(sf):
                if entry.url not in seen and entry.url not in success_urls:
                    seen.add(entry.url)
                    entries.append(entry)
        return entries

    def _stream_entries_to_writer(
        self,
        entries: list[PageIndexEntry],
        prefix: str,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """Stream pages from *entries* through a fresh ``FileWriter``.

        Pages are loaded one at a time via :meth:`PageSidecar.read_page_at`,
        so the full corpus never lives in RAM.
        """
        assert self.output_dir is not None
        target_dir = output_dir if output_dir is not None else self.output_dir
        ext = self.page_config.output_extension
        writer = FileWriter(
            output_dir=target_dir,
            max_file_size_mb=self.page_config.max_file_size_mb,
            file_extension=ext,
            prefix=prefix,
            run_metadata=self._run_metadata,
        )
        for entry in entries:
            page = PageSidecar.read_page_at(
                entry.sidecar_path, entry.byte_offset, entry.byte_length
            )
            writer.add(page)
        return writer.flush()

    def _build_run_config(self, run_config_cls: type) -> object:
        """Map PageConfig to a Crawl4AI CrawlerRunConfig."""
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        kwargs["wait_until"] = self.page_config.wait_until

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        if self.page_config.scan_full_page:
            kwargs["scan_full_page"] = True
            kwargs["scroll_delay"] = self.page_config.scroll_delay

        if self.page_config.flatten_shadow_dom:
            kwargs["flatten_shadow_dom"] = True

        if self.config.stealth:
            kwargs["simulate_user"] = True
            kwargs["override_navigator"] = True
            kwargs["magic"] = True

        return run_config_cls(**kwargs)

    def _build_fallback_run_config(self, run_config_cls: type) -> object:
        """Build a reduced CrawlerRunConfig for retry rounds.

        Disables ``scan_full_page`` and stealth run-flags (``magic``,
        ``simulate_user``, ``override_navigator``) to avoid browser
        context destruction on pages that perform JS redirects during
        page evaluation.  Also downgrades ``wait_until`` to
        ``domcontentloaded`` to avoid repeated timeouts on
        analytics-heavy sites where ``networkidle`` never resolves.
        """
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        kwargs["wait_until"] = _FALLBACK_WAIT_UNTIL

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        if self.page_config.flatten_shadow_dom:
            kwargs["flatten_shadow_dom"] = True

        # scan_full_page and stealth run-flags intentionally omitted

        return run_config_cls(**kwargs)

    def _url_allowed(self, url: str) -> bool:
        """Check whether a URL passes include/exclude filters."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        bare_netloc = netloc[4:] if netloc.startswith("www.") else netloc

        # Restrict to the same base domain(s) as the seed URLs
        # Always strip www. from both sides — domain matching is www-insensitive
        if self._allowed_domains and not any(
            bare_netloc == bare_d or bare_netloc.endswith("." + bare_d)
            for d in self._allowed_domains
            for bare_d in (d[4:] if d.startswith("www.") else d,)
        ):
            return False

        # Block boilerplate browser-upgrade domains
        netloc_path = parsed.netloc + parsed.path
        if any(
            netloc_path.startswith(d) or netloc_path.startswith("www." + d)
            for d in self._BOILERPLATE_DOMAINS
        ):
            return False

        if self.config.include_only_paths and not any(
            re.search(p, url) for p in self.config.include_only_paths
        ):
            return False

        return not (
            self.config.exclude_paths and any(re.search(p, url) for p in self.config.exclude_paths)
        )

    # File extensions that are never useful pages to crawl
    _STATIC_ASSET_EXTENSIONS = frozenset(
        (
            ".css",
            ".js",
            ".ico",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".webp",
            ".bmp",
            ".tiff",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".otf",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".webm",
            ".ogg",
            ".zip",
            ".gz",
            ".tar",
            ".rar",
            ".7z",
            ".xml",
            ".json",
            ".rss",
            ".atom",
            ".axd",
            ".ashx",
            ".asmx",
        )
    )

    # Domains that appear as boilerplate "upgrade your browser" links on
    # many websites and are never useful crawl targets.
    _BOILERPLATE_DOMAINS = frozenset(
        (
            "browsehappy.com",
            "google.com",
        )
    )

    @staticmethod
    def _normalize_url(url: str, *, strip_www: bool = True) -> str:
        """Normalize a URL to reduce duplicate crawling.

        Applies: ``http`` → ``https``, optionally strips ``www.`` prefix,
        lowercases scheme + host.  The path, query and fragment are
        preserved as-is.
        """
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        scheme = "https"
        netloc = parsed.netloc.lower()
        if strip_www and netloc.startswith("www."):
            netloc = netloc[4:]
        return urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))

    @staticmethod
    def _extract_base_domains(urls: list[str], *, strip_www: bool = True) -> set[str]:
        """Derive base domains from seed URLs (e.g. 'starhub.com' from 'www.starhub.com')."""
        from urllib.parse import urlparse

        domains: set[str] = set()
        for url in urls:
            netloc = urlparse(url).netloc.lower()
            if strip_www and netloc.startswith("www."):
                netloc = netloc[4:]
            domains.add(netloc)
        return domains

    @staticmethod
    def _extract_links(result: CrawlResult, base_url: str, *, strip_www: bool = True) -> list[str]:
        """Extract absolute http(s) links from crawled HTML."""
        from urllib.parse import urljoin, urlparse

        links: list[str] = []
        for match in _HREF_RE.finditer(result.html):
            href = match.group(1)
            # Skip unresolved template placeholders (e.g. ${var}, {{var}}, {%var%})
            if _TEMPLATE_PLACEHOLDER_RE.search(href):
                continue
            absolute = urljoin(base_url, href)
            if absolute.startswith(_URL_SCHEMES):
                # Strip fragments
                absolute = absolute.split("#")[0]
                # Skip boilerplate browser-upgrade links
                parsed = urlparse(absolute)
                netloc_path = parsed.netloc + parsed.path
                if any(
                    netloc_path.startswith(d) or netloc_path.startswith("www." + d)
                    for d in SiteCrawler._BOILERPLATE_DOMAINS
                ):
                    continue
                # Skip static asset URLs
                path = parsed.path.lower()
                if any(path.endswith(ext) for ext in SiteCrawler._STATIC_ASSET_EXTENSIONS):
                    continue
                if absolute not in links:
                    links.append(absolute)
        # Normalize all discovered links and deduplicate (different raw URLs
        # may normalize to the same canonical form).
        seen: set[str] = set()
        normalized: list[str] = []
        for lnk in links:
            norm = SiteCrawler._normalize_url(lnk, strip_www=strip_www)
            if norm not in seen:
                seen.add(norm)
                normalized.append(norm)
        return normalized

    def _create_output_dir(self) -> Path:
        """Create and return a timestamped output directory."""
        folder_name = datetime.now().strftime(_TIMESTAMP_FORMAT)
        output_dir = self._output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _build_run_metadata(self) -> dict[str, object]:
        """Build run-level metadata used in output-file YAML front matter."""
        assert self.output_dir is not None
        crawl_parameters: dict[str, object] = {
            "crawler_config": json.loads(self.config.model_dump_json()),
            "page_config": json.loads(self.page_config.model_dump_json()),
        }
        return {
            "crawl_start_datetime": datetime.now().isoformat(timespec="seconds"),
            "session_id": self._derive_session_id(),
            "crawl_parameters": crawl_parameters,
        }

    def _derive_session_id(self) -> str:
        """Return Streamlit session folder name when present; else output dir name."""
        assert self.output_dir is not None
        for path in [self.output_dir, *self.output_dir.parents]:
            if path.name.startswith(_SESSION_DIR_PREFIX):
                return path.name
        return self.output_dir.name

    def _save_url_list(self, results: list[CrawlResult]) -> None:
        """Write urls.txt with one URL per line (legacy, kept for compatibility)."""
        assert self.output_dir is not None
        urls_file = self.output_dir / "urls.txt"
        lines = [r.url for r in results]
        urls_file.write_text("\n".join(lines), encoding="utf-8")
