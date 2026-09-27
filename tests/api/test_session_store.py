"""Unit tests for SessionStore (Phase 5 spec B6).

Same approach as ``test_cache.py``: exercise expiry with a tiny TTL and a real
short sleep rather than monkeypatching the clock.
"""

import time

from app.agents.conversation import ConversationContext, TurnFacts
from app.agents.data import CatalogData
from app.api.session_store import SessionStore

_EMPTY_CATALOG = CatalogData(products=[], reviews=[], policies=[])


def _context(message: str = "hi") -> ConversationContext:
    return ConversationContext().with_turn(message, TurnFacts(tool="policy_faq_agent"), _EMPTY_CATALOG)


def test_an_unknown_session_yields_an_empty_context():
    store = SessionStore(ttl_seconds=60)

    assert store.get("a" * 32).is_empty


def test_save_then_get_returns_the_saved_context():
    store = SessionStore(ttl_seconds=60)
    store.save("a" * 32, _context("remember me"))

    assert store.get("a" * 32).turns[0].message == "remember me"


def test_sessions_are_isolated_from_each_other():
    store = SessionStore(ttl_seconds=60)
    store.save("a" * 32, _context("A's secret"))

    assert store.get("b" * 32).is_empty


def test_an_idle_session_expires():
    store = SessionStore(ttl_seconds=0.05)
    store.save("a" * 32, _context())
    time.sleep(0.1)

    assert store.get("a" * 32).is_empty
    assert len(store) == 0  # the expired entry was dropped, not just hidden


def test_reading_a_session_refreshes_its_ttl():
    # Sliding TTL: activity keeps a conversation alive; only *idle* time expires it.
    store = SessionStore(ttl_seconds=0.15)
    store.save("a" * 32, _context())
    for _ in range(3):
        time.sleep(0.07)
        assert not store.get("a" * 32).is_empty  # each read pushes expiry out again


def test_the_oldest_session_is_evicted_when_over_capacity():
    store = SessionStore(ttl_seconds=60, max_sessions=2)
    store.save("a" * 32, _context("a"))
    store.save("b" * 32, _context("b"))
    store.save("c" * 32, _context("c"))  # evicts "a", the oldest

    assert store.get("a" * 32).is_empty
    assert not store.get("b" * 32).is_empty
    assert not store.get("c" * 32).is_empty


def test_updating_an_existing_session_never_evicts_another():
    store = SessionStore(ttl_seconds=60, max_sessions=2)
    store.save("a" * 32, _context("a"))
    store.save("b" * 32, _context("b"))
    store.save("a" * 32, _context("a again"))  # same key: an update, not growth

    assert not store.get("b" * 32).is_empty


def test_clear_forgets_a_session_and_is_idempotent():
    store = SessionStore(ttl_seconds=60)
    store.save("a" * 32, _context())

    store.clear("a" * 32)
    store.clear("a" * 32)  # clearing again must not raise
    store.clear("z" * 32)  # nor must clearing one that never existed

    assert store.get("a" * 32).is_empty


def test_max_turns_reads_the_environment_override(monkeypatch):
    monkeypatch.setenv("SHOPENSEMBLE_SESSION_MAX_TURNS", "3")

    assert SessionStore(ttl_seconds=60).max_turns == 3


def test_ttl_reads_the_environment_override(monkeypatch):
    monkeypatch.setenv("SHOPENSEMBLE_SESSION_TTL_SECONDS", "0.05")
    store = SessionStore()
    store.save("a" * 32, _context())
    time.sleep(0.1)

    assert store.get("a" * 32).is_empty
