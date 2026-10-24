"""Chunk C — Wikipedia evidence pipeline (``apps/sources/``).

The pipeline is a two-hop crawl (ARCHITECTURE.md §3.2)::

    claim ──▶ discovery (C1) ──▶ article read (C2) ──▶ citation extract (C3)
                                                          │
                                                          └─▶ source fetch (C4, later)

C1–C3 are deliberately framework-free: they take a claim (or article refs) in and
return plain dataclasses out, so they can be unit-tested hermetically and composed
by the later packer (C6) without a Django settings module. The ``Source``/``Evidence``
persistence layer belongs to Chunk A (A2) and is wired in by C4/C6.
"""

from .article_read import WikiEvidence, read_articles
from .citations import CitedSource, extract_citations, filter_citation_urls
from .discovery import ArticleRef, discover_articles, extract_keywords
from .wiki_client import WikiClient, WikiUnavailableError

__all__ = [
    "ArticleRef",
    "CitedSource",
    "WikiClient",
    "WikiEvidence",
    "WikiUnavailableError",
    "discover_articles",
    "extract_citations",
    "extract_keywords",
    "filter_citation_urls",
    "read_articles",
]
