from __future__ import annotations

from vector_indexer.languages import DEFAULT_LANGUAGE, LUCENE_LANGUAGES, is_supported_language


def test_default_language_is_listed() -> None:
    assert DEFAULT_LANGUAGE in LUCENE_LANGUAGES


def test_is_supported_language_is_case_insensitive() -> None:
    assert is_supported_language("English")
    assert is_supported_language(" french ")


def test_unknown_language_not_supported() -> None:
    assert not is_supported_language("klingon")
