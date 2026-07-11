"""Translation catalog for the crawl4md Streamlit app.

Each supported language lives in its own module (e.g. ``en.py``, ``id.py``).
To add a new language:
  1. Create ``<lang_code>.py`` in this package with a ``STRINGS_<CODE>`` dict.
  2. Import it here and add it to ``CATALOG``.

Call ``get_strings(lang)`` to retrieve the active language's translations.
"""

from __future__ import annotations

from collections.abc import Mapping

from app_support.i18n._types import Strings
from app_support.i18n.en import STRINGS_EN
from app_support.i18n.id import STRINGS_ID

__all__ = [
    "CATALOG",
    "Strings",
    "STRINGS_EN",
    "STRINGS_ID",
    "get_strings",
    "localize_message",
]

CATALOG: dict[str, Strings] = {
    "EN": STRINGS_EN,
    "ID": STRINGS_ID,
}


def get_strings(lang: str) -> Strings:
    """Return the translation catalog for *lang*, falling back to English."""
    normalized_lang = str(lang).strip().upper()
    return CATALOG.get(normalized_lang, STRINGS_EN)


def localize_message(strings: Strings, message: Mapping[str, object]) -> str:
    """Localize a structured library message for display.

    *message* is the dict form of a library ``LibraryMessage`` (``code`` /
    ``text`` / ``params``). When the active language has a template for the
    message ``code`` it is formatted with the message params; otherwise the
    library-provided English ``text`` is returned, so the libraries remain the
    single source of truth for wording and any UI can localize incrementally.
    """
    code = str(message.get("code", ""))
    default_text = str(message.get("text", ""))
    template = strings["MESSAGE_CODES"].get(code)
    if not template:
        return default_text
    params = message.get("params")
    if isinstance(params, Mapping):
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return default_text
    return template
