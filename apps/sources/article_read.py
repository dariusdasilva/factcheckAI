"""C2 — Article read: turn discovered articles into hop-1 evidence ``W*``.

ARCHITECTURE.md §3.2 stage 2. For each article we combine the REST summary
(``/page/summary/``: lead extract, description, canonical URL) with the action-API
plaintext intro (``prop=extracts``), preferring whichever body of text is richer.
The result is the hop-1 evidence that later flows into the prompt as ``[W1]`` etc.
"""

from __future__ import annotations

from dataclasses import dataclass

from .discovery import ArticleRef
from .wiki_client import WikiClient


@dataclass(frozen=True)
class WikiEvidence:
    """Hop-1 evidence: a snippet drawn from a Wikipedia article.

    ``label`` is the citation id used by the prompt (``W1``, ``W2``, …); the model
    is only allowed to cite ids we supplied (AGENTS.md §4.5).
    """

    label: str
    pageid: int
    title: str
    url: str
    snippet: str
    description: str
    hop: str = "wiki"


def _canonical_url(summary: dict, fallback: str) -> str:
    content_urls = summary.get("content_urls") or {}
    desktop = content_urls.get("desktop") or {}
    return desktop.get("page") or fallback


def _extract_map(payload: dict) -> dict[str, str]:
    """Map article title → plaintext extract from a ``prop=extracts`` payload."""
    extracts: dict[str, str] = {}
    for page in payload.get("query", {}).get("pages", []):
        title = page.get("title")
        if title and page.get("extract"):
            extracts[title] = page["extract"]
    return extracts


def read_articles(
    articles: list[ArticleRef],
    *,
    client: WikiClient | None = None,
) -> list[WikiEvidence]:
    """Read hop-1 evidence for ``articles``, returned as ordered ``W1..Wn``.

    A missing summary or extract degrades to the discovery snippet rather than
    dropping the article, so a partially-available Wikipedia still yields evidence.
    """
    client = client or WikiClient()
    if not articles:
        return []

    extracts = _extract_map(client.extracts([article.title for article in articles]))

    evidence: list[WikiEvidence] = []
    for index, article in enumerate(articles, start=1):
        summary = client.summary(article.title)
        summary_extract = summary.get("extract") or ""
        extract_text = extracts.get(article.title) or ""
        # Prefer the longer of the two bodies of prose; fall back to the search snippet.
        snippet = max((summary_extract, extract_text), key=len) or article.snippet
        evidence.append(
            WikiEvidence(
                label=f"W{index}",
                pageid=article.pageid,
                title=summary.get("title") or article.title,
                url=_canonical_url(summary, article.url),
                snippet=snippet,
                description=summary.get("description") or "",
            )
        )
    return evidence
