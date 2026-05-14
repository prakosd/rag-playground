"""English (en) translations for the crawl4md Streamlit app."""

from __future__ import annotations

from crawl4md_streamlit.i18n._types import Strings

STRINGS_EN: Strings = {
    # ── Page ──────────────────────────────────────────────────────────────
    "PAGE_TITLE": ":material/travel_explore: crawl4md — Website Crawler",
    "PAGE_SUBTITLE": (
        "Point it at any website and crawl4md will follow links, extract the main "
        "content from each page, and save everything as clean, readable Markdown files."
    ),
    "SESSION_PREFIX": "Session: {session_id}",
    "SESSION_LOADING": "Loading browser sessions...",
    "SESSION_SELECTOR_LABEL": "Session ID",
    "SESSION_CREATE_BUTTON": "New",
    "PROGRESS_HEADER": "📊 Progress",
    "LANG_SELECTOR_LABEL": "Language",
    # ── Form ──────────────────────────────────────────────────────────────
    "FORM_SUBHEADER": "Set up your crawl",
    "FORM_CAPTION": (
        "Configure the starting URLs, filtering rules, and crawl behaviour before starting."
    ),
    "FORM_URLS_LABEL": "Website URLs",
    "FORM_URLS_HELP": (
        "Paste one or more starting pages. Use one line per site or separate with commas."
    ),
    "FORM_INCLUDE_PATHS_LABEL": "Only include URL patterns",
    "FORM_INCLUDE_PATHS_HELP": (
        "Leave blank to allow all pages on the same site. "
        "Use regex patterns to stay inside a section."
    ),
    "FORM_EXCLUDE_PATHS_LABEL": "Skip URL patterns",
    "FORM_EXCLUDE_PATHS_HELP": "Pages matching these regex patterns will be skipped.",
    "FORM_LIMIT_LABEL": "Page limit",
    "FORM_LIMIT_HELP": (
        "Discovery cutoff: once this many pages are discovered, "
        "the crawler stops discovering new links but still finishes "
        "all already discovered pages."
    ),
    "FORM_DELAY_LABEL": "Delay between pages",
    "FORM_DELAY_HELP": "Adds a pause between pages to reduce blocking by websites.",
    "FORM_DEPTH_LABEL": "Link depth",
    "FORM_DEPTH_HELP": "How many clicks deep to follow links.",
    "FORM_RETRIES_LABEL": "Retry rounds",
    "FORM_RETRIES_HELP": "Tries failed pages again after a cooldown.",
    "FORM_OUTPUT_FORMAT_LABEL": "Output format",
    "FORM_OUTPUT_FORMAT_HELP": "Choose Markdown for formatted text or TXT for plain text.",
    "FORM_EXTRACT_MAIN_LABEL": "Extract main content only",
    "FORM_EXTRACT_MAIN_HELP": (
        "Keeps article/product text and strips most menus, footers, and sidebars."
    ),
    "FORM_ADVANCED_LABEL": "Advanced options",
    "FORM_FLUSH_LABEL": "Write every N pages",
    "FORM_FLUSH_HELP": "Writes generated files periodically during the crawl.",
    "FORM_MAX_FILE_SIZE_LABEL": "Max file size (MB)",
    "FORM_MAX_FILE_SIZE_HELP": "Splits output into files that are easier to open and download.",
    "FORM_WAIT_FOR_LABEL": "Extra render wait",
    "FORM_WAIT_FOR_HELP": "Helps JavaScript-heavy pages finish loading before extraction.",
    "FORM_TIMEOUT_LABEL": "Page timeout",
    "FORM_TIMEOUT_HELP": "Maximum seconds to spend loading one page.",
    "FORM_ACTIVITY_LOG_LABEL": "Activity log entries",
    "FORM_ACTIVITY_LOG_HELP": (
        "Controls how many newest entries are shown in the Activity log panel."
    ),
    "FORM_EXCLUDE_TAGS_LABEL": "HTML tags to remove",
    "FORM_EXCLUDE_TAGS_HELP": (
        "Common values remove menus, scripts, forms, and styles from extracted text."
    ),
    "FORM_INCLUDE_ONLY_TAGS_LABEL": "Only keep these HTML tags",
    "FORM_INCLUDE_ONLY_TAGS_HELP": (
        "Advanced: only extract content from these HTML tags. Leave blank for normal use."
    ),
    # ── Action buttons ────────────────────────────────────────────────────
    "BTN_START": "Start",
    "BTN_STOP": "Stop",
    # ── Stop dialog ───────────────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_STOP_BODY": "Stop this crawl now? This will cancel any pages still in progress.",
    "DIALOG_BTN_KEEP": "Keep running",
    "DIALOG_BTN_STOP": "Stop crawl",
    # ── Toast messages ────────────────────────────────────────────────────
    "TOAST_SUCCESS": "{n} page(s) crawled successfully",
    "TOAST_FAILED": "{n} page(s) failed",
    "TOAST_DISCOVERED": "{n} page(s) discovered",
    # ── Progress metrics ──────────────────────────────────────────────────
    "METRIC_PROCESSED_LABEL": "📄 Page attempts",
    "METRIC_PROCESSED_DELTA": "{n} total",
    "METRIC_PROCESSED_DELTA_RETRY": "{n} retry attempts",
    "METRIC_PROCESSED_TOOLTIP": (
        "Live attempt count for the current crawl phase. Failed pages may be attempted again during retries."
    ),
    "METRIC_SUCCESSFUL_LABEL": "✅ Successful",
    "METRIC_SUCCESSFUL_DELTA": "{n} completed",
    "METRIC_SUCCESSFUL_TOOLTIP": "Pages processed successfully",
    "METRIC_FAILED_LABEL": "❌ Failed",
    "METRIC_FAILED_DELTA": "{n} failed",
    "METRIC_FAILED_TOOLTIP": "Pages that failed during processing",
    "METRIC_DISCOVERED_LABEL": "🔎 Discovered",
    "METRIC_DISCOVERED_DELTA": "{n} found, {m} remaining",
    "METRIC_DISCOVERED_TOOLTIP": "URLs discovered and queued so far",
    "METRIC_LIMIT_LABEL": "🔢 Limit",
    "METRIC_LIMIT_TOOLTIP": (
        "Discovery cutoff — once reached, no new URLs are added, "
        "but already discovered URLs are still crawled."
    ),
    "METRIC_LIMIT_DELTA_REACHED": "Discovery stopped (limit reached)",
    "METRIC_LIMIT_DELTA_MORE": "Discovering more pages",
    "METRIC_STATE_WORD": "State",
    "METRIC_STATE_DELTA": "Current lifecycle stage",
    "METRIC_STATE_TOOLTIP": "Current crawl lifecycle state",
    # ── Progress bar labels ───────────────────────────────────────────────
    "DENOM_DISCOVERED": "{n} discovered",
    "DENOM_LIMIT": "{n} limit",
    "PROGRESS_ATTEMPTS": "{n} attempts",
    "PROGRESS_COMPLETE": "complete",
    "PROGRESS_RETRYING": "Retrying failed pages",
    # ── Status line ───────────────────────────────────────────────────────
    "STATUS_CRAWLING": "Crawling: {url_html}",
    "STATUS_ELAPSED": "Elapsed time: {elapsed}",
    "STATUS_NEXT_URL": "Next: {url_html}",
    # ── ETA phrases ───────────────────────────────────────────────────────
    "ETA_ESTIMATING": "Estimating...",
    "ETA_LESS_THAN_MINUTE": "Less than a minute left",
    "ETA_MINUTES": "About {n} minute(s) left",
    "ETA_HOURS_MINUTES": "About {h}h {m}m left",
    # ── State banners ─────────────────────────────────────────────────────
    "BANNER_FAILED": "🔴 Failed — processing encountered errors",
    "BANNER_CANCEL_REQUESTED": "🟡 Stop requested — waiting for worker to finish",
    "BANNER_STOPPED": "🟡 Stopped — generated files remain available",
    # ── Error messages ────────────────────────────────────────────────────
    "ERROR_NO_ACTIVE_CRAWL": "There is no active crawl to stop.",
    "ERROR_CRAWL_ALREADY_RUNNING": "A crawl is already running in this browser session.",
    "ERROR_SESSION_STORAGE_WRITE": (
        "Browser storage is unavailable. Enable local storage in this browser and refresh the page."
    ),
    "ERROR_SESSION_FOLDER_MISSING": "Session folder does not exist.",
    "ERROR_CRAWL_FAILED_FALLBACK": "The crawl failed.",
    "ERROR_PLAYWRIGHT_MISSING": (
        "Playwright browser binaries are missing in this Python environment. "
        "Install Chromium and then retry the crawl:\n"
        "python -m playwright install chromium"
    ),
    # ── Activity log ──────────────────────────────────────────────────────
    "ACTIVITY_LOG_HEADER": "Activity log",
    # ── Files section ─────────────────────────────────────────────────────
    "FILES_HEADER": "Generated Files",
    "FILES_DOWNLOADS_SUBHEADER": "Downloads",
    "FILES_COL_NAME": "File",
    "FILES_COL_TYPE": "Type",
    "FILES_COL_SIZE": "Size (MB)",
    "FILES_COL_MODIFIED": "Modified",
    "FILES_SESSION_CAPTION": "Session folder: {path}",
    "FILES_DOWNLOAD_TOO_LARGE": "{file} is too large to download from the app.",
    "FILES_DOWNLOADS_IN_PROGRESS": "Crawl in progress — files generated so far are shown below.",
    "FILES_PREVIEW_BUTTON": ":material/visibility:",
    "FILES_PREVIEW_HELP": "Preview {file}",
    "FILES_PREVIEW_DIALOG_TITLE": "Preview: {file}",
    "FILES_PREVIEW_DETAILS": "Path: {path} · Size: {size_kib} KiB",
    "FILES_PREVIEW_UNSUPPORTED": "Preview is available only for text-based files. {file} is not previewable.",
    "FILES_PREVIEW_MISSING": "The selected file is no longer available: {file}",
    "FILES_PREVIEW_READ_ERROR": "Unable to read file for preview: {file}",
    "FILES_PREVIEW_EMPTY": "{file} is empty.",
    "FILES_PREVIEW_TRUNCATED": "Preview is capped to the first {limit_kib} KiB.",
    # ── State display labels ──────────────────────────────────────────────
    "STATE_LABELS": {
        "idle": "Ready",
        "running": "Running",
        "failed": "Failed",
        "completed": "Completed",
        "cancel_requested": "Cancel Requested",
        "stopped": "Stopped",
    },
}
