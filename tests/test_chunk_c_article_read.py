"""C2 acceptance — Article read: ``page/summary`` + extracts → hop-1 evidence ``W*``.

Two-article fixture returns texts (WORK_CHUNKS.md, Chunk C). Verifies the ``W1``/
``W2`` labelling, the summary/extract merge, and the canonical-URL handling.
"""

from __future__ import annotations

from apps.sources.article_read import WikiEvidence, read_articles
from apps.sources.discovery import ArticleRef

ARTICLES = [
    ArticleRef(
        pageid=1234,
        title="Coffee",
        snippet="search snippet for coffee",
        wordcount=14000,
        score=42.5,
        url="https://en.wikipedia.org/wiki/Coffee",
    ),
    ArticleRef(
        pageid=5678,
        title="Common cold",
        snippet="search snippet for the cold",
        wordcount=11000,
        score=38.1,
        url="https://en.wikipedia.org/wiki/Common_cold",
    ),
]


def test_read_two_articles_returns_texts(wiki_api, wiki_client):
    evidence = read_articles(ARTICLES, client=wiki_client)

    assert len(evidence) == 2
    assert all(isinstance(item, WikiEvidence) for item in evidence)
    assert [item.label for item in evidence] == ["W1", "W2"]
    assert [item.title for item in evidence] == ["Coffee", "Common cold"]
    assert all(item.snippet.strip() for item in evidence)
    assert all(item.hop == "wiki" for item in evidence)


def test_read_prefers_the_richer_extract_text(wiki_api, wiki_client):
    evidence = read_articles(ARTICLES, client=wiki_client)

    # ``prop=extracts`` prose is longer than the REST summary extract, so it wins.
    assert evidence[0].snippet.startswith("Coffee is a beverage brewed")
    assert evidence[1].snippet.startswith("The common cold is a viral infection")


def test_read_uses_canonical_url_and_description(wiki_api, wiki_client):
    evidence = read_articles(ARTICLES, client=wiki_client)

    assert evidence[0].url == "https://en.wikipedia.org/wiki/Coffee"
    assert evidence[0].description == "Brewed beverage made from coffee beans"


def test_read_empty_returns_empty(wiki_client):
    assert read_articles([], client=wiki_client) == []
