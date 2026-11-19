"""Deployment-tunable settings for the FastAPI backend."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from artifact_store import ensure_within_root
from fastapi import HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Non-secret backend configuration, read from the environment.

    ``artifacts_root`` is the filesystem root that request ``run_dir`` paths are
    resolved under (with containment), so a client can never reach outside it. In a
    cloud deployment point it at the shared volume the indexer writes to.
    """

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    artifacts_root: str = "outputs"
    # Optional shared secret; when set, every non-health route requires a matching
    # ``X-Backend-Token`` header (default empty = auth disabled, preserving local use).
    backend_auth_token: str = ""
    # When False (default), the backend strips script-injection keys (``js_code``) from an
    # incoming ``page_config`` so a networked caller cannot run arbitrary JS in the headless
    # browser; set True only for a trusted deployment that needs page scripting.
    allow_page_scripts: bool = False
    # When True (set it for a networked deployment), the backend forces the crawler's SSRF
    # guard on regardless of the incoming config, so a direct caller cannot disable it.
    block_private_networks: bool = False
    # Proxy URLs (comma-separated) the backend crawler routes through on retry rounds. Proxies
    # are a backend/deployment concern — the frontend never sends them — so configure them here
    # for a networked backend. May carry credentials; keep it secret and never log it.
    crawl_proxies: str = ""
    # When True, the initial crawl round also routes through CRAWL_PROXIES (else retries only).
    crawl_proxy_on_initial: bool = False


@lru_cache(maxsize=1)
def get_backend_settings() -> BackendSettings:
    return BackendSettings()


def resolve_within_artifacts(relative: str) -> Path:
    """Resolve *relative* under the configured artifacts root, rejecting any escape with 400.

    Shared by the crawl/index/rag routers so a request path can never reach outside the root
    (``..`` escapes and absolute paths both yield an HTTP 400).
    """
    root = Path(get_backend_settings().artifacts_root).resolve()
    try:
        return ensure_within_root(root, root / relative)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
