"""C1 acceptance — Discovery: claim → MediaWiki ``list=search`` → ≤ 3 articles.

Canned-Wiki-API test (WORK_CHUNKS.md, Chunk C). Replays a recorded search payload;
asserts the article cap, the cleaned snippets and the ``maxlag`` / User-Agent
politeness contract.
"""

from __future__ import annotations

from apps.sources.discovery import (
    ArticleRef,
    build_search_query,
    discover_articles,
    extract_keywords,
)

CLAIM = "Drinking coffee cures the common cold."


def test_extract_keywords_drops_stopwords_and_duplicates():
    assert extract_keywords(CLAIM) == ["drinking", "coffee", "cures", "common", "cold"]


def test_build_search_query_joins_keywords():
    assert build_search_query(CLAIM) == "drinking coffee cures common cold"


def test_build_search_query_honours_custom_builder():
    assert build_search_query(CLAIM, query_builder=lambda _c: "coffee cold") == "coffee cold"


def test_discover_caps_at_three_articles(wiki_api, wiki_client):
    articles = discover_articles(CLAIM, client=wiki_client)

    assert len(articles) == 3
    assert all(isinstance(article, ArticleRef) for article in articles)
    assert [article.title for article in articles] == ["Coffee", "Common cold", "Caffeine"]
    assert articles[0].pageid == 1234
    assert articles[0].url == "https://en.wikipedia.org/wiki/Coffee"


def test_discover_strips_search_highlight_markup(wiki_api, wiki_client):
    articles = discover_articles(CLAIM, client=wiki_client)

    assert "<span" not in articles[0].snippet
    assert articles[0].snippet.startswith("Coffee is a brewed drink")


def test_discover_limit_is_clamped_to_the_cap(wiki_api, wiki_client):
    assert len(discover_articles(CLAIM, client=wiki_client, limit=99)) == 3


def test_discover_returns_empty_without_usable_keywords(wiki_client):
    assert discover_articles("the and of a to", client=wiki_client) == []


def test_search_request_is_polite(wiki_api, wiki_client):
    discover_articles(CLAIM, client=wiki_client)

    request = wiki_api.request_history[0]
    assert request.qs["maxlag"] == ["5"]
    assert request.headers["User-Agent"].startswith("FactCheckAI/")
