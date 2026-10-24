"""Shared-session politeness smoke tests (foundation for C5).

C1–C3 all fetch through :class:`~apps.sources.politeness.PoliteSession`, so these
assert the guards that protect the outbound path: per-host spacing, the content-type
allowlist and the page-size cap. The full C5 suite extends this.
"""

from __future__ import annotations

import pytest

from apps.sources.constants import USER_AGENT
from apps.sources.politeness import PolitenessError, PoliteSession, RateLimiter


def _fast_session(**kwargs) -> PoliteSession:
    return PoliteSession(
        limiter=RateLimiter(min_interval_seconds=0.0, sleep=lambda _seconds: None), **kwargs
    )


def test_rate_limiter_spaces_requests_per_host():
    slept: list[float] = []
    limiter = RateLimiter(min_interval_seconds=1.0, sleep=slept.append)

    limiter.wait("a.example.com")
    assert slept == []

    limiter.wait("a.example.com")
    assert len(slept) == 1
    assert slept[0] > 0

    # A different host is not blocked by the first host's cooldown.
    limiter.wait("b.example.com")
    assert len(slept) == 1


def test_session_sets_wikimedia_user_agent():
    session = _fast_session()

    assert session.session.headers["User-Agent"] == USER_AGENT


def test_session_rejects_disallowed_content_type(requests_mock):
    requests_mock.get(
        "https://example.com/data",
        content=b"\x00\x01",
        headers={"Content-Type": "application/octet-stream"},
    )

    with pytest.raises(PolitenessError):
        _fast_session().get("https://example.com/data")


def test_session_rejects_oversized_page(requests_mock):
    requests_mock.get(
        "https://example.com/big",
        content=b"x" * 10,
        headers={"Content-Type": "text/html", "Content-Length": "10"},
    )

    with pytest.raises(PolitenessError):
        _fast_session(max_bytes=5).get("https://example.com/big")
