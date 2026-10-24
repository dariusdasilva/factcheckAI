"""Audit-driven tests: §6 robots.txt compliance for non-Wikipedia sources.

Covers disallowed URLs (recorded as ``skipped``, page never fetched), permissive
and absent robots.txt, 5xx fail-open behaviour, per-domain caching of robots.txt,
and the Wikimedia exemption (Wiki politeness is maxlag + User-Agent, not robots).
"""

from __future__ import annotations

import pytest

from apps.checks.models import EvidenceFetchStatus
from apps.sources.citations import CitedSource
from apps.sources.robots import RobotsChecker
from apps.sources.source_fetch import fetch_source

WEBMD_URL = "https://www.webmd.com/diet/health-benefits-coffee"

_ROBOTS_BLOCK_DIET = "User-agent: *\nDisallow: /diet/\n"
_ROBOTS_ALLOW_ALL = "User-agent: *\nDisallow:\n"


def _citation(url: str, domain: str) -> CitedSource:
    return CitedSource(url=url, domain=domain, source_articles=("Coffee",))


@pytest.mark.django_db
def test_disallowed_url_is_skipped_without_fetching(requests_mock, fast_session):
    requests_mock.get(
        "https://www.webmd.com/robots.txt",
        text=_ROBOTS_BLOCK_DIET,
        headers={"Content-Type": "text/plain"},
    )
    requests_mock.get(
        WEBMD_URL,
        text="<html><body><p>should never be fetched</p></body></html>",
        headers={"Content-Type": "text/html"},
    )

    row = fetch_source(_citation(WEBMD_URL, "webmd.com"), session=fast_session)

    assert row.fetch_status == EvidenceFetchStatus.SKIPPED
    assert row.text_extract == ""
    assert all(request.url != WEBMD_URL for request in requests_mock.request_history)


def test_allowed_url_fetches(requests_mock, fast_session):
    requests_mock.get(
        "https://example.org/robots.txt",
        text=_ROBOTS_ALLOW_ALL,
        headers={"Content-Type": "text/plain"},
    )

    assert RobotsChecker(session=fast_session).can_fetch("https://example.org/page") is True


def test_missing_robots_404_allows_everything(requests_mock, fast_session):
    requests_mock.get("https://example.org/robots.txt", status_code=404)

    assert RobotsChecker(session=fast_session).can_fetch("https://example.org/any") is True


def test_unreachable_robots_fails_open(requests_mock, fast_session):
    requests_mock.get("https://example.org/robots.txt", status_code=500)

    assert RobotsChecker(session=fast_session).can_fetch("https://example.org/page") is True


def test_unreachable_robots_is_backoff_cached_not_refetched(requests_mock, fast_session):
    robots_url = "https://example.org/robots.txt"
    requests_mock.get(robots_url, status_code=500)
    checker = RobotsChecker(session=fast_session)

    checker.can_fetch("https://example.org/a")
    checker.can_fetch("https://example.org/b")

    # The second call must not re-request a 5xx robots.txt (short backoff cached).
    robots_calls = [r for r in requests_mock.request_history if r.url == robots_url]
    assert len(robots_calls) == 1


def test_robots_txt_fetched_once_per_domain(requests_mock, fast_session):
    robots_url = "https://example.org/robots.txt"
    requests_mock.get(
        robots_url, text=_ROBOTS_ALLOW_ALL, headers={"Content-Type": "text/plain"}
    )
    checker = RobotsChecker(session=fast_session)

    checker.can_fetch("https://example.org/a")
    checker.can_fetch("https://example.org/b")

    robots_calls = [r for r in requests_mock.request_history if r.url == robots_url]
    assert len(robots_calls) == 1


def test_wikimedia_hosts_are_exempt(fast_session):
    checker = RobotsChecker(session=fast_session)

    # No robots.txt call is made for Wikimedia hosts.
    assert checker.can_fetch("https://en.wikipedia.org/wiki/Coffee") is True
    assert checker.can_fetch("https://www.wikidata.org/entity/Q43") is True
