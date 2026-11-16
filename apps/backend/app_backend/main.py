"""FastAPI application factory for the rag-playground backend."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from app_backend.auth import require_backend_auth
from app_backend.crawl_api import router as crawl_router
from app_backend.index_api import router as index_router
from app_backend.rag_api import router as rag_router


def create_app() -> FastAPI:
    """Build the backend app: an open health probe plus the (optionally authed) routes."""
    app = FastAPI(title="rag-playground backend", version="0.1.0")

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
