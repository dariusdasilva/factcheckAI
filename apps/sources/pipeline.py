"""The Chunk C pipeline, wired end to end: C1 → C2 → C3 → C4 → C6.

This is the single entry point the orchestrator (Chunk A's check task, once A4
lands) calls to enrich a claim before inference. It composes the stage functions
and applies the §5 degradation rules:

- discovery failing → hop-1 evidence unavailable: the check proceeds without
  evidence and (per §5) hop 2 is skipped with it — nothing is fabricated;
- article read / citation extraction failing per *page* → partial degradation,
  the surviving snippets are kept ("use the ones that succeeded").

ALL outbound traffic of a run goes through exactly ONE
:class:`~apps.sources.politeness.PoliteSession` so the process-global limiter
sees — and spaces — hop-1 and hop-2 requests together.
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
    # One shared polite session for the whole run: hop-1 and hop-2 share the
    # same per-host limiter bookkeeping (§3.2 "outbound crawl concurrency … 1").
    session = session or PoliteSession()
    client = client or WikiClient(session)
    result = EvidencePipelineResult(claim=claim)

    try:
        result.articles = discover_articles(claim, client=client)
    except WikiUnavailableError as exc:
        # §5: no hop-1 evidence → reduced-confidence verdict, not a failure.
        # No articles → no citations → hop 2 is skipped with it.
        result.degraded = True
        result.degrade_reason = str(exc)
        result.bundle = EvidenceBundle(claim=claim)
        return result

    # read_articles degrades per article and keeps the survivors; if every page
    # failed we mark the run degraded rather than shipping an empty-looking OK.
    result.wiki_evidence = read_articles(result.articles, client=client)
    if result.articles and not result.wiki_evidence:
        result.degraded = True
        result.degrade_reason = "Wikipedia articles could not be read"
    try:
        result.citations = extract_citations(result.articles, client=client)
    except WikiUnavailableError as exc:
        result.degraded = True
        result.degrade_reason = str(exc)

    if result.citations:
        result.source_evidence = fetch_sources(result.citations, depth=depth, session=session)
    result.bundle = pack_evidence(
        claim,
        result.wiki_evidence,
        result.source_evidence,
        token_budget=token_budget,
    )
    return result
