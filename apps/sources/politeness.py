"""Shared rate-limited HTTP session for every outbound fetch in Chunk C.

AGENTS.md §5 (Chunk C): *"politeness limits are not optional performance tweaks;
they're a condition of being allowed to talk to Wikipedia's API at all. Any new
fetch path goes through the shared rate-limited HTTP session."*

This module is that session. C1–C3 (and the later source fetcher, C4) must obtain
their HTTP client from here rather than calling ``requests`` directly, so the
:data:`~apps.sources.constants.PER_HOST_MIN_INTERVAL_SECONDS` spacing, the
Wikimedia User-Agent, ``maxlag=5`` and the content-type/size guards cannot be
bypassed by accident.

The full C5 politeness test-suite extends this module; the limits themselves live
in ``constants.py`` so they stay in one place.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
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


class PolitenessError(RuntimeError):
    """Raised when a response violates the politeness contract.

    Currently fired on disallowed content types and oversized pages — the two
    ways a response can be "rude to accept" without being an HTTP error.
    """


@dataclass
class RateLimiter:
    """Enforces a minimum interval between requests to the same host.

    State is kept per host so different hosts don't block one another, but the
    lock serialises the bookkeeping (the Django-Q2 worker pool may call from
    several threads; we still keep concurrency to one request per host).

    ``sleep`` is injectable so tests can run at zero wall-clock cost.
    """

    min_interval_seconds: float = PER_HOST_MIN_INTERVAL_SECONDS
    sleep: Callable[[float], None] = time.sleep
    _last_call: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(host)
            if last is not None:
                remaining = self.min_interval_seconds - (now - last)
                if remaining > 0:
                    self.sleep(remaining)
                    now = time.monotonic()
            self._last_call[host] = now


class PoliteSession:
    """A ``requests.Session`` wrapper that cannot be impolite.

    - reuses one connection pool (keep-alive) across the whole pipeline;
    - throttles per host via :class:`RateLimiter`;
    - sets the Wikimedia User-Agent on every request;
    - enforces the content-type allowlist and the ~1 MB page cap.
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
        self.limiter = limiter or RateLimiter()
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
        """Throttled GET with content-type and size guards.

        Raises :class:`PolitenessError` for a disallowed type or oversized body.
        HTTP status errors are left to the caller (``raise_for_status``) so the
        pipeline can degrade gracefully on 404 / 503 (ARCHITECTURE.md §5).
        """
        host = urlsplit(url).netloc
        self.limiter.wait(host)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        self._check_content_type(response, allow_pdf=allow_pdf)
        self._check_size(response)
        return response

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> object:
        """Throttled GET that raises for HTTP errors and returns parsed JSON."""
        response = self.get(url, params=params)
        response.raise_for_status()
        return response.json()

    # -- guards -----------------------------------------------------------------------
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
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    raise PolitenessError(
                        f"Refusing {declared} byte body from {response.url!r} "
                        f"(cap ~{self.max_bytes} bytes)"
                    )
            except ValueError:
                pass
        if len(response.content) > self.max_bytes:
            raise PolitenessError(
                f"Refusing {len(response.content)} byte body from {response.url!r} "
                f"(cap ~{self.max_bytes} bytes)"
            )
