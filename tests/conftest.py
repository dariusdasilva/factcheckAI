"""Shared pytest configuration for the test suite.

Cache isolation: pytest-django resets the database between tests (so user pks
restart at 1) while Django's cache survives the whole session. Without an
autouse reset, throttle history written by one test leaks into another's user
(e.g. a test's first authenticated request inherits the previous test's 429).

Chunk C hermeticity: no test in this package performs a live network call
(CI_CD.md: "CI must stay hermetic"). Recorded MediaWiki/Wikimedia response
shapes live under ``tests/fixtures/wikipedia/`` and are replayed through
``requests-mock``. The ``wiki_client`` fixture injects a zero-interval rate
limiter so the 1 req/s politeness spacing does not slow the suite — the
spacing itself is asserted separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from apps.sources.politeness import PoliteSession, RateLimiter
from apps.sources.wiki_client import WikiClient

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wikipedia"

WIKI_API = "https://en.wikipedia.org/w/api.php"
SUMMARY_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def load_text_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolate_caches():
    """Reset Django's cache per test.

    The wiki response cache, robots cache and (Chunk B) throttle history all
    live in Django's cache framework (LocMem in dev/CI), which is
    process-global — without a per-test reset a cached payload or rate-limit
    counter could leak across tests.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def wiki_client() -> WikiClient:
    """A WikiClient wired to a polite session that never sleeps."""
    limiter = RateLimiter(min_interval_seconds=0.0, sleep=lambda _seconds: None)
    return WikiClient(PoliteSession(limiter=limiter))


@pytest.fixture
def fast_session() -> PoliteSession:
    """A dignified-but-impatient session for tests: no rate-limit sleeping."""
    return PoliteSession(limiter=RateLimiter(min_interval_seconds=0.0, sleep=lambda _s: None))


# Cited sources referenced by ``extlinks_*`` fixtures → recorded hop-2 pages.
SOURCE_PAGES = {
    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/": "source_ncbi.html",
    "https://www.hsph.harvard.edu/news/coffee/": "source_harvard.html",
    "https://www.cdc.gov/common-cold/": "source_cdc.html",
    "https://www.webmd.com/diet/health-benefits-coffee": "source_webmd.html",
}

ROBOTS_ALLOW_ALL = "User-agent: *\nDisallow:\n"


@pytest.fixture
def source_pages(requests_mock):
    """Register recorded hop-2 pages *and* permissive robots.txt per host."""
    for url, fixture in SOURCE_PAGES.items():
        requests_mock.get(
            url,
            text=load_text_fixture(fixture),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
        host = urlsplit(url).netloc
        requests_mock.get(
            f"https://{host}/robots.txt",
            text=ROBOTS_ALLOW_ALL,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    return requests_mock


def _api_dispatch(request, _context):
    """Route an ``action=query`` request to the matching recorded fixture."""
    query = request.qs
    if query.get("list", [""])[0] == "search":
        return load_fixture("search_full.json")
    prop = query.get("prop", [""])[0]
    if prop == "extracts":
        return load_fixture("extracts_two_articles.json")
    if prop == "extlinks":
        if "eloffset" in query:
            return load_fixture("extlinks_continuation_page.json")
        return load_fixture("extlinks_first_page.json")
    raise AssertionError(f"unexpected MediaWiki request: {request.url}")


@pytest.fixture
def wiki_api(requests_mock):
    """Register all replayed Wikimedia endpoints on the requests_mock adapter."""
    requests_mock.get(WIKI_API, json=_api_dispatch)
    requests_mock.get(SUMMARY_BASE + "Coffee", json=load_fixture("summary_coffee.json"))
    requests_mock.get(
        SUMMARY_BASE + "Common_cold", json=load_fixture("summary_common_cold.json")
    )
    requests_mock.get(SUMMARY_BASE + "Caffeine", json=load_fixture("summary_caffeine.json"))
    return requests_mock
