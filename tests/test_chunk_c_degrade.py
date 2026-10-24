"""Audit-driven tests: §5 degradation must cover *connection-level* outages.

Review round 2 found that only HTTP status errors (503) were handled — a Wikipedia
that is unreachable at the network level (``ConnectionError``, ``Timeout``) crashed
the pipeline instead of degrading. These tests pin the network-failure paths:

- MediaWiki connection errors map to ``WikiUnavailableError`` (client level);
- the whole run degrades when discovery is unreachable (no hop-1, no hop-2);
- a partial summary outage degrades *per article* and keeps discovery snippets;
- an extlinks outage degrades to reference parsing of article HTML.
"""

from __future__ import annotations

import pytest
import requests
from conftest import SUMMARY_BASE, load_text_fixture

from apps.sources.article_read import read_articles
from apps.sources.citations import extract_citations, parse_references
from apps.sources.discovery import ArticleRef, discover_articles
from apps.sources.pipeline import run_evidence_pipeline
from apps.sources.wiki_client import WikiUnavailableError

CLAIM = "Drinking coffee cures the common cold."

ARTICLES = [
    ArticleRef(1234, "Coffee", "search snippet for coffee", 14000, 42.5, "https://en.wikipedia.org/wiki/Coffee"),
    ArticleRef(5678, "Common cold", "search snippet for the cold", 11000, 38.1, "https://en.wikipedia.org/wiki/Common_cold"),
    ArticleRef(91011, "Caffeine", "search snippet for caffeine", 9000, 30.0, "https://en.wikipedia.org/wiki/Caffeine"),
]


def test_connection_error_raises_wiki_unavailable(requests_mock, wiki_client):
    # More severe than a 503: the TCP connection itself fails (§5 "Wikipedia …
    # down or rate-limiting us" — both must degrade, neither may crash).
    requests_mock.get("https://en.wikipedia.org/w/api.php", exc=requests.ConnectionError("refused"))

    with pytest.raises(WikiUnavailableError):
        discover_articles(CLAIM, client=wiki_client)


def test_timeout_raises_wiki_unavailable(requests_mock, wiki_client):
    requests_mock.get("https://en.wikipedia.org/w/api.php", exc=requests.ConnectTimeout())

    with pytest.raises(WikiUnavailableError):
        discover_articles(CLAIM, client=wiki_client)


@pytest.mark.django_db
def test_pipeline_degrades_on_connection_error(requests_mock, wiki_client, fast_session):
    requests_mock.get("https://en.wikipedia.org/w/api.php", exc=requests.ConnectionError("refused"))

    result = run_evidence_pipeline(CLAIM, client=wiki_client, session=fast_session)

    # §5: the check proceeds without hop-1 evidence — degraded, never a crash.
    assert result.degraded is True
    assert result.degrade_reason
    assert result.articles == []
    assert result.wiki_evidence == []
    assert result.bundle.labels() == []
    assert result.bundle.claim == CLAIM


def test_summary_outage_falls_back_to_discovery_snippet(wiki_api, wiki_client):
    # Partial outage: the action API (extracts batch) and the Common cold summary
    # endpoint are down, but Coffee and Caffeine summaries are still served.
    wiki_api.get("https://en.wikipedia.org/w/api.php", exc=requests.ConnectionError("refused"))
    wiki_api.get(SUMMARY_BASE + "Common_cold", status_code=503)

    evidence = read_articles(ARTICLES, client=wiki_client)

    # §5 "use the ones that succeeded": three rows, not an empty list.
    assert [item.label for item in evidence] == ["W1", "W2", "W3"]
    assert evidence[0].snippet  # Coffee summary survived
    assert evidence[2].snippet  # Caffeine summary survived
    # Common cold degraded to the discovery snippet instead of disappearing.
    assert evidence[1].snippet == "search snippet for the cold"
    assert evidence[1].title == "Common cold"


def test_extlinks_outage_falls_back_to_article_html(wiki_api, wiki_client, monkeypatch):
    def broken_extlinks(_titles):
        raise WikiUnavailableError("extlinks endpoint down")

    monkeypatch.setattr(wiki_client, "extlinks", broken_extlinks)
    html = load_text_fixture("article_refs.html")

    citations = extract_citations(ARTICLES[:1], client=wiki_client, article_html={"Coffee": html})

    # Hop 2 survives via the rendered-HTML fallback (parser + hardening both ran:
    # the social URL and the mailto link were dropped).
    urls = {citation.url for citation in citations}
    assert urls == {"https://example.org/study", "https://journals.example.edu/article/42",
                    "https://www.britannica.com/topic/coffee"}
    assert citations[0].source_articles == ("Coffee",)
    # Sanity: the fallback sources are a subset of what the parser found.
    parsed = set(parse_references(html)) | {"https://twitter.com/someone/status/1"}
    assert urls <= {url.split("#", 1)[0] for url in parsed}


def test_connection_error_is_not_cached_as_an_article(requests_mock, wiki_client):
    # A connection outage must not poison the cache: once Wikipedia is back, the
    # next pass re-fetches (caching only happens on success).
    requests_mock.get("https://en.wikipedia.org/w/api.php", exc=requests.ConnectionError("refused"))
    from apps.sources.discovery import discover_articles as _discover

    with pytest.raises(WikiUnavailableError):
        _discover(CLAIM, client=wiki_client)

    # Wikipedia is back — the same client now talks to a healthy API again.
    requests_mock.get("https://en.wikipedia.org/w/api.php", json={"query": {"search": []}})

    assert _discover("coffee cold", client=wiki_client) == []
