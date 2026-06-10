# Development

← Back to [README](../README.md)

## Setup

```bash
pip install -e ".[dev,vector,bedrock,openai]" -e "apps/streamlit[dev]"
```

## Tests and lint

```bash
# Core library (includes artifact_store and vector_indexer)
python -m pytest tests/ -q
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/

# Streamlit app
python -m pytest apps/streamlit/tests/ -q
python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
```

- Core tests (including `artifact_store` and `vector_indexer`) live in `tests/`.
- Streamlit app helper tests live in `apps/streamlit/tests/`.
- Tests use mocked HTTP — no real network requests are made, and no embedding
  models are downloaded (use fakes / explicit embeddings).

## Conventions

- Python 3.10+, type hints on all public APIs, Pydantic v2.
- No inline magic values — use `_UPPER_SNAKE_CASE` constants and module-level
  compiled regexes.
- Keep the libraries UI-independent: `crawl4md`, `artifact_store`, and
  `vector_indexer` must not import Streamlit. Boundary tests enforce this.
- All user-facing Streamlit text lives in the `i18n` catalog (English + Indonesian)
  and is referenced via `get_strings()` — never hardcoded in components.

## Component guides

| Component | Guide |
|---|---|
| Core crawler | [src/crawl4md/README.md](../src/crawl4md/README.md) |
| Shared foundation | [src/artifact_store/README.md](../src/artifact_store/README.md) |
| Vector indexer | [src/vector_indexer/README.md](../src/vector_indexer/README.md) |
| Streamlit app | [apps/streamlit/README.md](../apps/streamlit/README.md) |
| Building another UI | [BUILDING_ANOTHER_UI.md](BUILDING_ANOTHER_UI.md) |

## Agent skills

Development guidance in this repository uses external agent skills:

- Streamlit app: [Developing with Streamlit](https://skills.sh/streamlit/agent-skills/developing-with-streamlit)
- Async Python patterns: [async-python-patterns](https://www.skills.sh/wshobson/agents/async-python-patterns)
- crawl4md library performance: [python-performance-optimization](https://www.skills.sh/wshobson/agents/python-performance-optimization)
- Python design patterns: [python-design-patterns](https://www.skills.sh/wshobson/agents/python-design-patterns)
- Python testing patterns: [python-testing-patterns](https://www.skills.sh/wshobson/agents/python-testing-patterns)
- Python project structure: [python-project-structure](https://www.skills.sh/wshobson/agents/python-project-structure)
