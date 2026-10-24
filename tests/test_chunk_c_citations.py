"""C3 acceptance — Citation extraction: ``prop=extlinks`` + reference parse.

Fixture with known refs (WORK_CHUNKS.md, Chunk C). Verifies archive/social/mirror
stripping, exact + per-domain dedupe, reference parsing, and continuation paging.
"""

from __future__ import annotations

from conftest import load_text_fixture

from apps.sources.citations import (
    CitedSource,
    dedupe_by_domain,
    extract_citations,
    filter_citation_urls,
    parse_references,
)
from apps.sources.discovery import ArticleRef

ARTICLES = [
    ArticleRef(1234, "Coffee", "", 14000, 42.5, "https://en.wikipedia.org/wiki/Coffee"),
    ArticleRef(5678, "Common cold", "", 11000, 38.1, "https://en.wikipedia.org/wiki/Common_cold"),
]


def test_filter_strips_archives_social_mirrors_and_bad_schemes():
    urls = [
        "https://www.webmd.com/diet/health-benefits-coffee",
        "https://web.archive.org/web/2020/https://example.com/old",
        "https://twitter.com/someone/status/123",
        "https://en.wikipedia.org/wiki/Coffee",
        "mailto:editor@example.com",
        "ftp://files.example.com/report.pdf",
        "https://www.webmd.com/diet/health-benefits-coffee",  # exact duplicate
        "https://www.webmd.com/diet/health-benefits-coffee#section",  # fragment variant
    ]

    assert filter_citation_urls(urls) == ["https://www.webmd.com/diet/health-benefits-coffee"]


def test_dedupe_by_domain_keeps_the_first_url_per_host():
    urls = [
        "https://a.example.com/1",
        "https://b.example.com/2",
        "https://a.example.com/3",
    ]

    assert dedupe_by_domain(urls) == ["https://a.example.com/1", "https://b.example.com/2"]


def test_parse_references_reads_cite_and_external_anchors():
    urls = parse_references(load_text_fixture("article_refs.html"))

    assert "https://example.org/study" in urls
    assert "https://journals.example.edu/article/42" in urls
    assert "https://www.britannica.com/topic/coffee" in urls
    assert not any(url.startswith("mailto:") for url in urls)


def test_parse_references_empty_html():
    assert parse_references("") == []


def test_extract_citations_hardens_and_accumulates_by_domain(wiki_api, wiki_client):
    citations = extract_citations(ARTICLES, client=wiki_client)

    assert all(isinstance(citation, CitedSource) for citation in citations)
    domains = {citation.domain for citation in citations}
    assert {"webmd.com", "ncbi.nlm.nih.gov", "nhs.uk", "hsph.harvard.edu", "cdc.gov"} <= domains
    assert not any("archive" in domain for domain in domains)
    assert not any("twitter" in domain for domain in domains)
    assert not any("wikipedia" in domain for domain in domains)

    # webmd.com is cited by both articles but stored once, recording both sources.
    webmd = [citation for citation in citations if citation.domain == "webmd.com"]
    assert len(webmd) == 1
    assert set(webmd[0].source_articles) == {"Coffee", "Common cold"}


def test_extract_citations_follows_continuation(wiki_api, wiki_client):
    extract_citations(ARTICLES, client=wiki_client)

    continued = [request for request in wiki_api.request_history if "eloffset" in request.qs]
    assert continued, "the continuation page from prop=extlinks was never fetched"


def test_extract_citations_merges_reference_html(wiki_api, wiki_client):
    html = {"Coffee": load_text_fixture("article_refs.html")}

    citations = extract_citations(ARTICLES, client=wiki_client, article_html=html)

    domains = {citation.domain for citation in citations}
    assert "example.org" in domains
    assert "journals.example.edu" in domains
    # A social link present in the HTML must still be filtered out.
    assert not any("twitter" in domain for domain in domains)


def test_extract_citations_empty(wiki_client):
    assert extract_citations([], client=wiki_client) == []
