"""Chunk C — Wikipedia evidence pipeline (``apps/sources/``).

The pipeline is a two-hop crawl (ARCHITECTURE.md §3.2)::

    claim ──▶ discovery (C1) ──▶ article read (C2) ──▶ citation extract (C3)
                                                          │
                                                          ▼
                                          source fetch (C4) ──▶ pack (C6)

Every outbound request goes through the shared rate-limited
:class:`~apps.sources.politeness.PoliteSession` (C5). C1–C3 and the packer are
framework-free and hermetically testable; C4 and :func:`store_evidence` touch the
Chunk A ``Source``/``Evidence`` models lazily, so this package imports without a
configured Django app registry.

Use :func:`run_evidence_pipeline` for the whole chain.
"""

from .article_read import WikiEvidence, read_articles
from .citations import CitedSource, extract_citations, filter_citation_urls
from .discovery import ArticleRef, discover_articles, extract_keywords, tokenize
from .packer import (
    EvidenceBundle,
    PackedEvidence,
    estimate_tokens,
    pack_evidence,
    store_evidence,
)
from .pipeline import EvidencePipelineResult, run_evidence_pipeline
from .politeness import PolitenessError, PoliteSession, RateLimiter
from .robots import RobotsChecker
from .source_fetch import SourceEvidence, fetch_source, fetch_sources, is_primary_source
from .wiki_client import WikiClient, WikiUnavailableError

__all__ = [
    "ArticleRef",
    "CitedSource",
    "EvidenceBundle",
    "EvidencePipelineResult",
    "PackedEvidence",
    "PoliteSession",
    "PolitenessError",
    "RateLimiter",
    "RobotsChecker",
    "SourceEvidence",
    "WikiClient",
    "WikiEvidence",
    "WikiUnavailableError",
    "discover_articles",
    "estimate_tokens",
    "extract_citations",
    "extract_keywords",
    "fetch_source",
    "fetch_sources",
    "filter_citation_urls",
    "is_primary_source",
    "pack_evidence",
    "read_articles",
    "run_evidence_pipeline",
    "store_evidence",
    "tokenize",
]
