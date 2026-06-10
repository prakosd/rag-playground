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
- Setup order: `pip install -e '.[dev,vector,bedrock,openai]' -e 'apps/streamlit[dev]'` → `playwright install --with-deps chromium` → `crawl4ai-setup`.
- Port `8501` is forwarded for the Streamlit app and should keep the `Streamlit crawl4md app` label.
- `postAttachCommand` starts Streamlit with `python -m streamlit run apps/streamlit/streamlit_app.py --server.address=0.0.0.0 --server.port=8501`; keep `0.0.0.0` so forwarded ports work from containers and Codespaces.
- `ANONYMIZED_TELEMETRY=False` is set in `containerEnv` to disable ChromaDB telemetry.

## Dependencies

Core library dependencies live in the root `pyproject.toml`. The `vector_indexer`
library ships within the same distribution; its backends are opt-in extras:

- `vector` → `chromadb`, `langchain-text-splitters` (chunking + vector store).
- `bedrock` → `boto3` (Amazon Titan embeddings, the default model).
- `openai` → `openai` (OpenAI embeddings).

Streamlit app dependencies, including `streamlit`, live in `apps/streamlit/pyproject.toml`;
the app depends on `crawl4md[vector,bedrock]` so installing it pulls the indexing backends.

Cloud embedding credentials are read from the environment (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `OPENAI_API_KEY`). See `.env.example`. In
Codespaces/CI, set them as environment secrets/variables; never commit real values.
The offline default embedding model needs no credentials.

When adding or removing a Python or system dependency, also update `.devcontainer/devcontainer.json` to keep the image in sync.
