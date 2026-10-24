"""C3 — Citation extraction: the cited URLs behind each hop-1 article.

ARCHITECTURE.md §3.2 stage 3. Two sources of cited URLs are merged:

1. ``prop=extlinks`` — the programmatic list of external URLs per article
   (both "External links" sections and references);
2. reference parsing from the rendered article HTML (``<ol class="references">``,
   ``cite`` and ``a.external`` anchors), used when the API list is incomplete.

The merged list is then hardened: archive/redirect services are stripped, social
and wiki-mirror hosts dropped, non-HTTP schemes removed, and URLs deduped both
exact and one-per-domain. The survivors become hop-2 ``S*`` candidates for C4.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .constants import ARCHIVE_HOSTS, SOCIAL_HOSTS, WIKI_MIRROR_HOSTS
from .discovery import ArticleRef
from .wiki_client import WikiClient, WikiUnavailableError


@dataclass(frozen=True)
class CitedSource:
    """A hop-2 candidate: a URL cited by one or more hop-1 articles."""

    url: str
    domain: str
    source_articles: tuple[str, ...] = ()
    hop: str = "cited_source"


def _host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_excluded(host: str) -> bool:
    for blocked in (*ARCHIVE_HOSTS, *SOCIAL_HOSTS, *WIKI_MIRROR_HOSTS):
        if host == blocked or host.endswith("." + blocked):
            return True
    return False


def _is_fetchable(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def filter_citation_urls(urls: Iterable[str]) -> list[str]:
    """Strip archives/mirrors/social hosts and dedupe exact URLs, preserving order."""
    filtered: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url or not _is_fetchable(url) or _is_excluded(_host(url)):
            continue
        normalized = url.split("#", 1)[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)
    return filtered


def dedupe_by_domain(urls: Iterable[str]) -> list[str]:
    """Keep only the first URL seen per registrable-ish host, preserving order.

    ARCHITECTURE.md §3.2 stage 3: "dedupe by domain" — a page citing the same site
    five times should not five times the hop-2 fetch budget.
    """
    kept: list[str] = []
    seen_domains: set[str] = set()
    for url in urls:
        host = _host(url)
        if host in seen_domains:
            continue
        seen_domains.add(host)
        kept.append(url)
    return kept


def parse_references(html: str) -> list[str]:
    """Extract cited URLs from rendered article HTML (best-effort, order-preserving)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("ol.references a[href], cite a[href], a.external[href]"):
        href = anchor.get("href")
        if href and _is_fetchable(href):
            urls.append(href)
    return urls


@dataclass
class _DomainAccumulator:
    url: str
    articles: list[str] = field(default_factory=list)


def extract_citations(
    articles: list[ArticleRef],
    *,
    client: WikiClient | None = None,
    article_html: dict[str, str] | None = None,
) -> list[CitedSource]:
    """Extract and harden cited sources for ``articles``.

    ``article_html`` (title → rendered HTML) is optional and only needed when the
    ``prop=extlinks`` list alone is insufficient; the two sources are merged.
    """
    client = client or WikiClient()
    if not articles:
        return []

    titles = [article.title for article in articles]
    try:
        extlinks = client.extlinks(titles) if titles else {}
    except WikiUnavailableError:
        # §5: degrade to reference parsing / article HTML rather than discarding hop 2.
        extlinks = {}

    by_domain: dict[str, _DomainAccumulator] = {}
    for article in articles:
        raw_urls = list(extlinks.get(article.title, []))
        if article_html and article.title in article_html:
            raw_urls.extend(parse_references(article_html[article.title]))
        cleaned = dedupe_by_domain(filter_citation_urls(raw_urls))
        for url in cleaned:
            host = _host(url)
            entry = by_domain.setdefault(host, _DomainAccumulator(url=url))
            if article.title not in entry.articles:
                entry.articles.append(article.title)

    return [
        CitedSource(url=entry.url, domain=domain, source_articles=tuple(entry.articles))
        for domain, entry in by_domain.items()
    ]
