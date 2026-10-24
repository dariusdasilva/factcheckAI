"""C4 — Source fetch: hop-2 ``S*`` evidence + the ``Source`` crawl cache.

ARCHITECTURE.md §3.2 stage 4 and the degradation rules in §5. For the top
``evidence_depth`` cited URLs we:

1. check the ``Source`` cache (URL + content hash, 7-day TTL) and skip the network
   entirely on a hit — repeated checks on the same topic must cost nothing;
2. otherwise fetch through the shared :class:`~apps.sources.politeness.PoliteSession`
   (1 MB cap, content-type allowlist, PDFs permitted for gov/edu/doi sources);
3. extract clean text — trafilatura for HTML, pypdf for PDFs;
4. upsert a ``Source`` row recording ``fetch_status``.

A source that cannot be fetched (paywall, 403, parse failure) is **not an error**:
it is cached with ``fetch_status='error'`` and skipped by the packer, so the check
still returns on the sources that did succeed (§5).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from .citations import CitedSource
from .constants import (
    DEFAULT_EVIDENCE_DEPTH,
    EVIDENCE_DEPTH_OPTIONS,
    MAX_SOURCE_TEXT_CHARS,
    PDF_CONTENT_TYPE,
    PRIMARY_SOURCE_HOSTS,
    PRIMARY_SOURCE_SUFFIXES,
    SOURCE_CACHE_TTL_SECONDS,
)
from .politeness import PolitenessError, PoliteSession
from .robots import RobotsChecker

try:  # pragma: no cover - import guard keeps this module importable without the extras
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None

try:  # pragma: no cover
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


@dataclass(frozen=True)
class SourceEvidence:
    """Hop-2 evidence: a snippet drawn from a source cited by a Wikipedia article.

    ``label`` is a pre-packing *ordinal* (S1..Sn over the fetched list). The
    canonical ``[W#]``/``[S#]`` ids the model may cite are assigned by
    :meth:`apps.sources.packer.pack_evidence`, which is the single label
    authority (AGENTS.md §4.5) and may skip renumberable empty entries.
    """

    label: str
    url: str
    title: str
    snippet: str
    domain: str
    fetch_status: str
    source_articles: tuple[str, ...] = ()
    hop: str = "cited_source"


def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_html_text(html: str) -> str:
    """Main-text extraction from HTML: trafilatura, falling back to a text dump."""
    if trafilatura is not None:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted and extracted.strip():
            return extracted.strip()
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def extract_pdf_text(data: bytes) -> str:
    """Text extraction from a PDF cited source (gov/edu/doi reports)."""
    if PdfReader is None:  # pragma: no cover
        return ""
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_text(content: bytes, content_type: str) -> str:
    """Route by content type to the right extractor."""
    base_type = content_type.split(";", 1)[0].strip().lower()
    if base_type == PDF_CONTENT_TYPE:
        return extract_pdf_text(content)
    return extract_html_text(content.decode("utf-8", errors="replace"))


def is_primary_source(url: str) -> bool:
    """True for govt/edu/doi/journal hosts — the ones hop-2 exists to check."""
    host = _domain(url)
    return host in PRIMARY_SOURCE_HOSTS or host.endswith(PRIMARY_SOURCE_SUFFIXES)


def rank_citations(citations: list[CitedSource]) -> list[CitedSource]:
    """Primary sources first, otherwise stable insertion order (§3.2 stage 4)."""
    return sorted(citations, key=lambda citation: not is_primary_source(citation.url))


def _source_model():
    """Lazily resolve the Chunk A ``Source`` model (avoids app-load-time import)."""
    from apps.checks.models import Source

    return Source


def _store(
    url: str,
    *,
    content_hash: str,
    fetch_status: str,
    text: str,
    fetched_at,
) -> object:
    Source = _source_model()
    row, _created = Source.objects.update_or_create(
        url=url,
        defaults={
            "content_hash": content_hash,
            "domain": _domain(url),
            "fetch_status": fetch_status,
            "text_extract": text,
            "fetched_at": fetched_at,
        },
    )
    return row


def _is_fresh(row, now, max_age_seconds: int) -> bool:
    if row.fetched_at is None:
        return False
    return (now - row.fetched_at) < timedelta(seconds=max_age_seconds)


def fetch_source(
    citation: CitedSource,
    *,
    session: PoliteSession | None = None,
    robots: RobotsChecker | None = None,
    now=None,
    max_age_seconds: int = SOURCE_CACHE_TTL_SECONDS,
):
    """Fetch (or return the cached) ``Source`` row for one cited URL.

    Returns the Django ``Source`` instance. Never raises on a fetch failure — the
    error is recorded on the row instead (§5). URLs disallowed by the domain's
    robots.txt are recorded as ``skipped`` without a single byte fetched (§6).
    """
    from django.utils import timezone

    from apps.checks.models import EvidenceFetchStatus

    session = session or PoliteSession()
    robots = robots or RobotsChecker(session=session)
    now = now or timezone.now()
    url = citation.url

    cached = _source_model().objects.filter(url=url).first()
    if cached is not None and _is_fresh(cached, now, max_age_seconds):
        return cached

    if not robots.can_fetch(url):
        return _store(
            url,
            content_hash=_sha256(url.encode("utf-8")),
            fetch_status=EvidenceFetchStatus.SKIPPED,
            text="",
            fetched_at=now,
        )

    try:
        response = session.get(url, allow_pdf=True)
        response.raise_for_status()
    except (requests.RequestException, PolitenessError):
        return _store(
            url,
            content_hash=_sha256(url.encode("utf-8")),
            fetch_status=EvidenceFetchStatus.ERROR,
            text="",
            fetched_at=now,
        )

    content = response.content
    content_type = response.headers.get("Content-Type", "")
    text = extract_text(content, content_type)[:MAX_SOURCE_TEXT_CHARS]
    return _store(
        url,
        content_hash=_sha256(content),
        fetch_status=EvidenceFetchStatus.FETCHED,
        text=text,
        fetched_at=now,
    )


def fetch_sources(
    citations: list[CitedSource],
    *,
    depth: str = DEFAULT_EVIDENCE_DEPTH,
    session: PoliteSession | None = None,
    robots: RobotsChecker | None = None,
    now=None,
    max_age_seconds: int = SOURCE_CACHE_TTL_SECONDS,
) -> list[SourceEvidence]:
    """Fetch hop-2 evidence for the top ``depth`` cited sources.

    ``depth`` is the ``evidence_depth`` knob (fast=0, balanced=3, deep=5).
    """
    if not citations:
        return []
    limit = EVIDENCE_DEPTH_OPTIONS.get(depth, EVIDENCE_DEPTH_OPTIONS[DEFAULT_EVIDENCE_DEPTH])
    if limit <= 0:
        return []

    session = session or PoliteSession()
    robots = robots or RobotsChecker(session=session)
    selected = rank_citations(citations)[:limit]

    evidence: list[SourceEvidence] = []
    for index, citation in enumerate(selected, start=1):
        row = fetch_source(
            citation, session=session, robots=robots, now=now, max_age_seconds=max_age_seconds
        )
        evidence.append(
            SourceEvidence(
                label=f"S{index}",
                url=row.url,
                title=_domain(row.url),
                snippet=row.text_extract or "",
                domain=row.domain,
                fetch_status=row.fetch_status,
                source_articles=citation.source_articles,
            )
        )
    return evidence
