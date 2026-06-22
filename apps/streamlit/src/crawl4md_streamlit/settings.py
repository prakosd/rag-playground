"""Typed, env-driven configuration for the Streamlit app.

This is the app's single source of deployment-tunable settings — the Python
equivalent of a React ``config.ts`` that loads ``process.env`` into a typed
``EnvironmentVariables`` object. Values are read (in increasing precedence) from
``.env.defaults`` (committed defaults), ``.env`` (local, git-ignored overrides),
and the process environment — which is what Streamlit Community Cloud uses, since
it exposes root-level ``secrets.toml`` keys as environment variables.

Only **non-secret** knobs live here. Credentials (``AWS_*``, ``OPENAI_API_KEY``)
stay as plain environment variables read by their own SDKs, so secrets never mix
with regular configuration.

The library config models (``crawl4md``/``vector_indexer``/``rag_engine``) remain
authoritative; these settings just let an operator change the *starting* values
per environment without editing code or redeploying.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_DEFAULTS = _REPO_ROOT / ".env.defaults"
_ENV_LOCAL = _REPO_ROOT / ".env"

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Deployment-tunable, non-secret settings for the app.

    Each field maps to an UPPER_SNAKE_CASE environment variable of the same name
    (case-insensitive). Change a value in ``.env`` (local) or the Streamlit Cloud
    Secrets console (deployed) and restart the app — no code change or redeploy.
    """

    model_config = SettingsConfigDict(
        env_file=(_ENV_DEFAULTS, _ENV_LOCAL),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Step 1 · Crawl (crawl4md) ────────────────────────────────────────────
    # Default *starting* values for the crawl form; users can still override any
    # of these per crawl in the UI. Changing them sets the deployed app's
    # out-of-the-box defaults.
    #
    # Pages to crawl before stopping (the crawl breadth).
    crawl_limit: int = 10
    # How many links deep to follow from each seed URL.
    crawl_max_depth: int = 5
    # Parallel page fetches. Higher = faster but more load and WAF risk.
    crawl_max_concurrent: int = 5
    # Pages buffered before each incremental flush to disk.
    crawl_flush_interval: int = 5
    # Polite delay (seconds) between page fetches.
    crawl_delay: float = 3.0
    # Extra retry rounds for failed pages (the crawler enforces a minimum of 2).
    crawl_max_retries: int = 5
    # Seconds to wait for late content after a page loads.
    crawl_wait_for: float = 3.0
    # Per-page navigation/extraction timeout, in seconds.
    crawl_timeout: float = 60.0
    # Maximum size (MB) of a single extracted page file (larger pages are split).
    crawl_max_file_size_mb: float = 10.0
    # Lines of activity log retained for the live crawl view.
    crawl_activity_log_size: int = 10

    # ── Step 2 · Vector index (vector_indexer) ───────────────────────────────
    # Tokens per chunk. Larger keeps more context together but retrieves coarser
    # matches; smaller is more precise but produces more chunks.
    vector_chunk_size: int = 600
    # Overlap between adjacent chunks, so context is not cut at boundaries.
    vector_chunk_overlap: int = 100
    # Default embedding vector size. Must be supported by the chosen model;
    # smaller = cheaper/faster search, larger = potentially higher quality.
    vector_embedding_dimension: int = 512

    # ── Steps 3-5 · RAG (rag_engine) ─────────────────────────────────────────
    # Chunks retrieved as context for QA/conversational answers. More = broader
    # context but more tokens/noise.
    rag_top_k: int = 4
    # Default number of ranked matches shown on the Semantic Search page.
    semantic_search_top_n: int = 5

    # ── Session lifecycle ────────────────────────────────────────────────────
    # Days an inactive browser session's files are kept before the startup
    # cleanup deletes them. Loading or crawling in a session resets its clock.
    session_retention_days: int = 7

    # ── App UI limits ────────────────────────────────────────────────────────
    # Largest file (MB) the app will serve as a download (above this it is
    # shown but view-only).
    ui_download_limit_mb: int = 50
    # Largest inline text preview (KB) before previews are truncated.
    ui_preview_limit_kb: int = 256


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (loaded once)."""
    return Settings()
