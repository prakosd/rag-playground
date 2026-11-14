"""Tests for the crawl run-settings (settings.json) writer."""

from __future__ import annotations

import json
from pathlib import Path

from crawl4md._internal.run_settings import SETTINGS_FILENAME, write_crawl_settings
from crawl4md.config import CrawlerConfig, PageConfig


def _run_metadata() -> dict[str, object]:
    return {
        "crawl_start_datetime": "2026-01-02T03:04:05",
        "session_id": "session_demo",
        "crawl_parameters": {
            "crawler_config": CrawlerConfig(urls=["https://example.com"]).model_dump(mode="json"),
            "page_config": PageConfig().model_dump(mode="json"),
        },
    }


# Risk: a crawl must leave a readable settings.json capturing its parameters so the
# user can see/reproduce them without opening content files. Type: unit.
def test_write_crawl_settings_writes_json(tmp_path: Path) -> None:
    path = write_crawl_settings(tmp_path, _run_metadata())

    assert path == tmp_path / SETTINGS_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["crawl_start_datetime"] == "2026-01-02T03:04:05"
    assert data["session_id"] == "session_demo"
    assert data["crawl_parameters"]["crawler_config"]["limit"] == 100


# Risk: settings.json must never leak credentials; secret headers are excluded from the
# config dump upstream, so they must not appear in the file. Type: unit.
def test_write_crawl_settings_excludes_secret_headers(tmp_path: Path) -> None:
    config = CrawlerConfig(
        urls=["https://example.com"], secret_headers={"Authorization": "Bearer super-secret"}
    )
    metadata = {
        "crawl_start_datetime": "2026-01-02T03:04:05",
        "session_id": "session_demo",
        "crawl_parameters": {"crawler_config": config.model_dump(mode="json")},
    }

    path = write_crawl_settings(tmp_path, metadata)

    assert path is not None
    assert "super-secret" not in path.read_text(encoding="utf-8")


# Risk: proxy URLs can embed credentials and are excluded from the config dump, so they must
# not appear in settings.json either. Type: unit.
def test_write_crawl_settings_excludes_proxies(tmp_path: Path) -> None:
    config = CrawlerConfig(urls=["https://example.com"], proxies=["http://user:pass@host:8080"])
    metadata = {
        "crawl_start_datetime": "2026-01-02T03:04:05",
        "session_id": "session_demo",
        "crawl_parameters": {"crawler_config": config.model_dump(mode="json")},
    }

    path = write_crawl_settings(tmp_path, metadata)

    assert path is not None
    assert "user:pass" not in path.read_text(encoding="utf-8")


# Risk: the file is informational, so a write failure must not crash the crawl. Type: unit.
def test_write_crawl_settings_returns_none_on_oserror(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert write_crawl_settings(missing, _run_metadata()) is None
    assert not (missing / SETTINGS_FILENAME).exists()
