"""Shared rate-limited HTTP session for every outbound fetch in Chunk C.

AGENTS.md §5 (Chunk C): *"politeness limits are not optional performance tweaks;
they're a condition of being allowed to talk to Wikipedia's API at all. Any new
fetch path goes through the shared rate-limited HTTP session."*

This module is that session. C1–C3 (and the C4 source fetcher + robots checker)
must obtain their HTTP client from here rather than calling ``requests``
directly, so the :data:`~apps.sources.constants.PER_HOST_MIN_INTERVAL_SECONDS`
spacing, one-request-at-a-time-per-host, the Wikimedia User-Agent, ``maxlag=5``
and the content-type/size guards cannot be bypassed by accident.

The limiter enforcing the limits is **process-global** (``DEFAULT_LIMITER``): one
Django-Q2 worker calling :class:`PoliteSession` without arguments still shares
the same per-host bookkeeping, which is what keeps concurrent checks polite. A
caller may inject a limiter/session for tests; production always shares.

Note for the doc reader: ARCHITECTURE.md's "HTTP/2 keep-alive" is approximated
with a Python-``requests`` session (HTTP/1.1 keep-alive via one connection pool).
Upgrading to ``httpx`` for real HTTP/2 would be transparent to callers.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests

from .constants import (
    ALLOWED_CONTENT_TYPES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_PAGE_BYTES,
    PDF_CONTENT_TYPE,
    PER_HOST_MIN_INTERVAL_SECONDS,
    USER_AGENT,
)

_STREAM_CHUNK_BYTES = 65_536


class PolitenessError(RuntimeError):
    """Raised when a response violates the politeness contract.

    Currently fired on disallowed content types and oversized pages — the two
    ways a response can be "rude to accept" without being an HTTP error.
    """


@dataclass
class RateLimiter:
    """Enforces per-host spacing *and* one request at a time per host.

    ``slot(host)`` holds a per-host lock around the whole request, so parallel
    callers (e.g. Django-Q2 workers) can never overlap requests to the same host,
    and the request-start spacing is guaranteed. Different hosts use different
    locks and do not block one another.

    ``sleep`` is injectable so tests can run at zero wall-clock cost.
    """

    min_interval_seconds: float = PER_HOST_MIN_INTERVAL_SECONDS
    sleep: Callable[[float], None] = time.sleep
    _last_call: dict[str, float] = field(default_factory=dict)
    _host_locks: dict[str, threading.Lock] = field(default_factory=dict)
    _meta_lock: threading.Lock = field(default_factory=threading.Lock)

    def _lock_for(self, host: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    @contextmanager
    def slot(self, host: str) -> Iterator[None]:
        """Hold the host slot across a request (concurrency 1 + start spacing)."""
        with self._lock_for(host):
            now = time.monotonic()
            last = self._last_call.get(host)
            if last is not None:
                remaining = self.min_interval_seconds - (now - last)
                if remaining > 0:
                    self.sleep(remaining)
                    now = time.monotonic()
            self._last_call[host] = now
            yield

    def wait(self, host: str) -> None:
        """Compatibility wrapper: take and release the host slot immediately."""
        with self.slot(host):
            return


#: The process-global limiter every ``PoliteSession()`` shares (see module docstring).
DEFAULT_LIMITER = RateLimiter()


class PoliteSession:
    """A ``requests.Session`` wrapper that cannot be impolite.

    - reuses one connection pool (keep-alive) across the whole pipeline;
    - throttles per host via the shared :class:`RateLimiter`;
    - sets the Wikimedia User-Agent on every request and never lets a per-request
      header override it;
    - streams every body (capped hosts down not megabytes before the guard fires)
      and enforces the content-type allowlist and the ~1 MB page cap.
    """

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        limiter: RateLimiter | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allowed_content_types: frozenset[str] = ALLOWED_CONTENT_TYPES,
        max_bytes: int = MAX_PAGE_BYTES,
    ) -> None:
        self.session = session or requests.Session()
        # Override unconditionally: requests' default UA is rejected by Wikimedia's
        # User-Agent policy, so a politeness session must always identify us.
        self.session.headers["User-Agent"] = USER_AGENT
        self.limiter = limiter or DEFAULT_LIMITER
        self.timeout = timeout
        self.allowed_content_types = allowed_content_types
        self.max_bytes = max_bytes

    def close(self) -> None:
        self.session.close()

    def get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        allow_pdf: bool = False,
    ) -> requests.Response:
        """Throttled, streamed GET with content-type and size guards.

        Raises :class:`PolitenessError` for a disallowed type or oversized body.
        HTTP status errors are left to the caller (``raise_for_status``) so the
        pipeline can degrade gracefully on 404 / 503 (ARCHITECTURE.md §5).
        """
        effective_headers = self._effective_headers(headers)
        host = urlsplit(url).netloc
        with self.limiter.slot(host):
            streamed = self.session.get(
                url,
                params=params,
                headers=effective_headers,
                timeout=self.timeout,
                stream=True,
            )
            try:
                self._check_content_type(streamed, allow_pdf=allow_pdf)
                self._declared_size(streamed)
                self._read_capped(streamed)
                self._check_size(streamed)
            finally:
                streamed.close()
        return streamed

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> object:
        """Throttled GET that raises for HTTP errors and returns parsed JSON."""
        response = self.get(url, params=params)
        response.raise_for_status()
        return response.json()

    # -- politeness helpers -----------------------------------------------------------
    def _effective_headers(self, headers: dict[str, str] | None) -> dict[str, str] | None:
        """Merge per-request headers, but never let them replace the session UA."""
        if not headers:
            return None
        merged = {key: value for key, value in headers.items() if key.lower() != "user-agent"}
        return merged or None

    def _declared_size(self, response: requests.Response) -> None:
        """Reject an oversized declared body before downloading it."""
        declared = response.headers.get("Content-Length")
        if declared is None:
            return
        try:
            declared_len = int(declared)
        except ValueError:
            return
        if declared_len > self.max_bytes:
            raise PolitenessError(
                f"Refusing {declared_len} byte body from {response.url!r} "
                f"(cap ~{self.max_bytes} bytes)"
            )

    def _read_capped(self, response: requests.Response) -> None:
        """Stream the body, buffering at most ``max_bytes``, then expose it to callers.

        ``response._content`` is assigned (as ``requests`` itself does) so callers
        can use ``response.content``/``.json()`` after the streamed read closes.
        """
        buffered = bytearray()
        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK_BYTES):
            buffered.extend(chunk)
            if len(buffered) > self.max_bytes:
                raise PolitenessError(
                    f"Refusing body from {response.url!r}: exceeded ~{self.max_bytes} "
                    "bytes mid-stream (cap ~1 MB, §6)"
                )
        response._content = bytes(buffered)

    def _check_content_type(self, response: requests.Response, *, allow_pdf: bool) -> None:
        raw = response.headers.get("Content-Type")
        if not raw:
            # No declared type (e.g. a bare test stub): nothing to enforce against.
            return
        content_type = raw.split(";", 1)[0].strip().lower()
        allowed = set(self.allowed_content_types)
        if allow_pdf:
            allowed.add(PDF_CONTENT_TYPE)
        if content_type not in allowed:
            raise PolitenessError(
                f"Refusing content-type {content_type!r} from {response.url!r} "
                f"(allowed: {sorted(allowed)})"
            )

    def _check_size(self, response: requests.Response) -> None:
        if len(response.content) > self.max_bytes:
            raise PolitenessError(
                f"Refusing {len(response.content)} byte body from {response.url!r} "
                f"(cap ~{self.max_bytes} bytes)"
            )
