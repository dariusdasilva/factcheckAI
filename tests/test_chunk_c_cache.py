"""Audit-driven tests: §3.2 response caching in the wiki layer.

"Everything cached: articles 7 days, sources 7 days, search results 24 h" — the
search/summary/extracts/extlinks responses must not be re-requested on a second
identical pass, and error responses must never be cached.
"""

from __future__ import annotations

import pytest
from conftest import WIKI_API

from apps.sources.article_read import read_articles
from apps.sources.citations import extract_citations
from apps.sources.discovery import ArticleRef, discover_articles
from apps.sources.wiki_client import WikiUnavailableError

CLAIM = "Drinking coffee cures the common cold."

ARTICLES = [
    ArticleRef(1234, "Coffee", "snippet", 14000, 42.5, "https://en.wikipedia.org/wiki/Coffee"),
    ArticleRef(5678, "Common cold", "snippet", 11000, 38.1, "https://en.wikipedia.org/wiki/Common_cold"),
    ArticleRef(91011, "Caffeine", "snippet", 9000, 30.0, "https://en.wikipedia.org/wiki/Caffeine"),
]


def test_search_results_are_cached(wiki_api, wiki_client):
    discover_articles(CLAIM, client=wiki_client)
    discover_articles(CLAIM, client=wiki_client)

    search_calls = [r for r in wiki_api.request_history if r.qs.get("list") == ["search"]]
    assert len(search_calls) == 1


def test_extracts_and_summaries_are_cached(wiki_api, wiki_client):
    read_articles(ARTICLES, client=wiki_client)
    read_articles(ARTICLES, client=wiki_client)

    extracts_calls = [r for r in wiki_api.request_history if r.qs.get("prop") == ["extracts"]]
    summary_calls = [r for r in wiki_api.request_history if "/page/summary/" in r.url]
    assert len(extracts_calls) == 1
    assert len(summary_calls) == 3  # one per title, not per pass


def test_extlinks_are_cached(wiki_api, wiki_client):
    extract_citations(ARTICLES, client=wiki_client)
    extract_citations(ARTICLES, client=wiki_client)

    extlink_calls = [r for r in wiki_api.request_history if r.qs.get("prop") == ["extlinks"]]
    # First pass: 2 requests (first page + continuation). Second pass: 0 (cache).
    assert len(extlink_calls) == 2


def test_error_responses_are_not_cached(requests_mock, wiki_client):
    requests_mock.get(WIKI_API, status_code=503)

    with pytest.raises(WikiUnavailableError):
        discover_articles(CLAIM, client=wiki_client)
    with pytest.raises(WikiUnavailableError):
        discover_articles(CLAIM, client=wiki_client)

    assert requests_mock.call_count == 2  # both attempts hit the network


def test_missing_summary_is_not_cached(wiki_api, wiki_client):
    # A page that vanished between discovery and read returns {} — it must be
    # re-checked on the next pass, never re-served from the cache.
    from conftest import SUMMARY_BASE

    wiki_api.get(SUMMARY_BASE + "Deleted_page", status_code=404)
    vanished = ArticleRef(
        1, "Deleted page", "snippet", 100, 1.0, "https://en.wikipedia.org/wiki/Deleted_page"
    )

    read_articles([vanished], client=wiki_client)
    read_articles([vanished], client=wiki_client)

    summary_calls = [r for r in wiki_api.request_history if r.url.endswith("Deleted_page")]
    assert len(summary_calls) == 2
