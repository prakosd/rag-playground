from __future__ import annotations

import os
from pathlib import Path

import pytest

from vector_indexer import (
    DEFAULT_LOCAL_MODEL,
    EMBEDDING_MODEL_INFOS,
    EMBEDDING_MODEL_OPTIONS,
    get_embedding_model_info,
)
from vector_indexer.embeddings.local import _CA_BUNDLE_ENV_VARS, _propagate_ca_bundle_env


def test_every_offered_model_has_catalog_metadata() -> None:
    for model_id in EMBEDDING_MODEL_OPTIONS:
        info = get_embedding_model_info(model_id)
        assert info is not None
        assert info.model_id == model_id


def test_get_embedding_model_info_returns_none_for_unknown() -> None:
    assert get_embedding_model_info("nonexistent/model") is None


def test_local_model_is_local_with_fixed_dimension() -> None:
    info = get_embedding_model_info(DEFAULT_LOCAL_MODEL)

    assert info is not None
    assert info.kind == "local"
    assert info.requires_api_key is False
    assert info.one_time_download is True
    assert info.supported_dimensions == (info.default_dimension,)


def test_cloud_models_require_api_keys() -> None:
    cloud = [info for info in EMBEDDING_MODEL_INFOS if info.kind == "cloud"]

    assert cloud
    assert all(info.requires_api_key for info in cloud)


def test_discrete_dimension_models_default_to_a_supported_value() -> None:
    for info in EMBEDDING_MODEL_INFOS:
        if info.supported_dimensions is not None:
            assert info.default_dimension in info.supported_dimensions


def test_range_dimension_models_keep_default_within_bounds() -> None:
    for info in EMBEDDING_MODEL_INFOS:
        if info.supported_dimensions is None:
            assert info.min_dimension is not None
            assert info.max_dimension is not None
            assert info.min_dimension <= info.default_dimension <= info.max_dimension


def test_propagate_ca_bundle_mirrors_configured_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "corp-ca.pem"
    bundle.write_text("cert", encoding="utf-8")
    for var in _CA_BUNDLE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))

    _propagate_ca_bundle_env()

    for var in _CA_BUNDLE_ENV_VARS:
        assert os.environ[var] == str(bundle)


def test_propagate_ca_bundle_is_a_noop_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _CA_BUNDLE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    _propagate_ca_bundle_env()

    assert all(var not in os.environ for var in _CA_BUNDLE_ENV_VARS)


def test_propagate_ca_bundle_does_not_override_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    primary = tmp_path / "primary.pem"
    primary.write_text("cert", encoding="utf-8")
    secondary = tmp_path / "secondary.pem"
    secondary.write_text("cert", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(primary))
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(secondary))
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)

    _propagate_ca_bundle_env()

    assert os.environ["SSL_CERT_FILE"] == str(primary)
    assert os.environ["REQUESTS_CA_BUNDLE"] == str(secondary)
    assert os.environ["CURL_CA_BUNDLE"] in {str(primary), str(secondary)}
