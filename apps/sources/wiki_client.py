"""Low-level MediaWiki / Wikimedia REST client used by the C1–C3 stages.

All requests go through a :class:`~apps.sources.politeness.PoliteSession`, and
every ``action=query`` call carries ``maxlag=5``. The client returns *raw parsed
JSON* (or aggregated structures); the stages in ``discovery`` / ``article_read``
/ ``citations`` decide how to interpret it. Keeping the wire layer dumb means the
stages can be exercised against recorded fixtures without a network.
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from .constants import (
    EXTLINKS_MAX_PAGES,
    MAXLAG_SECONDS,
    WIKI_API_ENDPOINT,
    WIKI_REST_SUMMARY_ENDPOINT,
)
from .politeness import PoliteSession


class WikiUnavailableError(RuntimeError):
    """Wikipedia/MediaWiki is down or rate-limiting us (maxlag 503).

    The caller degrades gracefully: the check proceeds *without hop-1 evidence*
    at reduced confidence (ARCHITECTURE.md §5) rather than failing the whole check.
    """


class WikiClient:
    """Thin typed wrapper over the MediaWiki action API and the REST summary API."""

    def __init__(self, session: PoliteSession | None = None) -> None:
        self.session = session or PoliteSession()

    # -- action=query primitives ------------------------------------------------------
    def _api_get(self, params: dict[str, object]) -> dict:
        try:
            payload = self.session.get_json(WIKI_API_ENDPOINT, params=params)
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code == 503:
                # maxlag=5 response: Wikimedia is under load — don't hammer it.
                raise WikiUnavailableError("MediaWiki is lagged/unavailable (maxlag)") from exc
            raise WikiUnavailableError(f"MediaWiki request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise WikiUnavailableError("Unexpected non-JSON MediaWiki response")
        if "error" in payload:
            raise WikiUnavailableError(f"MediaWiki error: {payload['error']}")
        return payload

    def search(self, query: str, *, limit: int) -> dict:
        """``list=search`` — return the raw search payload (§3.2 stage 1)."""
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
        return self._api_get(params)

    def extracts(self, titles: list[str]) -> dict:
        """``prop=extracts`` (plaintext intro) for a batch of article titles."""
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
        return self._api_get(params)

    def extlinks(self, titles: list[str], *, max_pages: int = EXTLINKS_MAX_PAGES) -> dict[str, list[str]]:
        """``prop=extlinks`` with continuation — ``{article_title: [external_url, ...]}``.

        External links include both "External links" sections and references, which
        is exactly the hop-2 candidate set we want (§3.2 stage 3).
        """
        collected: dict[str, list[str]] = {}
        params: dict[str, object] = {
            "action": "query",
            "prop": "extlinks",
            "ellimit": "max",
            "titles": "|".join(titles),
            "format": "json",
            "formatversion": 2,
            "maxlag": MAXLAG_SECONDS,
        }
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
        """``GET /page/summary/{title}`` — lead extract + canonical URL (§3.2 stage 2).

        A missing page returns HTTP 404, which we map to an empty dict rather than
        an error: a title can be deleted between discovery and read.
        """
        rest_title = quote(title.replace(" ", "_"), safe="")
        url = WIKI_REST_SUMMARY_ENDPOINT.format(title=rest_title)
        try:
            payload = self.session.get_json(url)
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code == 404:
                return {}
            raise WikiUnavailableError(f"Wikipedia summary request failed: {exc}") from exc
        return payload if isinstance(payload, dict) else {}
