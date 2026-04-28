---
description: "Use when editing the dev container, pyproject.toml, or adding/removing Python or system dependencies. Covers shm size, Tesseract, apt source fixes, and setup order."
applyTo: ".devcontainer/**, pyproject.toml"
---

# Dev Environment & Dependencies

Dev container is defined in `.devcontainer/devcontainer.json` (Python 3.12 + Chromium via Playwright + Tesseract OCR).

## Constraints

- `--shm-size=2g` is required — Chromium crashes with Docker's default 64 MB `/dev/shm`.
- Tesseract `eng` + `msa` are pre-installed to match `PageConfig.ocr_languages` defaults.
- The yarn apt source is removed before `apt-get update` (expired GPG key in the base image).
- Setup order: `pip install -e '.[dev]'` → `playwright install --with-deps chromium` → `crawl4ai-setup`.

## Dependencies

crawl4ai, trafilatura, markdownify, pydantic, nest-asyncio, beautifulsoup4, mdformat + mdformat-gfm, pymupdf4llm, httpx. Full list in `pyproject.toml`.

When adding or removing a Python or system dependency, also review `.devcontainer/devcontainer.json` to keep the image in sync.
