# Streamlit frontend — crawl-capable (bundles Chromium + Tesseract for Step 1).
# Mirrors the .devcontainer setup. Run with a large /dev/shm for Chromium:
#   docker build -t rag-playground-frontend .
#   docker run --shm-size=2g -p 8501:8501 -v app-data:/data/sessions \
#     -e SESSIONS_ROOT=/data/sessions rag-playground-frontend
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANONYMIZED_TELEMETRY=False \
    PIP_NO_CACHE_DIR=1

# Tesseract OCR (eng + msa) for PDF OCR during crawling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-msa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install every library extra + the Streamlit app, then the Chromium browser (with
# its OS deps) and crawl4ai's one-time setup. Dev tools are intentionally omitted.
RUN pip install --upgrade pip \
    && pip install -e '.[all]' -e 'apps/streamlit' \
    && playwright install --with-deps chromium \
    && crawl4ai-setup

EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "apps/streamlit/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
