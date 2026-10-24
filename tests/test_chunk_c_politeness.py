"""C5 acceptance — the politeness layer.

"Rate-limiter unit test" (WORK_CHUNKS.md, Chunk C). C1–C3 and C4 all fetch through
:class:`~apps.sources.politeness.PoliteSession`, so these assert every non-negotiable
limit from ARCHITECTURE.md §3.2/§6: the Wikimedia User-Agent, ``maxlag=5`` on every
``action=query`` call, 1 req/s per host, a 10 s timeout, and the content-type /
page-size guards.
"""

from __future__ import annotations

import pytest

from apps.sources.constants import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
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


def test_default_timeout_is_ten_seconds():
    assert PoliteSession().timeout == DEFAULT_TIMEOUT_SECONDS == 10.0


def test_get_forwards_the_timeout(monkeypatch):
    session = _fast_session()
    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {"Content-Type": "application/json"}
        content = b"{}"
        url = "https://example.com/x"

        def raise_for_status(self):
            return None

    def _fake_get(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(session.session, "get", _fake_get)
    session.get("https://example.com/x")

    assert captured["timeout"] == 10.0


def test_session_sets_wikimedia_user_agent():
    session = _fast_session()

    assert session.session.headers["User-Agent"] == USER_AGENT


def test_user_agent_is_sent_on_the_wire(requests_mock):
    requests_mock.get("https://example.com/x", json={})

    _fast_session().get("https://example.com/x")

    assert requests_mock.last_request.headers["User-Agent"] == USER_AGENT


def test_every_action_api_call_carries_maxlag(wiki_api, wiki_client):
    from apps.sources.discovery import discover_articles

    discover_articles("coffee cold", client=wiki_client)
    wiki_client.extracts(["Coffee"])
    wiki_client.extlinks(["Coffee"])

    api_calls = [r for r in wiki_api.request_history if r.url.startswith("https://en.wikipedia.org/w/api.php")]
    assert api_calls, "expected at least one action=query call"
    assert all(call.qs["maxlag"] == ["5"] for call in api_calls)


def test_session_rejects_disallowed_content_type(requests_mock):
    requests_mock.get(
        "https://example.com/data",
        content=b"\x00\x01",
        headers={"Content-Type": "application/octet-stream"},
    )

    with pytest.raises(PolitenessError):
        _fast_session().get("https://example.com/data")


def test_session_accepts_json(requests_mock):
    requests_mock.get("https://example.com/data", json={"ok": True})

    response = _fast_session().get("https://example.com/data")

    assert response.json() == {"ok": True}


def test_pdf_is_only_allowed_when_opted_in(requests_mock):
    requests_mock.get(
        "https://example.com/report.pdf",
        content=b"%PDF-1.4",
        headers={"Content-Type": "application/pdf"},
    )

    with pytest.raises(PolitenessError):
        _fast_session().get("https://example.com/report.pdf")

    response = _fast_session().get("https://example.com/report.pdf", allow_pdf=True)
    assert response.content == b"%PDF-1.4"


def test_session_rejects_oversized_page(requests_mock):
    requests_mock.get(
        "https://example.com/big",
        content=b"x" * 10,
        headers={"Content-Type": "text/html", "Content-Length": "10"},
    )

    with pytest.raises(PolitenessError):
        _fast_session(max_bytes=5).get("https://example.com/big")
