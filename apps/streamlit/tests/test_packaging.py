from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES_FILE = _REPO_ROOT / "packages.txt"
_REQUIREMENTS_FILE = _REPO_ROOT / "apps" / "streamlit" / "requirements.txt"


def _nonblank_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# Risk: Streamlit Community Cloud feeds packages.txt straight to `apt-get install` and
# does NOT support `#` comments, so a comment line breaks the apt step. Chromium must be
# present so its shared libraries are installed for Playwright. Type: unit.
def test_packages_file_has_no_comments_and_installs_chromium() -> None:
    lines = _nonblank_lines(_PACKAGES_FILE)

    assert "chromium" in lines
    assert not any(line.startswith("#") for line in lines)


# Risk: the rag-playground packages are unpublished, so Streamlit Cloud must install them
# from the checkout (root package first, then the app). Type: unit.
def test_requirements_install_local_root_and_app() -> None:
    lines = _nonblank_lines(_REQUIREMENTS_FILE)
    active = [line for line in lines if not line.startswith("#")]

    assert any(line.startswith(".[") for line in active)
    assert "./apps/streamlit" in active


# Risk: a fresh Streamlit Cloud build can resolve a protobuf runtime newer than the
# chromadb/opentelemetry generated *_pb2 code, aborting vector indexing with
# "Descriptors cannot be created directly". requirements.txt brackets protobuf to the
# supported range; guard the pin so the fix is not silently dropped. Type: unit.
def test_requirements_pin_protobuf_runtime() -> None:
    lines = _nonblank_lines(_REQUIREMENTS_FILE)
    active = [line for line in lines if not line.startswith("#")]

    pins = [line for line in active if line.replace(" ", "").lower().startswith("protobuf")]
    assert pins, "expected a protobuf version pin in requirements.txt"
    normalized = pins[0].replace(" ", "").lower()
    assert ">=5" in normalized and "<7" in normalized
