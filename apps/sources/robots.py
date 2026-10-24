"""Per-domain robots.txt compliance (ARCHITECTURE.md §6 — a "must-have").

Respected for **all non-Wikipedia sources** fetched in §3.2 stage 4. Wikimedia
hosts are exempt: the politeness mechanism for Wikipedia/MediaWiki is ``maxlag``
plus the User-Agent policy, and the robots rule in §6 explicitly targets the
cited-source crawl.

robots.txt documents are fetched through the shared
:class:`~apps.sources.politeness.PoliteSession` (so they inherit the per-host
throttle and the Wikimedia User-Agent) and cached for 24 h in Django's cache,
so the checker adds at most one polite request per domain per day. Fail-open
behaviour is deliberate but short-circuited: a 5xx/unreachable robots.txt yields
*allow* with a short 300 s backoff so a flaky host is not hammered either.
"""

from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .constants import (
    ROBOTS_CACHE_TTL_SECONDS,
    ROBOTS_ERROR_BACKOFF_SECONDS,
    USER_AGENT,
    WIKI_MIRROR_HOSTS,
)
from .politeness import PolitenessError, PoliteSession

_CACHE_PREFIX = "factcheckai:robots:"
# Sentinel stored in the cache on an unreachable/5xx robots.txt. It cannot be
# ``None`` — Django's cache cannot distinguish a stored None from a miss, which
# would defeat the backoff (re-request robots.txt on every call).
_ROBOTS_UNREACHABLE = ["__factcheckai_robots_unreachable__"]
_USER_AGENT_TOKEN = USER_AGENT.split("/", 1)[0]  # robotparser matches product token


def _django_cache():
    """Lazily resolved so this module (and ``apps.sources``) imports without Django."""
    from django.core.cache import cache

    return cache


class RobotsChecker:
    """Answers "may we fetch this URL?" per robots.txt, cached per domain."""

    def __init__(
        self,
        session: PoliteSession | None = None,
        *,
        cache=None,
        ttl_seconds: int = ROBOTS_CACHE_TTL_SECONDS,
        error_backoff_seconds: int = ROBOTS_ERROR_BACKOFF_SECONDS,
    ) -> None:
        self.session = session or PoliteSession()
        self._cache = cache
        self.ttl_seconds = ttl_seconds
        self.error_backoff_seconds = error_backoff_seconds

    @property
    def cache(self):
        return self._cache if self._cache is not None else _django_cache()

    def can_fetch(self, url: str) -> bool:
        """True when robots.txt permits fetching ``url`` (or is absent/unreachable)."""
        host = urlsplit(url).netloc.lower()
        if _is_wikimedia(host):
            return True
        lines = self._load_robots(url, host)
        if lines is None:
            return True  # fail-open on unreachable robots (short-backoff cached)
        parser = RobotFileParser()
        parser.parse(lines)
        return parser.can_fetch(_USER_AGENT_TOKEN, url)

    def _robots_url(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}/robots.txt"

    def _load_robots(self, url: str, host: str) -> list[str] | None:
        """Return robots.txt lines; ``None`` on unreachable/5xx (fail-open).

        4xx (robots.txt simply does not exist) means *allow all* and is cached for
        the full TTL — hosts without a robots file must not be polled repeatedly.
        """
        key = _CACHE_PREFIX + host
        cached = self.cache.get(key)
        if cached is not None:
            if cached == _ROBOTS_UNREACHABLE:
                return None
            return cached

        try:
            response = self.session.get(self._robots_url(url))
        except (requests.RequestException, PolitenessError):
            self.cache.set(
                key, _ROBOTS_UNREACHABLE, timeout=self.error_backoff_seconds
            )
            return None

        if response.status_code == 200:
            lines: list[str] | None = response.text.splitlines()
        elif 400 <= response.status_code < 500:
            lines = []  # no robots.txt at all -> allow everything
        else:  # 5xx
            lines = None

        self.cache.set(
            key,
            lines if lines is not None else _ROBOTS_UNREACHABLE,
            timeout=self.ttl_seconds if lines is not None else self.error_backoff_seconds,
        )
        return lines


def _is_wikimedia(host: str) -> bool:
    return any(
        host == domain or host.endswith("." + domain) for domain in WIKI_MIRROR_HOSTS
    )
