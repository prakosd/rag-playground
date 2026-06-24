from __future__ import annotations

import pytest

from crawl4md_streamlit.settings import Settings, get_settings


def test_settings_use_code_defaults_without_env_files() -> None:
    settings = Settings(_env_file=None)

    assert settings.rag_top_k == 4
    assert settings.semantic_search_top_n == 5
    assert settings.semantic_search_default_tab == "raw"
    assert settings.semantic_search_default_mode == "similarity"
    assert settings.semantic_search_min_score_percent == 0
    assert settings.semantic_search_fetch_k == 20
    assert settings.semantic_search_mmr_lambda == 0.5
    assert settings.vector_chunk_size == 600
    assert settings.vector_embedding_dimension == 512
    assert settings.vector_default_embedding_model == "all-MiniLM-L6-v2"
    assert "all-MiniLM-L6-v2" in settings.vector_embedding_models
    assert settings.crawl_timeout == 60.0
    assert settings.crawl_max_file_size_mb == 10.0
    assert settings.ui_download_limit_mb == 50
    assert settings.session_retention_days == 7


def test_settings_read_overrides_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_TOP_K", "9")
    monkeypatch.setenv("VECTOR_CHUNK_SIZE", "900")
    monkeypatch.setenv("UI_PREVIEW_LIMIT_KB", "512")
    monkeypatch.setenv("SESSION_RETENTION_DAYS", "30")
    monkeypatch.setenv("SEMANTIC_SEARCH_DEFAULT_TAB", "preview")

    settings = Settings(_env_file=None)

    assert settings.rag_top_k == 9
    assert settings.vector_chunk_size == 900
    assert settings.ui_preview_limit_kb == 512
    assert settings.session_retention_days == 30
    assert settings.semantic_search_default_tab == "preview"


def test_settings_ignore_unrelated_secret_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # Secret credentials live alongside config in ".env"; the settings model must
    # ignore them rather than fail on unknown keys.
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-be-ignored")

    settings = Settings(_env_file=None)

    assert not hasattr(settings, "aws_secret_access_key")


def test_get_settings_is_cached_singleton() -> None:
    assert get_settings() is get_settings()
