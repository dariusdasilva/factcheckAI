"""C4 acceptance — Source fetch: hop-2 ``S*`` + the ``Source`` crawl cache.

"Cache hit = no refetch (double-call test)" (WORK_CHUNKS.md, Chunk C). Also covers
text extraction (HTML + PDF routing) and the §5 rule that a failed source is cached
with ``fetch_status='error'`` rather than raised.
"""

from __future__ import annotations

import pytest
from conftest import load_text_fixture

from apps.checks.models import EvidenceFetchStatus, Source
from apps.sources.citations import CitedSource
from apps.sources.source_fetch import (
    extract_html_text,
    extract_text,
    fetch_source,
    fetch_sources,
    is_primary_source,
    rank_citations,
)

WEBMD_URL = "https://www.webmd.com/diet/health-benefits-coffee"


def _citation(url: str, domain: str) -> CitedSource:
    return CitedSource(url=url, domain=domain, source_articles=("Coffee",))


@pytest.mark.django_db
def test_cache_hit_does_not_refetch(source_pages, requests_mock, fast_session):
    citation = _citation(WEBMD_URL, "webmd.com")

    first = fetch_source(citation, session=fast_session)
    second = fetch_source(citation, session=fast_session)

    assert first.pk == second.pk
    page_calls = [r for r in requests_mock.request_history if r.url == WEBMD_URL]
    assert len(page_calls) == 1  # second call served from the cache
    row = Source.objects.get(url=WEBMD_URL)
    assert row.fetch_status == EvidenceFetchStatus.FETCHED
    assert "antioxidants" in row.text_extract


@pytest.mark.django_db
def test_failed_fetch_is_cached_as_error_not_raised(source_pages, requests_mock, fast_session):
    url = "https://www.webmd.com/paywalled"
    requests_mock.get(url, status_code=403)
    citation = _citation(url, "webmd.com")

    row = fetch_source(citation, session=fast_session)

    assert row.fetch_status == EvidenceFetchStatus.ERROR
    assert row.text_extract == ""
    # A cached failure is not retried either — no repeated hammering of a dead URL.
    fetch_source(citation, session=fast_session)
    page_calls = [r for r in requests_mock.request_history if r.url == url]
    assert len(page_calls) == 1


@pytest.mark.django_db
def test_fetch_sources_produces_hop2_evidence(source_pages, fast_session):
    citations = [
        _citation("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/", "ncbi.nlm.nih.gov"),
        _citation("https://www.cdc.gov/common-cold/", "cdc.gov"),
    ]

    evidence = fetch_sources(citations, depth="balanced", session=fast_session)

    assert [item.label for item in evidence] == ["S1", "S2"]
    assert all(item.hop == "cited_source" for item in evidence)
    assert all(item.snippet for item in evidence)
    assert all(item.fetch_status == EvidenceFetchStatus.FETCHED for item in evidence)
    assert Source.objects.count() == 2


@pytest.mark.django_db
def test_depth_fast_skips_hop2(fast_session):
    citations = [_citation("https://www.cdc.gov/common-cold/", "cdc.gov")]

    assert fetch_sources(citations, depth="fast", session=fast_session) == []
    assert Source.objects.count() == 0


def test_extract_html_text_keeps_main_prose():
    text = extract_html_text(load_text_fixture("source_cdc.html"))

    assert "no cure for the common cold" in text


def test_extract_text_routes_html():
    text = extract_text(b"<html><body><p>Hello world</p></body></html>", "text/html")

    assert "Hello world" in text


def test_extract_text_routes_pdf(monkeypatch):
    monkeypatch.setattr(
        "apps.sources.source_fetch.extract_pdf_text", lambda _data: "PDF BODY"
    )

    assert extract_text(b"%PDF-1.4 fake", "application/pdf") == "PDF BODY"


def test_is_primary_source():
    assert is_primary_source("https://www.cdc.gov/common-cold/")
    assert is_primary_source("https://www.hsph.harvard.edu/news/coffee/")
    assert is_primary_source("https://doi.org/10.1000/xyz")
    assert not is_primary_source(WEBMD_URL)
    assert not is_primary_source("https://www.nhs.uk/conditions/common-cold/")


def test_rank_citations_puts_primary_sources_first():
    webmd = _citation(WEBMD_URL, "webmd.com")
    cdc = _citation("https://www.cdc.gov/common-cold/", "cdc.gov")
    nhs = _citation("https://www.nhs.uk/conditions/common-cold/", "nhs.uk")
    harvard = _citation("https://www.hsph.harvard.edu/news/coffee/", "hsph.harvard.edu")

    ranked = rank_citations([webmd, cdc, nhs, harvard])

    assert ranked[0] is cdc
    assert ranked[1] is harvard
    assert ranked[-2:] == [webmd, nhs]  # non-primary keep insertion order
