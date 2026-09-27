"""Tests for TTLCache (unit) and the /query cache-hit behavior (contract).

Uses time.monotonic-based expiry directly — the unit tests below construct
a TTLCache with a tiny TTL and sleep past it rather than monkeypatching
time, since the sleep needed is only milliseconds.
"""

import time

from fastapi.testclient import TestClient

from app.agents.conversation import TurnFacts
from app.agents.coordinator import TurnResult
from app.agents.models import ReviewSummaryResponse
from app.api import routes as routes_module
from app.api.cache import TTLCache, get_query_cache
from app.api.dependencies import get_app_state
from app.api.main import app
from app.api.rate_limit import check_rate_limit


def test_ttl_cache_returns_none_for_a_missing_key():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("missing") is None


def test_ttl_cache_returns_the_stored_value_before_expiry():
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_ttl_cache_expires_entries_after_the_ttl():
    cache = TTLCache(ttl_seconds=0.05)
    cache.set("k", "v")
    time.sleep(0.1)
    assert cache.get("k") is None


def test_ttl_cache_evicts_the_oldest_entry_once_over_max_size():
    cache = TTLCache(ttl_seconds=60, max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # should evict "a", the oldest

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_query_endpoint_serves_a_repeated_identical_query_from_the_cache(app_state_factory, routing_decision, monkeypatch):
    """A second, identical request must not call handle_turn again.

    Mocks ``handle_turn`` (the route's seam since Phase 5) directly (matching ``test_query.py``'s own
    convention) rather than letting the real dispatch run — the fixture's
    sub-agents use a bare, unconfigured ``TestModel`` that only produces
    schema-valid output when a dispatch function is mocked around it, same
    as every other test in this suite.
    """

    calls = {"count": 0}
    fake_response = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=2
    )

    async def fake_handle_turn(coordinator_agent, sub_agents, catalog, query, context=None):
        calls["count"] += 1
        return TurnResult(response=fake_response, facts=TurnFacts(tool="review_summary_agent"))

    monkeypatch.setattr(routes_module, "handle_turn", fake_handle_turn)

    app.dependency_overrides[get_app_state] = lambda: app_state_factory(routing_decision)
    shared_cache = TTLCache()
    app.dependency_overrides[get_query_cache] = lambda: shared_cache
    app.dependency_overrides[check_rate_limit] = lambda: None

    with TestClient(app) as client:
        first = client.post("/query", json={"query": "What do people say about SP0001?"})
        second = client.post("/query", json={"query": "What do people say about SP0001?"})

    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls["count"] == 1  # the second request was served from the cache


def test_query_endpoint_does_not_cache_across_different_queries(app_state_factory, routing_decision, monkeypatch):
    calls = {"count": 0}
    fake_response = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=2
    )

    async def fake_handle_turn(coordinator_agent, sub_agents, catalog, query, context=None):
        calls["count"] += 1
        return TurnResult(response=fake_response, facts=TurnFacts(tool="review_summary_agent"))

    monkeypatch.setattr(routes_module, "handle_turn", fake_handle_turn)

    app.dependency_overrides[get_app_state] = lambda: app_state_factory(routing_decision)
    shared_cache = TTLCache()
    app.dependency_overrides[get_query_cache] = lambda: shared_cache
    app.dependency_overrides[check_rate_limit] = lambda: None

    with TestClient(app) as client:
        client.post("/query", json={"query": "What do people say about SP0001?"})
        client.post("/query", json={"query": "What do people say about SP0002?"})

    app.dependency_overrides.clear()

    assert calls["count"] == 2
