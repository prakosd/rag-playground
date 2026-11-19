"""FastAPI application factory for the rag-playground backend."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from log4py import get_logger

from app_backend.auth import require_backend_auth
from app_backend.config import get_backend_settings
from app_backend.crawl_api import router as crawl_router
from app_backend.index_api import router as index_router
from app_backend.rag_api import router as rag_router

_logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Build the backend app: an open health probe plus the (optionally authed) routes."""
    app = FastAPI(title="rag-playground backend", version="0.1.0")

    if not get_backend_settings().backend_auth_token:
        _logger.warning(
            "BACKEND_AUTH_TOKEN is empty — the backend is unauthenticated. Set it (and serve "
            "over https) before exposing the backend on a network; leave it empty only for "
            "local, single-user use."
        )

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Optional shared-secret guard on every data route; /health stays open for probes.
    protected = [Depends(require_backend_auth)]
    app.include_router(rag_router, dependencies=protected)
    app.include_router(crawl_router, dependencies=protected)
    app.include_router(index_router, dependencies=protected)
    return app


app = create_app()
