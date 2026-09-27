"""A small in-memory TTL cache for repeated /query requests.

Phase 4b implementation plan's "Caching" design: exact-string-match only
(no semantic/vector caching — Appendix B already rules that out, not
triggered by any measured cost/latency problem), hand-rolled rather than a
new dependency (the actual logic needed here — single-process, in-memory,
fixed TTL — is small enough that a library wouldn't meaningfully reduce
code), and placed here in app/api/ rather than app/agents/ since caching is
specifically a "serving repeated HTTP requests" concern — the CLI is a
fresh process per invocation, so an in-memory cache would never even
persist between CLI calls.
"""

import os
import time
from typing import Generic, TypeVar

CACHE_TTL_SECONDS_ENV = "SHOPENSEMBLE_CACHE_TTL_SECONDS"
DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_CACHE_MAX_SIZE = 256

T = TypeVar("T")


class TTLCache(Generic[T]):
    """A tiny dict-based cache with a fixed time-to-live per entry.

    Not thread-safe by design — this project's API runs a single asyncio
    event loop, not multiple OS threads, so a lock would be pure overhead.
    Eviction is deliberately simple (drop the oldest entry once over
    ``max_size``) rather than true LRU — proportionate to a capstone's
    single-process, no-measured-load scale (same reasoning Appendix B
    already applies to skipping vector semantic caching and circuit
    breakers).
    """

    def __init__(self, ttl_seconds: float | None = None, max_size: int = DEFAULT_CACHE_MAX_SIZE) -> None:
        self._ttl_seconds = ttl_seconds if ttl_seconds is not None else _default_ttl_seconds()
        self._max_size = max_size
        self._entries: dict[str, tuple[T, float]] = {}  # key -> (value, expires_at)

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if len(self._entries) >= self._max_size and key not in self._entries:
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]
        self._entries[key] = (value, time.monotonic() + self._ttl_seconds)


def _default_ttl_seconds() -> float:
    raw = os.getenv(CACHE_TTL_SECONDS_ENV)
    return float(raw) if raw else DEFAULT_CACHE_TTL_SECONDS


# One instance for the process's lifetime (spec Section 7's "instantiate
# once" idiom), exposed through a Depends-style provider rather than
# imported directly — the same reason app/api/dependencies.py::get_app_state
# exists: it's what lets a test swap in a fresh, isolated TTLCache instead
# of sharing this module-level one across every test in the same process.
_query_cache: TTLCache = TTLCache()


def get_query_cache() -> TTLCache:
    return _query_cache
