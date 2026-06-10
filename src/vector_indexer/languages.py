"""Lucene-style analyzer language options for the indexing language hint.

The list mirrors the languages for which Apache Lucene ships a dedicated
analyzer. ``DEFAULT_LANGUAGE`` is used when a caller does not specify one.
"""

from __future__ import annotations

__all__ = ["DEFAULT_LANGUAGE", "LUCENE_LANGUAGES", "is_supported_language"]

DEFAULT_LANGUAGE = "english"

LUCENE_LANGUAGES: tuple[str, ...] = (
    "arabic",
    "armenian",
    "basque",
    "bengali",
    "brazilian",
    "bulgarian",
    "catalan",
    "chinese",
    "czech",
    "danish",
    "dutch",
    "english",
    "estonian",
    "finnish",
    "french",
    "galician",
    "german",
    "greek",
    "hindi",
    "hungarian",
    "indonesian",
    "irish",
    "italian",
    "latvian",
    "lithuanian",
    "norwegian",
    "persian",
    "portuguese",
    "romanian",
    "russian",
    "sorani",
    "spanish",
    "swedish",
    "thai",
    "turkish",
)


def is_supported_language(language: str) -> bool:
    """Return True when *language* is a known Lucene analyzer language."""
    return language.strip().lower() in LUCENE_LANGUAGES
