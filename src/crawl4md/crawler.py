"""SiteCrawler — synchronous wrapper around Crawl4AI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import nest_asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from crawl4md.config import CrawlerConfig, CrawlResult, ExtractedPage, PageConfig
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.sorter import ContentSorter
from crawl4md.writer import FileWriter

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
# Output file naming
# ------------------------------------------------------------------

# Prefixes for merged content files (unsorted and sorted)
_FINAL_SUCCESS_PREFIX = "final_success_"
_FINAL_FAIL_PREFIX = "final_fail_"
_SORTED_FINAL_SUCCESS_PREFIX = "sorted_final_success_"
_SORTED_FINAL_FAIL_PREFIX = "sorted_final_fail_"

# URL list filenames
_FINAL_SUCCESS_URLS_FILE = "final_success_urls.txt"
_FINAL_FAIL_URLS_FILE = "final_fail_urls.txt"
_SORTED_FINAL_SUCCESS_URLS_FILE = "sorted_final_success_urls.txt"
_SORTED_FINAL_FAIL_URLS_FILE = "sorted_final_fail_urls.txt"

# ------------------------------------------------------------------
# Round file naming components
# ------------------------------------------------------------------

# Prefix for per-round output files (combined with round number)
_ROUND_PREFIX = "round_"
# Suffix appended to round prefix for successful pages
_SUCCESS_SUFFIX = "success_"
# Suffix appended to round prefix for failed pages
_FAIL_SUFFIX = "fail_"

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
    ) -> None:
        self.config = config
        self.page_config = page_config or PageConfig()
        self._output_base = Path(output_base) if output_base else Path.cwd()
        self.output_dir: Path | None = None
        self._allowed_domains: set[str] = self._extract_base_domains(config.urls)
        self._extractor = extractor
        self._writer = writer
        self._activity_log_size = activity_log_size
        self.content_files: list[Path] = []
        # Internal writer for failed-page content (symmetrical with _writer)
        self._fail_writer: FileWriter | None = None
        if writer is not None:
            self._fail_writer = FileWriter(
                max_file_size_mb=self.page_config.max_file_size_mb,
                file_extension=writer._file_extension,
            )

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
        """
        self.output_dir = self._create_output_dir()
        # Attach output_dir to writer so incremental flushes land there
        if self._writer is not None:
            self._writer._output_dir = self.output_dir
        if self._fail_writer is not None:
            self._fail_writer._output_dir = self.output_dir
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                all_results = pool.submit(self._run_rounds_in_proactor_loop).result()
        else:
            all_results = asyncio.run(self._run_rounds_async())
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
                for f in self.output_dir.iterdir()
                if (m := re.match(r"round_(\d+)_", f.name))
            }
        )
        for rn in round_nums:
            prefix = f"round_{rn}_"
            content = sorted(self.output_dir.glob(f"{prefix}success_content_*"))
            fail_content = sorted(self.output_dir.glob(f"{prefix}fail_content_*"))
            url_files = sorted(self.output_dir.glob(f"{prefix}*urls*.txt"))
            print(f"--- Round {rn} ---")
            _print_files("Success content", content)
            _print_files("Fail content", fail_content)
            _print_files("URL lists", url_files)

        # --- Unsorted final files (merged across rounds) ---
        final_success = sorted(self.output_dir.glob("final_success_content_*"))
        final_fail = sorted(self.output_dir.glob("final_fail_content_*"))
        if final_success or final_fail:
            print("--- Final (unsorted, merged across rounds) ---")
            _print_files("Success content", final_success)
            _print_files("Fail content", final_fail)

        # --- Sorted files (primary output) ---
        sorted_success = sorted(self.output_dir.glob("sorted_final_success_content_*"))
        sorted_fail = sorted(self.output_dir.glob("sorted_final_fail_content_*"))
        sorted_urls = sorted(self.output_dir.glob("sorted_final_*_urls.txt"))
        final_urls = sorted(self.output_dir.glob("final_*_urls.txt"))
        all_urls = sorted(set(sorted_urls) | set(final_urls), key=lambda p: p.name)
        if sorted_success or sorted_fail:
            print("--- Sorted by URL path (primary output) ---")
            _print_files("Success content", sorted_success)
            _print_files("Fail content", sorted_fail)
            _print_files("URL lists", all_urls)

        if fail_count > 0:
            print(
                f"See sorted_final_fail_urls.txt for the "
                f"{fail_count} URL(s) that could not be crawled."
            )

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
        succeeded_urls: set[str] = set()  # URLs already crawled successfully
        total_rounds = 1 + self.config.max_retries  # round 1 + retries

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
        round_prefix = f"{_ROUND_PREFIX}1_"
        if self._writer is not None:
            self._writer.reset(f"{round_prefix}{_SUCCESS_SUFFIX}")
        if self._fail_writer is not None:
            self._fail_writer.reset(f"{round_prefix}{_FAIL_SUFFIX}")
        print(f"--- Round 1/{total_rounds}: Crawling {len(self.config.urls)} seed URL(s) ---")

        # Shared across all rounds so link discovery in retries sees
        # every URL ever queued and uses the correct depth.
        all_generated: set[str] = set()
        url_depths: dict[str, int] = {}

        # Use a single browser instance across all rounds so that
        # cookies (including WAF challenge tokens) persist through retries.
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            round_results = await self._crawl_urls_async(
                urls=self.config.urls,
                crawler=crawler,
                run_cfg=run_cfg,
                discover_links=True,
                round_prefix=round_prefix,
                prior_success=0,
                prior_fail=0,
                round_label=f"Round 1/{total_rounds}",
                all_generated=all_generated,
                url_depths=url_depths,
            )
            success, fail = self._split_results(round_results)
            self._save_url_lists(success, fail, round_prefix)
            if self._writer is not None:
                self._writer.flush()
            if self._fail_writer is not None:
                self._fail_writer.flush()
            all_success.extend(success)
            succeeded_urls.update(r.url for r in success)
            all_fail.extend(fail)

            # --- Retry rounds ---
            failed_urls = [r.url for r in all_fail]
            for retry_num in range(1, self.config.max_retries + 1):
                if not failed_urls:
                    print("\nAll pages succeeded — skipping remaining retries.")
                    break

                round_num = retry_num + 1
                round_prefix = f"{_ROUND_PREFIX}{round_num}_"
                if self._writer is not None:
                    self._writer.reset(f"{round_prefix}{_SUCCESS_SUFFIX}")
                if self._fail_writer is not None:
                    self._fail_writer.reset(f"{round_prefix}{_FAIL_SUFFIX}")

                cooldown = _ROUND_COOLDOWN * random.uniform(
                    _ROUND_COOLDOWN_JITTER_MIN, _ROUND_COOLDOWN_JITTER_MAX
                )
                print(
                    f"\n--- Round {round_num}/{total_rounds}: Retrying {len(failed_urls)} failed URL(s) (waiting {cooldown:.0f}s cooldown) ---"
                )
                await asyncio.sleep(cooldown)

                round_results = await self._crawl_urls_async(
                    urls=failed_urls,
                    crawler=crawler,
                    run_cfg=fallback_run_cfg,
                    discover_links=True,
                    is_retry=True,
                    round_prefix=round_prefix,
                    prior_success=len(all_success),
                    prior_fail=len(all_fail),
                    skip_urls=frozenset(succeeded_urls),
                    round_label=f"Round {round_num}/{total_rounds}",
                    all_generated=all_generated,
                    url_depths=url_depths,
                )
                success, fail = self._split_results(round_results)
                self._save_url_lists(success, fail, round_prefix)
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

        # --- Final merged files (unsorted) ---
        remaining_fail_urls = [r.url for r in all_fail]
        self._write_final_files(all_success, all_fail, remaining_fail_urls)

        # --- Sorted final files (grouped by URL path) ---
        self._write_sorted_files(all_success, all_fail)
        self.content_files = self._get_final_content_files()

        total_crawled = len(all_success) + len(all_fail)
        print(
            f"\nDone! {len(all_success)} succeeded, {len(all_fail)} failed out of {total_crawled} total."
        )
        assert self.output_dir is not None
        print(f"Output folder: {self.output_dir}")

        # Return all results (success + remaining failures) for API consumers
        return all_success + all_fail

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
        round_prefix: str = "",
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
        visited: set[str] = set(skip_urls)
        generated: set[str] = all_generated if all_generated is not None else set()
        depths: dict[str, int] = url_depths if url_depths is not None else {}
        queue: list[tuple[str, int]] = []
        for seed_url in urls:
            if seed_url not in generated and len(generated) >= self.config.limit:
                break
            generated.add(seed_url)
            queue.append((seed_url, depths.get(seed_url, 1)))
        progress = ProgressReporter(
            min(len(urls), self.config.limit),
            prior_success=prior_success,
            prior_fail=prior_fail,
            round_label=round_label,
            max_log_entries=self._activity_log_size,
        )

        consecutive_blocks = 0

        while queue and len(results) < self.config.limit:
            url, depth = queue.pop(0)

            if url in visited:
                continue
            visited.add(url)

            if not self._url_allowed(url):
                continue

            try:
                progress.set_activity(f"Crawling {url}")
                result = await crawler.arun(url=url, config=run_cfg)

                # Use the final URL after any redirects
                final_url = getattr(result, "redirected_url", None) or url
                redirected = final_url != url

                if redirected and final_url in visited:
                    continue

                visited.add(final_url)
                generated.add(final_url)
                depths[final_url] = depth

                if redirected and not self._url_allowed(final_url):
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

            # Extract and buffer content incrementally
            if crawl_result.success and self._extractor and self._writer:
                progress.set_activity("Extracting content")
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
                progress.set_activity(f"WAF back-off {backoff:.1f}s")
                await asyncio.sleep(backoff)
            else:
                consecutive_blocks = 0

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

            # Flush content and URL lists periodically
            if len(results) % self.config.flush_interval == 0:
                progress.set_activity(f"Flushing to disk ({len(results)} pages processed)")
                if self._writer is not None:
                    self._writer.flush()
                if self._fail_writer is not None:
                    self._fail_writer.flush()
                success, fail = self._split_results(results)
                self._save_url_lists(success, fail, round_prefix)

            # Throttle between pages — jitter mimics human browsing.
            # Round 1 applies a light delay; retries apply a heavier one.
            # Both require delay > 0 (default 0 keeps current fast behavior).
            if self.config.delay > 0:
                if is_retry:
                    jitter = self.config.delay * random.uniform(
                        _JITTER_RETRY_MIN, _JITTER_RETRY_MAX
                    )
                    progress.set_activity(f"Delay {jitter:.1f}s (retry cooldown)")
                else:
                    jitter = self.config.delay * random.uniform(
                        _JITTER_ROUND1_MIN, _JITTER_ROUND1_MAX
                    )
                    progress.set_activity(f"Delay {jitter:.1f}s (throttle)")
                await asyncio.sleep(jitter)

            # Discover links for deeper crawling
            if discover_links and depth < self.config.max_depth and crawl_result.success:
                progress.set_activity(f"Discovering links from {url}")
                new_links = self._extract_links(crawl_result, crawl_result.url)
                added = 0
                for link in new_links:
                    if len(generated) >= self.config.limit:
                        break
                    if link not in generated:
                        generated.add(link)
                        depths[link] = depth + 1
                        queue.append((link, depth + 1))
                        added += 1
                progress.update_activity_label(f"Discovered {added} links from {url}")
                # Update progress total to reflect discovered pages
                progress.total = min(len(generated), self.config.limit)

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
        prefix: str = "",
    ) -> None:
        """Write per-round success and fail URL lists."""
        assert self.output_dir is not None
        if success:
            path = self.output_dir / f"{prefix}success_urls.txt"
            path.write_text("\n".join(r.url for r in success), encoding="utf-8")
        if fail:
            path = self.output_dir / f"{prefix}fail_urls.txt"
            path.write_text("\n".join(r.url for r in fail), encoding="utf-8")

    def _write_final_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
        remaining_fail_urls: list[str],
    ) -> None:
        """Produce final merged URL lists and unsorted content files (deduplicated)."""
        assert self.output_dir is not None
        ext = self.page_config.output_extension

        # final_success_urls.txt — all successful URLs across all rounds (deduplicated)
        if all_success:
            seen: set[str] = set()
            unique_urls: list[str] = []
            for r in all_success:
                if r.url not in seen:
                    seen.add(r.url)
                    unique_urls.append(r.url)
            path = self.output_dir / _FINAL_SUCCESS_URLS_FILE
            path.write_text("\n".join(unique_urls), encoding="utf-8")

        # final_fail_urls.txt — URLs that still failed after all retries (deduplicated)
        if remaining_fail_urls:
            unique_fail = list(dict.fromkeys(remaining_fail_urls))
            path = self.output_dir / _FINAL_FAIL_URLS_FILE
            path.write_text("\n".join(unique_fail), encoding="utf-8")

        # final_success_content_*.ext — unsorted merged content (deduplicated)
        if all_success and self._extractor is not None and self._writer is not None:
            seen_urls: set[str] = set()
            unique_success: list[CrawlResult] = []
            for r in all_success:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    unique_success.append(r)
            pages = [self._extractor._extract_page(r) for r in unique_success if r.markdown.strip()]
            pages = [p for p in pages if p.markdown.strip()]
            if pages:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix=_FINAL_SUCCESS_PREFIX,
                )
                for page in pages:
                    w.add(page)
                w.flush()

        # final_fail_content_*.ext — unsorted fail content (deduplicated)
        if all_fail and self._writer is not None:
            seen_fail_urls: set[str] = set()
            unique_fail_results: list[CrawlResult] = []
            for r in all_fail:
                if r.url not in seen_fail_urls:
                    seen_fail_urls.add(r.url)
                    unique_fail_results.append(r)
            fail_pages = []
            for r in unique_fail_results:
                raw_body = r.markdown.strip() or r.html.strip() or "(no response)"
                fail_pages.append(
                    ExtractedPage(
                        url=r.url,
                        title=f"{_FAILED_TITLE_PREFIX} {r.error or _UNKNOWN_ERROR_MSG}",
                        markdown=(
                            f"{_ERROR_SECTION_HEADER} {r.error or _UNKNOWN_ERROR_MSG}\n\n"
                            f"{_RAW_RESPONSE_HEADER}\n\n{raw_body}"
                        ),
                    )
                )
            if fail_pages:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix=_FINAL_FAIL_PREFIX,
                )
                for page in fail_pages:
                    w.add(page)
                w.flush()

    def _write_sorted_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Re-extract, sort by URL path, and write sorted final files."""
        if self._writer is None:
            return
        assert self.output_dir is not None
        ext = self.page_config.output_extension

        # Sorted success content (deduplicated by URL, keeping first occurrence)
        if all_success and self._extractor is not None:
            seen_urls: set[str] = set()
            unique_success: list[CrawlResult] = []
            for r in all_success:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    unique_success.append(r)
            pages = [self._extractor._extract_page(r) for r in unique_success if r.markdown.strip()]
            pages = [p for p in pages if p.markdown.strip()]
            sorted_pages = ContentSorter.sort(pages)
            if sorted_pages:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix=_SORTED_FINAL_SUCCESS_PREFIX,
                )
                for page in sorted_pages:
                    w.add(page)
                w.flush()
                # Sorted success URLs
                path = self.output_dir / _SORTED_FINAL_SUCCESS_URLS_FILE
                path.write_text(
                    "\n".join(p.url for p in sorted_pages),
                    encoding="utf-8",
                )

        # Sorted fail content (deduplicated by URL, keeping first occurrence)
        if all_fail:
            seen_fail_urls: set[str] = set()
            unique_fail: list[CrawlResult] = []
            for r in all_fail:
                if r.url not in seen_fail_urls:
                    seen_fail_urls.add(r.url)
                    unique_fail.append(r)
            fail_pages = []
            for r in unique_fail:
                raw_body = r.markdown.strip() or r.html.strip() or "(no response)"
                fail_pages.append(
                    ExtractedPage(
                        url=r.url,
                        title=f"{_FAILED_TITLE_PREFIX} {r.error or _UNKNOWN_ERROR_MSG}",
                        markdown=(
                            f"{_ERROR_SECTION_HEADER} {r.error or _UNKNOWN_ERROR_MSG}\n\n"
                            f"{_RAW_RESPONSE_HEADER}\n\n{raw_body}"
                        ),
                    )
                )
            sorted_fail = ContentSorter.sort(fail_pages)
            if sorted_fail:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix=_SORTED_FINAL_FAIL_PREFIX,
                )
                for page in sorted_fail:
                    w.add(page)
                w.flush()
                # Sorted fail URLs
                path = self.output_dir / _SORTED_FINAL_FAIL_URLS_FILE
                path.write_text(
                    "\n".join(p.url for p in sorted_fail),
                    encoding="utf-8",
                )

    def _get_final_content_files(self) -> list[Path]:
        """Return sorted list of final content files."""
        assert self.output_dir is not None
        pattern = f"sorted_final_success_content_*{self.page_config.output_extension}"
        return sorted(self.output_dir.glob(pattern))

    def _build_run_config(self, run_config_cls: type) -> object:
        """Map PageConfig to a Crawl4AI CrawlerRunConfig."""
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        if self.page_config.scan_full_page:
            kwargs["scan_full_page"] = True
            kwargs["scroll_delay"] = self.page_config.scroll_delay

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
        page evaluation.  All other settings are preserved.
        """
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        # scan_full_page and stealth run-flags intentionally omitted

        return run_config_cls(**kwargs)

    def _url_allowed(self, url: str) -> bool:
        """Check whether a URL passes include/exclude filters."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Restrict to the same base domain(s) as the seed URLs
        if self._allowed_domains and not any(
            parsed.netloc == d or parsed.netloc.endswith("." + d) for d in self._allowed_domains
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
            ".pdf",
            ".zip",
            ".gz",
            ".tar",
            ".rar",
            ".7z",
            ".xml",
            ".json",
            ".rss",
            ".atom",
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
    def _extract_base_domains(urls: list[str]) -> set[str]:
        """Derive base domains from seed URLs (e.g. 'starhub.com' from 'www.starhub.com')."""
        from urllib.parse import urlparse

        domains: set[str] = set()
        for url in urls:
            netloc = urlparse(url).netloc.lower()
            # Strip www. prefix to get the base domain
            if netloc.startswith("www."):
                netloc = netloc[4:]
            domains.add(netloc)
        return domains

    @staticmethod
    def _extract_links(result: CrawlResult, base_url: str) -> list[str]:
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
        return links

    def _create_output_dir(self) -> Path:
        """Create and return a timestamped output directory."""
        folder_name = datetime.now().strftime(_TIMESTAMP_FORMAT)
        output_dir = self._output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _save_url_list(self, results: list[CrawlResult]) -> None:
        """Write urls.txt with one URL per line (legacy, kept for compatibility)."""
        assert self.output_dir is not None
        urls_file = self.output_dir / "urls.txt"
        lines = [r.url for r in results]
        urls_file.write_text("\n".join(lines), encoding="utf-8")
