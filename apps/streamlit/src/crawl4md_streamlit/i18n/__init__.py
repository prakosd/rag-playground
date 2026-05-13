"""Translation catalog for the crawl4md Streamlit app.

Each supported language lives in its own module (e.g. ``en.py``, ``id.py``).
To add a new language:
  1. Create ``<lang_code>.py`` in this package with a ``STRINGS_<CODE>`` dict.
  2. Import it here and add it to ``CATALOG``.

Call ``get_strings(lang)`` to retrieve the active language's translations.
"""

from __future__ import annotations

from crawl4md_streamlit.i18n._types import Strings
from crawl4md_streamlit.i18n.en import STRINGS_EN
from crawl4md_streamlit.i18n.id import STRINGS_ID

__all__ = ["CATALOG", "Strings", "STRINGS_EN", "STRINGS_ID", "get_strings"]

CATALOG: dict[str, Strings] = {
    "EN": STRINGS_EN,
    "ID": STRINGS_ID,
}


def get_strings(lang: str) -> Strings:
    """Return the translation catalog for *lang*, falling back to English."""
    normalized_lang = str(lang).strip().upper()
    return CATALOG.get(normalized_lang, STRINGS_EN)
