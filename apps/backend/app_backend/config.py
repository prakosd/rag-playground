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


@lru_cache(maxsize=1)
def get_backend_settings() -> BackendSettings:
    return BackendSettings()
