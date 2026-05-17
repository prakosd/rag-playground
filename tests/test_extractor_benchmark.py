from __future__ import annotations

import os

import pytest

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor

_RUN_BENCHMARKS_ENV = "CRAWL4MD_RUN_BENCHMARKS"
_BENCHMARK_CARD_COUNT = 120
_EXPECTED_LAST_PRODUCT = f"Phone {_BENCHMARK_CARD_COUNT - 1}"


@pytest.mark.skipif(
    os.getenv(_RUN_BENCHMARKS_ENV) != "1",
    reason=f"Set {_RUN_BENCHMARKS_ENV}=1 to run the manual extractor benchmark.",
)
def test_main_content_extraction_manual_benchmark() -> None:
    cards = "".join(
        f'<article class="card"><h2>Phone {index}</h2>'
        f"<p>Detailed product copy for benchmark phone {index} with enough visible text.</p>"
        f"<p>from ${index + 1}.00/mth</p></article>"
        for index in range(_BENCHMARK_CARD_COUNT)
    )
    html = f"<html><head><title>Phones</title></head><body><main>{cards}</main></body></html>"
    extractor = ContentExtractor(PageConfig(extract_main_content=True, exclude_tags=[]))
    result = CrawlResult(url="https://example.com/phones", html=html, success=True)

    page = extractor._extract_page(result)

    assert _EXPECTED_LAST_PRODUCT in page.markdown
