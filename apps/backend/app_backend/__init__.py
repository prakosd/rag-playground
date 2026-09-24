"""FastAPI backend exposing the rag-playground libraries over HTTP.

This is an **additive** deployable: it reuses ``rag_engine`` (and the shared
``artifact_store`` path guard) without changing the Streamlit app or the
libraries. The Streamlit frontend keeps working in-process; it can optionally call
this service when ``BACKEND_MODE=http`` (see the app's ``backend_client``).
"""

from __future__ import annotations

from app_backend.main import create_app

__all__ = ["create_app"]
