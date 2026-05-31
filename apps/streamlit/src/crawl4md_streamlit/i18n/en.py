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
    "SESSION_EXPIRY_CAPTION": "This session expires in {days} days \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_SINGULAR": "This session expires in 1 day \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOURS": "This session expires in {days} days and {hours} hours \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_DAY_HOURS": "This session expires in 1 day and {hours} hours \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOUR": "This session expires in {days} days and 1 hour \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_DAY_HOUR": "This session expires in 1 day and 1 hour \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_HOURS": "This session expires in {hours} hours \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR": "This session expires in 1 hour \u2014 all files will be deleted.",
    "SESSION_EXPIRY_CAPTION_SOON": "This session is expiring soon \u2014 all files will be deleted.",
    "SESSION_CREATE_BUTTON": "New",
    "SESSION_CREATE_BUTTON_TOOLTIP": "Create a separate session (keeps current results)",
    "SESSION_LOAD_BUTTON_TOOLTIP": "Load an existing session by ID",
    "SESSION_EXTEND_BUTTON_TOOLTIP": "Extend session — gives up to 7 days from now",
    "PROGRESS_HEADER": "⏳ Progress",
    "PROGRESS_CAPTION": "Track crawl activity as it runs.",
    "PROGRESS_EXPANDER_LABEL": "Live statistics",
    "LANG_SELECTOR_LABEL": "Language",
    "NAV_CRAWL": "Crawl",
    "NAV_VECTOR_INDEX": "Vector Index",
    "NAV_SEMANTIC_SEARCH": "Semantic Search",
    "NAV_RAG_QA": "RAG Q&A",
    "NAV_CONVERSATIONAL_RAG": "Conversational RAG",
    "PAGE_VECTOR_INDEX_TITLE": ":material/database: Step 2 - Build Vector Index",
    "PAGE_VECTOR_INDEX_SUBTITLE": (
        "Select Markdown, text, or ZIP outputs, split them into chunks, generate embeddings, "
        "and store them in a vector database."
    ),
    "PAGE_SEMANTIC_SEARCH_TITLE": ":material/search: Step 3 - Semantic Search",
    "PAGE_SEMANTIC_SEARCH_SUBTITLE": (
        "Embed a search query, retrieve similar chunks, and inspect ranked matches from the "
        "vector database."
    ),
    "PAGE_RAG_QA_TITLE": ":material/question_answer: Step 4 - RAG Q&A",
    "PAGE_RAG_QA_SUBTITLE": (
        "Ask one question, retrieve context, build the prompt, and review the LLM answer "
        "with sources."
    ),
    "PAGE_CONVERSATIONAL_RAG_TITLE": ":material/forum: Step 5 - Conversational RAG",
    "PAGE_CONVERSATIONAL_RAG_SUBTITLE": (
        "Chat across turns using retrieved context, conversation history, and query rewriting."
    ),
    "PLACEHOLDER_SECTION_HEADER": "Step workspace",
    "PLACEHOLDER_SECTION_CAPTION": (
        "This page uses the same session controls and layout while the RAG backend is added."
    ),
    "PLACEHOLDER_EXPANDER_LABEL": "Requirements summary",
    "PLACEHOLDER_VECTOR_INDEX": (
        "Select generated Markdown or text files, including ZIP archives that contain them. "
        "The future workflow will split content into chunks, generate embeddings, and persist "
        "the index in ChromaDB."
    ),
    "PLACEHOLDER_SEMANTIC_SEARCH": (
        "Enter a search query, embed it with the same model used for the indexed chunks, run a "
        "similarity search, then display ranked snippets with scores and source references."
    ),
    "PLACEHOLDER_RAG_QA": (
        "Ask a single question, retrieve the most relevant chunks, combine them into a prompt, "
        "call the selected LLM, then display the answer together with the context sources."
    ),
    "PLACEHOLDER_CONVERSATIONAL_RAG": (
        "Use a chat-style interface that can rewrite the retrieval query from conversation "
        "context, include recent message history, and grow into memory-aware RAG workflows."
    ),
    # ── Form ──────────────────────────────────────────────────────────────
    "FORM_SUBHEADER": "⚙️ Set up your crawl",
    "FORM_CAPTION": (
        "Configure the starting URLs, filtering rules, and crawl behaviour before starting."
    ),
    "FORM_EXPANDER_LABEL": "Crawl settings",
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
    "FORM_DELAY_HELP": "Spaces out page starts to reduce blocking by websites.",
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
    "FORM_MAX_CONCURRENT_LABEL": "Parallel fetches",
    "FORM_MAX_CONCURRENT_HELP": (
        "Fetches up to N already discovered pages at the same time during the "
        "initial crawl. 5 (default) can speed up large crawls on permissive "
        "sites. Use 1 for strict or easily rate-limited sites. "
        "Delay still spaces request starts; retries stay serial for WAF safety. "
        "Trade-off: higher values increase the chance of rate limits or blocks. "
        "Minimum: 1. Recommended: 1-5."
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
    # ── Load session dialog ───────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_LOAD_SESSION_ID_LABEL": "Session ID",
    "DIALOG_LOAD_SESSION_ID_PLACEHOLDER": "Paste session ID here",
    "DIALOG_LOAD_SESSION_ID_HELP": "Enter the session ID from another browser or computer",
    "DIALOG_LOAD_BTN_CANCEL": "Cancel",
    "DIALOG_LOAD_BTN_LOAD": "Load",
    "DIALOG_LOAD_SESSION_NOT_FOUND": "Session '{id}' does not exist on this server.",
    "DIALOG_LOAD_SESSION_ALREADY_LOADED": "Session '{id}' is already available. Switching to it.",
    "DIALOG_LOAD_SESSION_INVALID_ID": "Not a valid session ID.",
    # ── Toast messages ────────────────────────────────────────────────────
    "TOAST_SUCCESS": "{n} page(s) crawled successfully",
    "TOAST_FAILED": "{n} page(s) failed",
    "TOAST_DISCOVERED": "{n} page(s) discovered",
    "TOAST_SESSION_CREATED": "New session created",
    "TOAST_SESSION_LOADED": "Session '{id}' loaded.",
    "TOAST_SESSION_EXTENDED": "Session extended — expiry reset to 7 days",
    "TOAST_SESSION_EXTEND_FAILED": "Could not extend session",
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
    # ── Progress charts ───────────────────────────────────────────────────
    "CHART_CUMULATIVE_TITLE": "Cumulative crawl totals over time",
    "CHART_CUMULATIVE_TITLE_SECOND": "Crawl totals by second",
    "CHART_CUMULATIVE_TITLE_MINUTE": "Crawl progress timeline",
    "CHART_CUMULATIVE_TITLE_HOUR": "Crawl totals by hour",
    "CHART_SERIES_LIMIT": "Limit",
    "CHART_SERIES_DISCOVERED": "Discovered",
    "CHART_SERIES_SUCCESSFUL": "Successful",
    "CHART_SERIES_FAILED": "Failed",
    "CHART_TIME_UNIT_SECOND": "second",
    "CHART_TIME_UNIT_MINUTE": "minute",
    "CHART_TIME_UNIT_HOUR": "hour",
    # ── Status line ───────────────────────────────────────────────────────
    "STATUS_CRAWLING": "Crawling: {url_html}",
    "STATUS_ELAPSED": "Elapsed time: {elapsed}",
    "STATUS_NEXT_URL": "Next: {url_html}",
    "STATUS_ACTIVE_FETCHES": "Active fetches ({count} of {max} configured)",
    "STATUS_NEXT_FETCHES": "Next up ({count})",
    "STATUS_MORE_URLS": "+{count} more",
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
    "FILES_HEADER": "File Details",
    "FILES_CRAWL_RESULT_LABEL": "📁 Crawl result",
    "FILES_DOWNLOADS_SUBHEADER": "🗂️ Output Files",
    "FILES_COL_NAME": "File",
    "FILES_COL_TYPE": "Type",
    "FILES_COL_SIZE": "Size (MB)",
    "FILES_COL_MODIFIED": "Modified",
    "FILES_SESSION_CAPTION": "Session folder: {path}",
    "FILES_DOWNLOAD_TOO_LARGE": "{file} is too large to download from the app.",
    "FILES_DOWNLOADS_IN_PROGRESS": "Crawl in progress — files appear as pages are processed.",
    "FILES_DOWNLOADS_SUBTITLE": "Preview or download your crawled files below.",
    "FILES_PREVIEW_BUTTON": ":material/visibility:",
    "FILES_PREVIEW_HELP": "Preview {file}",
    "FILES_PREVIEW_PATH": "Path: {path}",
    "FILES_PREVIEW_SIZE": "Size: {size_kib} KiB",
    "FILES_PREVIEW_MODIFIED_AT": "Last modified: {value}",
    "FILES_PREVIEW_CREATED_AT": "Created: {value}",
    "FILES_PREVIEW_UNSUPPORTED": "Preview is available only for text-based files. {file} is not previewable.",
    "FILES_PREVIEW_MISSING": "The selected file is no longer available: {file}",
    "FILES_PREVIEW_READ_ERROR": "Unable to read file for preview: {file}",
    "FILES_PREVIEW_EMPTY": "{file} is empty.",
    "FILES_PREVIEW_TRUNCATED": "Preview is capped to the first {limit_kib} KiB.",
    # ── Ready result download ──────────────────────────────────────────
    "READY_RESULT_HEADER": "📦 Crawl results ready",
    "READY_RESULT_SINGLE_SUBTITLE": "1 success file ready to download",
    "READY_RESULT_ZIP_SUBTITLE": "{count} success files — packaged as a zip",
    "READY_RESULT_DOWNLOAD_BUTTON": "⬇ Download",
    "READY_RESULT_TOO_LARGE": "The output is too large to download from the app — use the file listing below.",
    # ── Portfolio footer ─────────────────────────────────────────────────
    "FOOTER_BUILT_BY": "Built by {author}",
    "FOOTER_TAGLINE": "AI-assisted crawl-to-RAG playground",
    "FOOTER_LINK_LINKEDIN": "LinkedIn",
    "FOOTER_LINK_GITHUB": "GitHub",
    "FOOTER_LINK_README": "Read the docs",
    "FOOTER_LINK_STREAMLIT_README": "App docs",
    # ── Portfolio modal ──────────────────────────────────────────────────
    "PORTFOLIO_MODAL_TITLE": "Hi, I'm {author}",
    "PORTFOLIO_MODAL_BODY": (
        "I'm building this project as a hands-on AI-assisted RAG playground. "
        "Today it crawls websites and turns pages into clean Markdown. Next, "
        "I'm extending it with vector embeddings, semantic search, RAG question "
        "answering, and conversational RAG experiments."
    ),
    "PORTFOLIO_MODAL_CTA": (
        "If this project is useful or interesting, connect with me on LinkedIn "
        "or star the GitHub repo. I'd love to share progress and compare notes."
    ),
    "PORTFOLIO_MODAL_LINK_LINKEDIN": "Connect on LinkedIn",
    "PORTFOLIO_MODAL_LINK_GITHUB": "Star the GitHub repo",
    "PORTFOLIO_MODAL_LINK_README": "Read the docs",
    "PORTFOLIO_MODAL_LINK_STREAMLIT_README": "App developer guide",
    "PORTFOLIO_MODAL_CLOSE_LABEL": "Close",
    "PORTFOLIO_MODAL_PHOTO_ALT": "Profile photo of {author}",
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
