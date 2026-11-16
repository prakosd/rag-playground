"""Deployment-tunable settings for the FastAPI backend."""

from __future__ import annotations

from functools import lru_cache

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


@lru_cache(maxsize=1)
def get_backend_settings() -> BackendSettings:
    return BackendSettings()
