"""Make the ``app_backend`` package importable when running the backend tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
