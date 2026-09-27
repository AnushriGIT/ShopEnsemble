"""A small in-memory store of per-conversation context (Phase 5 spec B6).

Mirrors ``app/api/cache.py`` on purpose — same reasoning, same shape:

- **Process state belongs in the API layer.** ``ConversationContext`` itself is
  pure and lives in ``app/agents/conversation.py``; *where contexts are kept*
  (keyed by session ID, expiring when idle) is a "serving HTTP requests"
  concern. The CLI is a fresh process per invocation, so an in-memory store
  would never persist between CLI calls anyway.
- **Hand-rolled, not a dependency.** Single process, in-memory, fixed limits —
  small enough that a library wouldn't meaningfully reduce code.
- **Not thread-safe by design.** The API runs one asyncio event loop, not
  multiple OS threads, so a lock would be pure overhead.
- **Known limitation:** memory is per process, so ``uvicorn --workers N`` (N>1)
  would lose sessions across workers, and a restart forgets every conversation.
  Both are intended — memory is ephemeral by spec. The upgrade path, if it were
  ever needed, is an external store such as Redis behind this same interface.

Bounds (spec B3/B10): a sliding idle TTL (activity keeps a conversation alive,
only idle time expires it) and a hard cap on the number of sessions, evicting
the least-recently-used first — unbounded memory would be a denial-of-service
surface.
"""

import os
import time

from app.agents.conversation import MAX_TURNS, ConversationContext

SESSION_TTL_SECONDS_ENV = "SHOPENSEMBLE_SESSION_TTL_SECONDS"
SESSION_MAX_TURNS_ENV = "SHOPENSEMBLE_SESSION_MAX_TURNS"
DEFAULT_SESSION_TTL_SECONDS = 1800.0
DEFAULT_MAX_SESSIONS = 1000


class SessionStore:
    """Maps a ``session_id`` to that conversation's ``ConversationContext``."""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_turns: int | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds if ttl_seconds is not None else _default_ttl_seconds()
        self._max_sessions = max_sessions
        self._max_turns = max_turns if max_turns is not None else _default_max_turns()
        # session_id -> (context, expires_at). Insertion order doubles as
        # recency order: every read/write re-inserts, so the first key is the
        # least recently used.
        self._entries: dict[str, tuple[ConversationContext, float]] = {}

    @property
    def max_turns(self) -> int:
        """How many turns a context may keep — passed to
        ``ConversationContext.with_turn`` so the env override applies without
        ``app/agents`` ever reading the environment."""

        return self._max_turns

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, session_id: str) -> ConversationContext:
        """Return the session's context, or an empty one if unknown/expired.

        A hit refreshes the sliding TTL (and marks the session most recently
        used). An expired entry is dropped, not merely hidden.
        """

        entry = self._entries.pop(session_id, None)
        if entry is None:
            return ConversationContext()
        context, expires_at = entry
        now = time.monotonic()
        if now >= expires_at:
            return ConversationContext()
        self._entries[session_id] = (context, now + self._ttl_seconds)
        return context

    def save(self, session_id: str, context: ConversationContext) -> None:
        """Store ``context`` for ``session_id``, evicting the least recently
        used session first if this would exceed the capacity."""

        self._entries.pop(session_id, None)  # re-insert at the end; also means an update never evicts another
        while len(self._entries) >= self._max_sessions:
            del self._entries[next(iter(self._entries))]
        self._entries[session_id] = (context, time.monotonic() + self._ttl_seconds)

    def clear(self, session_id: str) -> None:
        """Forget a session. Idempotent: clearing an unknown session is a no-op."""

        self._entries.pop(session_id, None)


def _default_ttl_seconds() -> float:
    raw = os.getenv(SESSION_TTL_SECONDS_ENV)
    return float(raw) if raw else DEFAULT_SESSION_TTL_SECONDS


def _default_max_turns() -> int:
    raw = os.getenv(SESSION_MAX_TURNS_ENV)
    return int(raw) if raw else MAX_TURNS


# One instance for the process's lifetime, exposed through a Depends-style
# provider rather than imported directly — the same reason
# ``app/api/cache.py::get_query_cache`` exists: it's what lets a test swap in a
# fresh, isolated SessionStore instead of sharing this module-level one across
# every test in the same process.
_session_store: SessionStore = SessionStore()


def get_session_store() -> SessionStore:
    return _session_store
