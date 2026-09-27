"""Tests for FixedWindowRateLimiter (unit) and the /query 429 behavior (contract).

Every contract test here deliberately overrides ``get_query_cache`` with a
fresh, per-test ``TTLCache`` instance shared across that test's own
requests (each of 2+ distinct queries within one test would otherwise
short-circuit on a cache hit before ever reaching the rate-limit check) but
does *not* override ``check_rate_limit`` — this file is the one place that
exercises the real dependency.
"""

from fastapi.testclient import TestClient

from app.agents.conversation import TurnFacts
from app.agents.coordinator import TurnResult
from app.agents.models import ReviewSummaryResponse
from app.api import routes as routes_module
from app.api.cache import TTLCache, get_query_cache
from app.api.dependencies import get_app_state
from app.api.main import app
from app.api.rate_limit import FixedWindowRateLimiter, check_rate_limit


def test_fixed_window_limiter_allows_up_to_the_limit():
    limiter = FixedWindowRateLimiter(requests_per_minute=3)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False


def test_fixed_window_limiter_tracks_each_key_independently():
    limiter = FixedWindowRateLimiter(requests_per_minute=1)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True  # a different client, own budget
    assert limiter.allow("client-a") is False


def test_query_endpoint_returns_429_once_the_limit_is_exceeded(app_state_factory, routing_decision, monkeypatch):
    import app.api.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "_limiter", FixedWindowRateLimiter(requests_per_minute=2))

    # Mocked directly (test_cache.py's rationale applies here too) — the
    # fixture's sub-agents use a bare, unconfigured TestModel that only
    # produces schema-valid output when dispatch itself is mocked around it.
    fake_response = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=2
    )

    async def fake_handle_turn(coordinator_agent, sub_agents, catalog, query, context=None):
        return TurnResult(response=fake_response, facts=TurnFacts(tool="review_summary_agent"))

    monkeypatch.setattr(routes_module, "handle_turn", fake_handle_turn)

    app.dependency_overrides[get_app_state] = lambda: app_state_factory(routing_decision)
    shared_cache = TTLCache()
    app.dependency_overrides[get_query_cache] = lambda: shared_cache

    with TestClient(app) as client:
        first = client.post("/query", json={"query": "one"})
        second = client.post("/query", json={"query": "two"})
        third = client.post("/query", json={"query": "three"})

    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json() == {
        "error": {"code": "rate_limited", "message": third.json()["error"]["message"], "sub_agent": None}
    }
    assert "Rate limit exceeded" in third.json()["error"]["message"]


def test_query_endpoint_health_is_never_rate_limited(monkeypatch):
    import app.api.rate_limit as rate_limit_module

    # A limiter that rejects everything — /health must still succeed since
    # check_rate_limit is only wired onto POST /query, not GET /health.
    monkeypatch.setattr(rate_limit_module, "_limiter", FixedWindowRateLimiter(requests_per_minute=0))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_check_rate_limit_raises_for_an_unknown_client_when_exhausted(monkeypatch):
    """Direct unit check of check_rate_limit() itself, not through HTTP —
    confirms the "unknown" fallback key (no request.client) still works."""
    import app.api.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "_limiter", FixedWindowRateLimiter(requests_per_minute=1))

    class _FakeRequest:
        client = None

    check_rate_limit(_FakeRequest())  # first call: allowed
    try:
        check_rate_limit(_FakeRequest())  # second call: exceeded
    except rate_limit_module.RateLimitExceeded as error:
        assert "unknown" in str(error)
    else:
        raise AssertionError("expected RateLimitExceeded")
