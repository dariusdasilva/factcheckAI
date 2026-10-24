"""Shared, hermetic fixtures for the Chunk C (Wikipedia pipeline) tests.

No test in this package performs a live network call (CI_CD.md: "CI must stay
hermetic"). Recorded MediaWiki/Wikimedia response shapes live under
``tests/fixtures/wikipedia/`` and are replayed through ``requests-mock``. The
``wiki_client`` fixture injects a zero-interval rate limiter so the 1 req/s
politeness spacing does not slow the suite — the spacing itself is asserted
separately.
"""

from __future__ import annotations

import json
from pathlib import Path

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


@pytest.fixture
def wiki_client() -> WikiClient:
    """A WikiClient wired to a polite session that never sleeps."""
    limiter = RateLimiter(min_interval_seconds=0.0, sleep=lambda _seconds: None)
    return WikiClient(PoliteSession(limiter=limiter))


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
    return requests_mock
