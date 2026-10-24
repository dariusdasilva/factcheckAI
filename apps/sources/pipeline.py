"""The Chunk C pipeline, wired end to end: C1 → C2 → C3 → C4 → C6.

This is the single entry point the orchestrator (Chunk A's check task, once A4
lands) calls to enrich a claim before inference. It composes the stage functions
and applies the §5 degradation rule: if Wikipedia/MediaWiki is unavailable, the
check proceeds **without hop-1 evidence** (``degraded=True``) instead of failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .article_read import WikiEvidence, read_articles
from .citations import CitedSource, extract_citations
from .constants import DEFAULT_EVIDENCE_DEPTH, DEFAULT_TOKEN_BUDGET
from .discovery import ArticleRef, discover_articles
from .packer import EvidenceBundle, pack_evidence
from .politeness import PoliteSession
from .source_fetch import SourceEvidence, fetch_sources
from .wiki_client import WikiClient, WikiUnavailableError


@dataclass
class EvidencePipelineResult:
    """Everything the pipeline gathered for one claim, ready to hand to B/A."""

    claim: str
    articles: list[ArticleRef] = field(default_factory=list)
    wiki_evidence: list[WikiEvidence] = field(default_factory=list)
    citations: list[CitedSource] = field(default_factory=list)
    source_evidence: list[SourceEvidence] = field(default_factory=list)
    bundle: EvidenceBundle | None = None
    degraded: bool = False
    degrade_reason: str | None = None


def run_evidence_pipeline(
    claim: str,
    *,
    client: WikiClient | None = None,
    session: PoliteSession | None = None,
    depth: str = DEFAULT_EVIDENCE_DEPTH,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> EvidencePipelineResult:
    """Run discovery → article read → citation extract → source fetch → pack."""
    client = client or WikiClient()
    result = EvidencePipelineResult(claim=claim)

    try:
        result.articles = discover_articles(claim, client=client)
        result.wiki_evidence = read_articles(result.articles, client=client)
        result.citations = extract_citations(result.articles, client=client)
    except WikiUnavailableError as exc:
        # §5: no hop-1 evidence → reduced-confidence verdict, not a failure.
        result.degraded = True
        result.degrade_reason = str(exc)
        result.bundle = EvidenceBundle(claim=claim)
        return result

    result.source_evidence = fetch_sources(result.citations, depth=depth, session=session)
    result.bundle = pack_evidence(
        claim,
        result.wiki_evidence,
        result.source_evidence,
        token_budget=token_budget,
    )
    return result
