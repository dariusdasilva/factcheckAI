"""C5 acceptance — the politeness layer.

"Rate-limiter unit test" (WORK_CHUNKS.md, Chunk C). C1–C3 and C4 all fetch through
:class:`~apps.sources.politeness.PoliteSession`, so these assert every non-negotiable
limit from ARCHITECTURE.md §3.2/§6: the Wikimedia User-Agent, ``maxlag=5`` on every
``action=query`` call, 1 req/s per host, one request at a time per host, a 10 s
timeout, and the content-type / page-size guards.
"""

from __future__ import annotations

import threading
import time

import pytest
import requests

from apps.sources.constants import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from apps.sources.politeness import PolitenessError, PoliteSession, RateLimiter


def _fast_session(**kwargs) -> PoliteSession:
    return PoliteSession(
        limiter=RateLimiter(min_interval_seconds=0.0, sleep=lambda _seconds: None), **kwargs
    )


def test_rate_limiter_spaces_requests_per_host():
    slept: list[float] = []
    limiter = RateLimiter(min_interval_seconds=1.0, sleep=slept.append)

    with limiter.slot("a.example.com"):
        pass
    assert slept == []

    with limiter.slot("a.example.com"):
        pass
    assert len(slept) == 1
    assert slept[0] > 0

    # A different host is not blocked by the first host's cooldown.
    with limiter.slot("b.example.com"):
        pass
    assert len(slept) == 1


def test_slot_serializes_concurrent_requests_to_same_host():
    order: list[str] = []
    limiter = RateLimiter(min_interval_seconds=0.0, sleep=lambda _s: None)

    def work(tag: str) -> None:
        with limiter.slot("shared.example"):
            order.append(f"{tag}:enter")
            time.sleep(0.02)
            order.append(f"{tag}:exit")

    threads = [threading.Thread(target=work, args=(tag,)) for tag in ("one", "two", "three")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Each worker's enter/exit must stay adjacent: no interleaved requests.
    for index in range(0, len(order), 2):
        enter_tag = order[index].split(":")[0]
        assert order[index].endswith(":enter")
        assert order[index + 1] == f"{enter_tag}:exit"


def test_default_timeout_is_ten_seconds():
    assert PoliteSession().timeout == DEFAULT_TIMEOUT_SECONDS == 10.0


def test_get_forwards_the_timeout_and_streaming(monkeypatch):
    session = _fast_session()
    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {"Content-Type": "application/json"}
        content = b"{}"
        url = "https://example.com/x"

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=None):
            yield self.content

        def close(self):
            return None

    def _fake_get(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(session.session, "get", _fake_get)
    session.get("https://example.com/x")

    assert captured["timeout"] == 10.0
    # Bodies are streamed so oversized pages are cut mid-download, not after.
    assert captured["stream"] is True


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


def test_oversized_page_is_cut_midstream_not_downloaded_whole(monkeypatch):
    # No declared Content-Length: the guard must fire while streaming, so the
    # bytes past the cap are never consumed (§6 ~1MB cap is a transmission-
    # level guarantee, not just a post-download check).
    session = _fast_session(max_bytes=8)
    iterated: list[int] = []

    class _StreamedResponse:
        headers = {"Content-Type": "text/html"}
        url = "https://example.com/trickling"

        def iter_content(self, chunk_size=None):
            for index, chunk in enumerate([b"a" * 5, b"b" * 5, b"c" * 5]):
                iterated.append(index)
                yield chunk

        def close(self):
            return None

    def _fake_get(url, **kwargs):
        assert kwargs["stream"] is True
        return _StreamedResponse()

    monkeypatch.setattr(session.session, "get", _fake_get)

    with pytest.raises(PolitenessError):
        session.get("https://example.com/trickling")

    # The third chunk (past the cap) was never read off the wire.
    assert iterated == [0, 1]


def test_per_request_headers_cannot_override_the_user_agent(requests_mock):
    requests_mock.get("https://example.com/x", json={})

    _fast_session().get("https://example.com/x", headers={"User-Agent": "evil-bot/1.0"})

    assert requests_mock.last_request.headers["User-Agent"] == USER_AGENT


def test_default_limiter_is_process_global():
    # Two independently-constructed PoliteSessions (e.g. two concurrent Django-Q2
    # checks) must share the same per-host bookkeeping (AGENTS.md §5 "shared
    # rate-limited HTTP session").
    from apps.sources.politeness import DEFAULT_LIMITER

    assert PoliteSession().limiter is DEFAULT_LIMITER
    assert PoliteSession(session=requests.Session()).limiter is DEFAULT_LIMITER
