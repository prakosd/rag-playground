"""Tests for the optional backend shared-secret auth."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app_backend import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _enable_auth(monkeypatch: pytest.MonkeyPatch, token: str = "s3cret") -> None:
    monkeypatch.setattr(
        "app_backend.auth.get_backend_settings",
        lambda: SimpleNamespace(backend_auth_token=token),
    )


def test_routes_open_when_no_token_configured(client: TestClient) -> None:
    # Default (empty token) preserves local/in-process use — no header required.
    assert client.post("/crawl/none/cancel").json() == {"cancelled": False}


def test_health_stays_open_even_with_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)
    assert client.get("/health").status_code == 200  # probes never need the token


def test_protected_route_rejects_missing_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)
    assert client.post("/crawl/none/cancel").status_code == 401


def test_protected_route_rejects_wrong_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)
    resp = client.post("/crawl/none/cancel", headers={"X-Backend-Token": "nope"})
    assert resp.status_code == 401


def test_protected_route_accepts_correct_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)
    resp = client.post("/crawl/none/cancel", headers={"X-Backend-Token": "s3cret"})
    assert resp.status_code == 200
    assert resp.json() == {"cancelled": False}


def test_all_data_routers_are_guarded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_auth(monkeypatch)
    # rag, crawl, and index routers all require the token; a valid body still 401s without it.
    assert client.post("/rag/search", json={"run_dir": "x", "query": "q"}).status_code == 401
    assert client.post("/index/none/cancel").status_code == 401
    assert client.post("/crawl/none/cancel").status_code == 401
