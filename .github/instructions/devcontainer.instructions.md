---
description: "Use when editing the dev container, pyproject.toml, or adding/removing Python or system dependencies. Covers shm size, Tesseract, Streamlit auto-start, port 8501, apt source fixes, and setup order."
applyTo: ".devcontainer/**, pyproject.toml"
---

# Dev Environment & Dependencies

Dev container is defined in `.devcontainer/devcontainer.json` (Python 3.12 + Chromium via Playwright + Tesseract OCR + Streamlit app forwarding).

## Constraints

- `--shm-size=2g` is required — Chromium crashes with Docker's default 64 MB `/dev/shm`.
- Tesseract `eng` + `msa` are pre-installed to match `PageConfig.ocr_languages` defaults.
- The yarn apt source is removed before `apt-get update` (expired GPG key in the base image).
- Setup order: `pip install -e '.[dev]' -e 'apps/streamlit[dev]'` → `playwright install --with-deps chromium` → `crawl4ai-setup`.
- Port `8501` is forwarded for the Streamlit app and should keep the `Streamlit crawl4md app` label.
- `postAttachCommand` starts Streamlit with `python -m streamlit run apps/streamlit/streamlit_app.py --server.address=0.0.0.0 --server.port=8501`; keep `0.0.0.0` so forwarded ports work from containers and Codespaces.

## Dependencies

Core library dependencies live in the root `pyproject.toml`. Streamlit app dependencies, including `streamlit`, live in `apps/streamlit/pyproject.toml`.

When adding or removing a Python or system dependency, also update `.devcontainer/devcontainer.json` to keep the image in sync.
