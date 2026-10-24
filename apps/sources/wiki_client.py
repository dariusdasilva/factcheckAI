"""Low-level MediaWiki / Wikimedia REST client used by the C1–C3 stages.

All requests go through a :class:`~apps.sources.politeness.PoliteSession`, and
every ``action=query`` call carries ``maxlag=5``. Responses are cached per
ARCHITECTURE.md §3.2 ("everything cached"): search results 24 h, article data
(extracts, summaries, external links) 7 days — so repeated checks on the same
topic cost the Wikimedia network nothing after the first pass. Error responses
are never cached; they surface as :class:`WikiUnavailableError` so the pipeline
can degrade (§5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from urllib.parse import quote

import requests

from .constants import (
    ARTICLE_CACHE_TTL_SECONDS,
    EXTLINKS_MAX_PAGES,
    MAXLAG_SECONDS,
    SEARCH_CACHE_TTL_SECONDS,
    WIKI_API_ENDPOINT,
    WIKI_REST_SUMMARY_ENDPOINT,
)
from .politeness import PoliteSession

_CACHE_PREFIX = "factcheckai:wiki:"


def _default_cache():
    """Lazily resolved so this module imports without a configured Django."""
    from django.core.cache import cache

    return cache


class WikiUnavailableError(RuntimeError):
    """Wikipedia/MediaWiki is down or rate-limiting us (maxlag 503).

    The caller degrades gracefully: the check proceeds *without hop-1 evidence*
    at reduced confidence (ARCHITECTURE.md §5) rather than failing the whole check.
    """


class WikiClient:
    """Thin typed wrapper over the MediaWiki action API and the REST summary API."""

    def __init__(self, session: PoliteSession | None = None, *, cache=None) -> None:
        self.session = session or PoliteSession()
        self._cache = cache

    @property
    def cache(self):
        return self._cache if self._cache is not None else _default_cache()

    # -- caching ----------------------------------------------------------------------
    @staticmethod
    def _cache_key(url: str, params: dict[str, object] | None) -> str:
        blob = json.dumps(params or {}, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{url}|{blob}".encode()).hexdigest()
        return _CACHE_PREFIX + digest

    def _cached(self, key: str, ttl: int, fetch: Callable[[], dict], *, cache_empty: bool = True) -> dict:
        """Return cached payload or fetch-and-store. Errors propagate uncached.

        ``cache_empty=False`` stores nothing when the fetch yields ``{}`` (used by
        ``summary``, where an empty mapping means "page missing right now" and
        must be re-checked, not re-served, on the next pass). The other endpoints
        treat empty results as meaningful and cache them.
        """
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        payload = fetch()
        if payload or cache_empty:
            self.cache.set(key, payload, ttl)
        return payload

    # -- action=query primitives ------------------------------------------------------
    def _api_get(self, params: dict[str, object]) -> dict:
        try:
            payload = self.session.get_json(WIKI_API_ENDPOINT, params=params)
        except requests.RequestException as exc:
            # §5: Wikipedia down / unreachable / rate-limiting us — the *whole*
            # request family degrades, not just HTTP status errors.
            response = getattr(exc, "response", None)
            if isinstance(response, requests.Response) and response.status_code == 503:
                # maxlag=5 response: Wikimedia is under load — don't hammer it.
                raise WikiUnavailableError("MediaWiki is lagged/unavailable (maxlag)") from exc
            raise WikiUnavailableError(f"MediaWiki request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise WikiUnavailableError("Unexpected non-JSON MediaWiki response")
        if "error" in payload:
            raise WikiUnavailableError(f"MediaWiki error: {payload['error']}")
        return payload

    def search(self, query: str, *, limit: int) -> dict:
        """``list=search`` — cached 24 h (§3.2 stage 1)."""
        params: dict[str, object] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "srnamespace": 0,
            "format": "json",
            "formatversion": 2,
            "maxlag": MAXLAG_SECONDS,
        }
        key = self._cache_key(WIKI_API_ENDPOINT, params)
        return self._cached(key, SEARCH_CACHE_TTL_SECONDS, lambda: self._api_get(params))

    def extracts(self, titles: list[str]) -> dict:
        """``prop=extracts`` (plaintext intro) for a batch of titles — cached 7 d."""
        params: dict[str, object] = {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "exlimit": "max",
            "titles": "|".join(titles),
            "format": "json",
            "formatversion": 2,
            "maxlag": MAXLAG_SECONDS,
        }
        key = self._cache_key(WIKI_API_ENDPOINT, params)
        return self._cached(key, ARTICLE_CACHE_TTL_SECONDS, lambda: self._api_get(params))

    def extlinks(self, titles: list[str], *, max_pages: int = EXTLINKS_MAX_PAGES) -> dict[str, list[str]]:
        """``prop=extlinks`` with continuation — ``{article_title: [external_url, ...]}``.

        External links include both "External links" sections and references, which
        is exactly the hop-2 candidate set we want (§3.2 stage 3). The aggregated
        result is cached 7 d keyed on the requested titles.
        """
        params: dict[str, object] = {
            "action": "query",
            "prop": "extlinks",
            "ellimit": "max",
            "titles": "|".join(titles),
            "format": "json",
            "formatversion": 2,
            "maxlag": MAXLAG_SECONDS,
        }
        key = self._cache_key(WIKI_API_ENDPOINT, params)
        return self._cached(
            key,
            ARTICLE_CACHE_TTL_SECONDS,
            lambda: self._extlinks(params, max_pages),
        )

    def _extlinks(self, params: dict[str, object], max_pages: int) -> dict[str, list[str]]:
        collected: dict[str, list[str]] = {}
        for page_index in range(max_pages):
            payload = self._api_get(params)
            for page in payload.get("query", {}).get("pages", []):
                title = page.get("title")
                if not title:
                    continue
                urls = [link["url"] for link in page.get("extlinks", []) if link.get("url")]
                collected.setdefault(title, []).extend(urls)
            continuation = payload.get("continue")
            if not continuation or page_index == max_pages - 1:
                break
            params = {**params, **continuation}
        return collected

    # -- REST summary -----------------------------------------------------------------
    def summary(self, title: str) -> dict:
        """``GET /page/summary/{title}`` — lead extract + canonical URL — cached 7 d.

        ``maxlag`` is an action-API parameter only: the RESTBase endpoint does not
        accept it, so these requests rely on the shared session's UA/throttle
        politeness (the docstring in politeness covers the contract).
        A missing page returns HTTP 404, which we map to an empty dict rather than
        an error: a title can be deleted between discovery and read. The empty
        mapping is returned uncached so a republished page is picked up next call.
        """
        rest_title = quote(title.replace(" ", "_"), safe="")
        url = WIKI_REST_SUMMARY_ENDPOINT.format(title=rest_title)
        key = self._cache_key(url, None)
        return self._cached(
            key,
            ARTICLE_CACHE_TTL_SECONDS,
            lambda: self._summary(url),
            cache_empty=False,
        )

    def _summary(self, url: str) -> dict:
        try:
            payload = self.session.get_json(url)
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            if isinstance(response, requests.Response) and response.status_code == 404:
                return {}
            raise WikiUnavailableError(f"Wikipedia summary request failed: {exc}") from exc
        return payload if isinstance(payload, dict) else {}
