"""Simple in-memory rate limiting for POST /query.

Phase 4b implementation plan's "Rate limiting" design: a hand-rolled fixed-
window counter keyed by client IP, applied only to /query via `Depends`
(not /health, which monitoring/the UI's sidebar indicator must always be
able to reach). Single-process, in-memory — a multi-process/distributed
deployment would need something like slowapi+Redis instead; no such
deployment target exists for this capstone (Appendix B), and the actual
logic needed at this scale is small enough that a library wouldn't
meaningfully reduce code.
"""

import os
import time

from fastapi import Request

RATE_LIMIT_PER_MINUTE_ENV = "SHOPENSEMBLE_RATE_LIMIT_PER_MINUTE"
DEFAULT_RATE_LIMIT_PER_MINUTE = 20
WINDOW_SECONDS = 60.0


class RateLimitExceeded(Exception):
    """Raised when a client exceeds the per-minute request limit — caught by
    a dedicated exception handler in app/api/main.py (a 429 with the
    existing AgentErrorEnvelope shape), never falling through to the
    generic 500 handler."""


class FixedWindowRateLimiter:
    """A basic fixed window, not a sliding one — a client can burst up to 2x
    the limit right at a window boundary. Acceptable for a "generous abuse
    control" (no numeric rate-limit target exists in either governing
    spec), not precise rate shaping.
    """

    def __init__(self, requests_per_minute: int | None = None) -> None:
        self._limit = requests_per_minute if requests_per_minute is not None else _default_limit()
        self._windows: dict[str, tuple[int, float]] = {}  # key -> (count, window_start)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= WINDOW_SECONDS:
            count, window_start = 0, now
        count += 1
        self._windows[key] = (count, window_start)
        return count <= self._limit


def _default_limit() -> int:
    raw = os.getenv(RATE_LIMIT_PER_MINUTE_ENV)
    return int(raw) if raw else DEFAULT_RATE_LIMIT_PER_MINUTE


_limiter = FixedWindowRateLimiter()


def check_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not _limiter.allow(client_host):
        raise RateLimitExceeded(f"Rate limit exceeded for {client_host}.")
