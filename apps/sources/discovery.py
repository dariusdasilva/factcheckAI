"""C1 — Discovery: claim text → up to three relevant Wikipedia articles.

ARCHITECTURE.md §3.2 stage 1. Keywords are extracted locally (deterministic, no
extra model call in the hot path); if keyword extraction is poor the pipeline can
later inject Gemma-generated queries through the ``query_builder`` hook without
changing this module's contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .constants import DISCOVERY_ARTICLE_LIMIT
from .wiki_client import WikiClient

# Deliberately small, hand-rolled stopword list: no NLTK download at runtime, and
# the demo's claims are English. Chunk C's eval set (§9 Q3) may extend it.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because
    been before being below between both but by can cannot could couldn't did didn't
    do does doesn't doing don't down during each few for from further had hadn't has
    hasn't have haven't having he her here hers herself him himself his how i if in
    into is isn't it its itself let's me more most mustn't my myself no nor not of off
    on once only or other ought our ours ourselves out over own same shan't she should
    shouldn't so some such than that the their theirs them themselves then there these
    they this those through to too under until up very was wasn't we were weren't what
    when where which while who whom why with won't would wouldn't you your yours
    yourself yourselves is are was were be been being
    """.split()
)

MIN_KEYWORD_LENGTH = 3
MAX_KEYWORDS = 12


@dataclass(frozen=True)
class ArticleRef:
    """A Wikipedia article candidate returned by discovery (hop-1 seed)."""

    pageid: int
    title: str
    snippet: str
    wordcount: int
    score: float
    url: str


def extract_keywords(claim: str, *, max_keywords: int = MAX_KEYWORDS) -> list[str]:
    """Return claim keywords in first-seen order, stopwords and short tokens removed.

    Deterministic and dependency-free; preserves order so the query reads naturally
    ("drinking coffee cures common cold") rather than alphabetically.
    """
    keywords: list[str] = []
    seen: set[str] = set()
    for raw in claim.split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum() or ch == "-").strip("-")
        if len(token) < MIN_KEYWORD_LENGTH or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= max_keywords:
            break
    return keywords


def build_search_query(claim: str, *, query_builder: Callable[[str], str] | None = None) -> str:
    """Build the ``srsearch`` string. ``query_builder`` overrides keyword extraction."""
    if query_builder is not None:
        return query_builder(claim)
    return " ".join(extract_keywords(claim))


def _article_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")


def _clean_snippet(snippet: str) -> str:
    """Search snippets arrive as HTML with ``<span class="searchmatch">`` highlights."""
    return BeautifulSoup(snippet, "html.parser").get_text(" ", strip=True)


def discover_articles(
    claim: str,
    *,
    client: WikiClient | None = None,
    limit: int = DISCOVERY_ARTICLE_LIMIT,
    query_builder: Callable[[str], str] | None = None,
) -> list[ArticleRef]:
    """Search Wikipedia for ``claim`` and return at most ``DISCOVERY_ARTICLE_LIMIT`` articles.

    ``limit`` is clamped to the §3.2 stage-1 cap so a caller cannot accidentally
    issue an impolite discovery fan-out.
    """
    client = client or WikiClient()
    effective_limit = max(0, min(limit, DISCOVERY_ARTICLE_LIMIT))
    if effective_limit == 0:
        return []

    query = build_search_query(claim, query_builder=query_builder)
    if not query.strip():
        return []

    payload = client.search(query, limit=effective_limit)
    hits = payload.get("query", {}).get("search", [])
    if not isinstance(hits, list):
        return []

    articles: list[ArticleRef] = []
    for hit in hits[:effective_limit]:
        title = hit.get("title")
        if not title:
            continue
        articles.append(
            ArticleRef(
                pageid=int(hit.get("pageid") or 0),
                title=title,
                snippet=_clean_snippet(hit.get("snippet", "")),
                wordcount=int(hit.get("wordcount") or 0),
                score=float(hit.get("score") or 0.0),
                url=_article_url(title),
            )
        )
    return articles
