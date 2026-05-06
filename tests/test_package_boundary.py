from __future__ import annotations

import pkgutil

import crawl4md

_STREAMLIT_CONTROL_MODULE = "streamlit_controls"
_STREAMLIT_SUPPORT_MODULE = "streamlit_support"


def test_public_api_excludes_streamlit_helpers() -> None:
    public_exports = set(crawl4md.__all__)

    assert _STREAMLIT_CONTROL_MODULE not in public_exports
    assert _STREAMLIT_SUPPORT_MODULE not in public_exports


def test_core_package_excludes_streamlit_helper_modules() -> None:
    module_names = {module.name for module in pkgutil.iter_modules(crawl4md.__path__)}

    assert _STREAMLIT_CONTROL_MODULE not in module_names
    assert _STREAMLIT_SUPPORT_MODULE not in module_names
