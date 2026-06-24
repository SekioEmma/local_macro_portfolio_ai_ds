from __future__ import annotations

from pathlib import Path

import pytest

from app_backend.schemas.search_external import SearchResult
from app_backend.services.search_result_classifier import ResultCategory, classify


def _result(
    url: str,
    *,
    title: str = "Macro result",
    snippet: str = "Reference page",
    domain: str = "example.com",
) -> SearchResult:
    return SearchResult(url=url, title=title, snippet=snippet, domain=domain)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(
            _result("https://fred.stlouisfed.org/series/CPIAUCSL"),
            ResultCategory.HISTORICAL_DATA,
            id="fred",
        ),
        pytest.param(
            _result("https://www.bls.gov/cpi/"),
            ResultCategory.HISTORICAL_DATA,
            id="bls-www",
        ),
        pytest.param(
            _result("https://api.bea.gov/data"),
            ResultCategory.HISTORICAL_DATA,
            id="bea-subdomain",
        ),
        pytest.param(
            _result("https://TREASURY.GOV/resource-center/data-chart-center/"),
            ResultCategory.HISTORICAL_DATA,
            id="treasury-case",
        ),
        pytest.param(
            _result(
                "https://fred.stlouisfed.org/release.pdf",
                title="FOMC minutes",
                snippet="statement",
            ),
            ResultCategory.HISTORICAL_DATA,
            id="historical-before-policy-pdf",
        ),
        pytest.param(
            _result("https://download.bls.gov/pub/time.series/cu/data.txt"),
            ResultCategory.HISTORICAL_DATA,
            id="bls-download-subdomain",
        ),
        pytest.param(
            _result(
                "https://www.federalreserve.gov/newsevents/speech/powell20260101.htm",
                title="Speech by Chair",
            ),
            ResultCategory.POLICY_DOC,
            id="fed-speech-title-path",
        ),
        pytest.param(
            _result(
                "https://federalreserve.gov/monetarypolicy/fomcminutes20260101.htm",
                title="Meeting minutes",
            ),
            ResultCategory.POLICY_DOC,
            id="fed-minutes",
        ),
        pytest.param(
            _result(
                "https://www.federalreserve.gov/monetarypolicy/fomcstatement20260101.htm",
                snippet="FOMC statement",
            ),
            ResultCategory.POLICY_DOC,
            id="fomc-statement",
        ),
        pytest.param(
            _result(
                "https://imf.org/en/News/Articles/2026/06/01/statement",
                title="IMF staff statement",
            ),
            ResultCategory.POLICY_DOC,
            id="imf-statement",
        ),
        pytest.param(
            _result(
                "https://worldbank.org/en/news/speech/2026/address",
                snippet="A development speech",
            ),
            ResultCategory.POLICY_DOC,
            id="world-bank-speech",
        ),
        pytest.param(
            _result(
                "https://federalreserve.gov/aboutthefed.htm",
                title="About the Federal Reserve",
            ),
            ResultCategory.DISCARD,
            id="plain-fed-page",
        ),
        pytest.param(
            _result("https://imf.org/en/About", title="About the IMF"),
            ResultCategory.DISCARD,
            id="plain-imf-page",
        ),
        pytest.param(
            _result("https://worldbank.org/en/who-we-are", title="Who we are"),
            ResultCategory.DISCARD,
            id="plain-world-bank-page",
        ),
        pytest.param(
            _result("https://nber.org/system/files/working_papers/w12345/w12345.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="nber-pdf",
        ),
        pytest.param(
            _result("https://www.bis.org/publ/work999.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="bis-pdf",
        ),
        pytest.param(
            _result("https://brookings.edu/wp-content/uploads/report.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="brookings-pdf",
        ),
        pytest.param(
            _result("https://piie.com/sites/default/files/documents/pb26-1.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="piie-pdf",
        ),
        pytest.param(
            _result("https://bruegel.org/sites/default/files/report.PDF"),
            ResultCategory.RESEARCH_REPORT,
            id="bruegel-pdf-uppercase",
        ),
        pytest.param(
            _result("https://cepr.org/publications/dp12345.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="cepr-pdf",
        ),
        pytest.param(
            _result("https://imf.org/-/media/Files/Publications/WP/2026/wp261.ashx.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="imf-pdf",
        ),
        pytest.param(
            _result("https://worldbank.org/en/research/report.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="world-bank-pdf",
        ),
        pytest.param(
            _result("https://federalreserve.gov/econres/feds/files/2026001pap.pdf"),
            ResultCategory.RESEARCH_REPORT,
            id="fed-research-pdf",
        ),
        pytest.param(
            _result("https://www.nber.org/papers/w12345"),
            ResultCategory.DISCARD,
            id="nber-non-pdf",
        ),
        pytest.param(
            _result("https://reuters.com/world/report.pdf"),
            ResultCategory.ONE_SHOT_NEWS,
            id="reuters-pdf-not-report",
        ),
        pytest.param(
            _result(
                "https://federalreserve.gov/monetarypolicy/files/fomcminutes.pdf",
                title="Meeting minutes",
            ),
            ResultCategory.POLICY_DOC,
            id="policy-pdf-priority",
        ),
        pytest.param(
            _result("https://reuters.com/markets/rates/us-yields"),
            ResultCategory.ONE_SHOT_NEWS,
            id="reuters",
        ),
        pytest.param(
            _result("https://www.bloomberg.com/news/articles/example"),
            ResultCategory.ONE_SHOT_NEWS,
            id="bloomberg-www",
        ),
        pytest.param(
            _result("https://markets.ft.com/data/bonds"),
            ResultCategory.ONE_SHOT_NEWS,
            id="ft-subdomain",
        ),
        pytest.param(
            _result("https://oilprice.com/Energy/Oil-Prices/example.html"),
            ResultCategory.ONE_SHOT_NEWS,
            id="oilprice",
        ),
        pytest.param(
            _result("https://www.reuters.com/"),
            ResultCategory.ONE_SHOT_NEWS,
            id="news-home-page",
        ),
        pytest.param(
            _result("https://unknown.example/report.pdf"),
            ResultCategory.DISCARD,
            id="unknown-domain",
        ),
        pytest.param(
            _result("https://reuters.com.evil.com/markets"),
            ResultCategory.DISCARD,
            id="news-suffix-attack",
        ),
        pytest.param(
            _result("https://fred.stlouisfed.org.evil.com/series/CPIAUCSL"),
            ResultCategory.DISCARD,
            id="historical-suffix-attack",
        ),
        pytest.param(
            _result("https://bls.gov.example.com/cpi"),
            ResultCategory.DISCARD,
            id="bls-suffix-attack",
        ),
        pytest.param(
            _result("https://user:pass@reuters.com/markets"),
            ResultCategory.DISCARD,
            id="userinfo",
        ),
        pytest.param(
            _result("https://reuters.com/markets?utm_source=x"),
            ResultCategory.DISCARD,
            id="query",
        ),
        pytest.param(
            _result("https://reuters.com/markets#section"),
            ResultCategory.DISCARD,
            id="fragment",
        ),
        pytest.param(
            _result("ftp://reuters.com/markets"),
            ResultCategory.DISCARD,
            id="ftp",
        ),
        pytest.param(
            _result("file:///tmp/report.pdf"),
            ResultCategory.DISCARD,
            id="file",
        ),
        pytest.param(
            _result("javascript:alert(1)"),
            ResultCategory.DISCARD,
            id="javascript",
        ),
        pytest.param(
            _result("https:///missing-host"),
            ResultCategory.DISCARD,
            id="missing-host",
        ),
        pytest.param(
            _result("https://[::1"),
            ResultCategory.DISCARD,
            id="malformed-url",
        ),
        pytest.param(
            _result("https://reuters.com:bad/markets"),
            ResultCategory.DISCARD,
            id="invalid-port",
        ),
        pytest.param(
            _result("https://reuters.com:99999/markets"),
            ResultCategory.DISCARD,
            id="out-of-range-port",
        ),
        pytest.param(
            _result(
                "https://fred.stlouisfed.org/series/GDP",
                domain="reuters.com",
            ),
            ResultCategory.HISTORICAL_DATA,
            id="fake-result-domain-ignored",
        ),
        pytest.param(
            _result("https://example.com/research.pdf"),
            ResultCategory.DISCARD,
            id="unsupported-pdf-domain",
        ),
    ],
)
def test_classify_search_result(result: SearchResult, expected: ResultCategory) -> None:
    assert classify(result) is expected


def test_classify_does_not_mutate_input() -> None:
    result = _result(
        "https://www.federalreserve.gov/newsevents/speech/example.htm",
        title="Speech",
        snippet="Monetary policy remarks",
        domain="fake.example",
    )
    before = result.model_dump()

    assert classify(result) is ResultCategory.POLICY_DOC
    assert result.model_dump() == before


def test_result_category_values_are_fixed() -> None:
    assert {category.value for category in ResultCategory} == {
        "one_shot_news",
        "policy_doc",
        "research_report",
        "historical_data",
        "discard",
    }


def test_classifier_source_has_no_external_runtime_hooks() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src"
        / "app_backend"
        / "services"
        / "search_result_classifier.py"
    )
    source = source_path.read_text(encoding="utf-8")
    forbidden_tokens = [
        "httpx",
        "requests",
        "aiohttp",
        "sqlite3",
        "socket",
        "open(",
        "os.environ",
        "os.getenv",
        "FastAPI",
        "main.py",
        "target allocation",
        "return prediction",
    ]
    forbidden_tokens.extend(["tr" + "ade", "b" + "uy", "s" + "ell", "prob" + "ability"])

    assert not any(token in source for token in forbidden_tokens)
