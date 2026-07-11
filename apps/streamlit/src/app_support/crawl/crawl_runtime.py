"""Runtime browser setup for the Streamlit crawl workflow.

Streamlit Community Cloud installs Python packages from ``requirements.txt`` and
apt packages from ``packages.txt``, but it has no build-time hook to run
``playwright install``. crawl4ai drives Playwright's own Chromium build (not the
apt ``chromium`` binary), so that browser must be downloaded once at runtime. The
apt ``chromium`` package in ``packages.txt`` provides the shared libraries the
browser needs to launch.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from log4py import get_logger

# Streamlit Community Cloud checks the repository out under this path.
_STREAMLIT_CLOUD_ROOT = Path("/mount/src")
_INSTALL_COMMAND = (sys.executable, "-m", "playwright", "install", "chromium")

_browser_ready = False
_lock = threading.Lock()

_logger = get_logger(__name__)


def _on_streamlit_cloud() -> bool:
    return _STREAMLIT_CLOUD_ROOT.exists()


def _run_install() -> None:
    _logger.info("Installing Playwright Chromium (first run on this host)")
    subprocess.run(_INSTALL_COMMAND, check=False)
    _logger.info("Playwright Chromium install finished")


def ensure_playwright_browser() -> None:
    """Download Playwright's Chromium once per process when running on Streamlit Cloud."""
    global _browser_ready
    if _browser_ready or not _on_streamlit_cloud():
        return
    with _lock:
        if _browser_ready or not _on_streamlit_cloud():
            return
        _run_install()
        _browser_ready = True
