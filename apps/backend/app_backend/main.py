"""FastAPI application factory for the rag-playground backend."""

from __future__ import annotations

from fastapi import FastAPI

from app_backend.rag_api import router as rag_router


def create_app() -> FastAPI:
    """Build the backend app: a health probe plus the RAG read routes."""
    app = FastAPI(title="rag-playground backend", version="0.1.0")

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(rag_router)
    return app


app = create_app()
