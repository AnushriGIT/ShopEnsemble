"""Fixtures for the FastAPI contract-test suite (Phase 3b implementation plan).

Uses ``TestClient`` + PydanticAI's ``TestModel`` (never the real OpenAI API,
same mocking policy as ``tests/agents/``) via FastAPI's own
``app.dependency_overrides`` mechanism — the FastAPI-idiomatic equivalent of
this project's existing ``monkeypatch``/fake-agent convention.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app.agents.comparison_agent import build_comparison_agent
from app.agents.coordinator import SubAgents, build_coordinator_agent
from app.agents.data import CatalogData
from app.agents.models import RoutingDecision
from app.agents.policy_faq_agent import build_policy_faq_agent
from app.agents.recommendation_agent import build_recommendation_agent
from app.agents.review_agent import build_review_agent
from app.api.cache import TTLCache, get_query_cache
from app.api.dependencies import AppState, get_app_state
from app.api.main import app
from app.api.rate_limit import check_rate_limit
from app.api.session_store import SessionStore, get_session_store
from app.models import Product, Review


@pytest.fixture
def fake_catalog() -> CatalogData:
    product = Product(
        id="SP0001",
        name="Widget Pro",
        brand="TechCo",
        category="speaker",
        price="49.99",
        description="A fine speaker",
        stock=10,
        rating=4.5,
    )
    reviews = [Review(product_id="SP0001", rating=5.0, text="Loved it!", date="2025-01-01")]
    return CatalogData(products=[product], reviews=reviews, policies=[])


@pytest.fixture
def session_store() -> SessionStore:
    """A fresh, isolated session store per test (the module-level singleton
    would otherwise leak conversations between tests — same reasoning as the
    per-test ``TTLCache`` override below)."""

    return SessionStore()


@pytest.fixture
def two_product_catalog() -> CatalogData:
    """A catalog with two products and a review each — enough for a comparison
    followed by "review both" (Phase 5's motivating conversation)."""

    def _product(pid: str, name: str, category: str, price: str) -> Product:
        return Product(id=pid, name=name, brand="TechCo", category=category,
                       price=price, description="d", stock=1, rating=4.0)

    return CatalogData(
        products=[_product("SP0001", "Mobile Z", "smartphone", "588.48"),
                  _product("LP0002", "Ultra Thin", "laptop", "372.50")],
        reviews=[Review(product_id="SP0001", rating=5.0, text="Great", date="2025-01-01"),
                 Review(product_id="LP0002", rating=4.0, text="Good", date="2025-01-02")],
        policies=[],
    )


@pytest.fixture
def routing_decision() -> RoutingDecision:
    """Default fixed decision: dispatch to review_summary_agent for SP0001.

    Individual tests override ``app_state`` (below) when a different
    decision or dispatch outcome is needed.
    """

    return RoutingDecision(chosen_tool="review_summary_agent", confidence=0.9, extracted_product_id="SP0001")


@pytest.fixture
def app_state_factory(fake_catalog: CatalogData):
    """Returns a function building an ``AppState`` with a chosen fixed
    ``RoutingDecision`` — every sub-agent still runs on a bare ``TestModel``
    unless a test needs one to return something specific."""

    def _build(decision: RoutingDecision, **sub_agent_models) -> AppState:
        return AppState(
            catalog=fake_catalog,
            coordinator_agent=build_coordinator_agent(model=TestModel(custom_output_args=decision)),
            sub_agents=SubAgents(
                review=build_review_agent(model=sub_agent_models.get("review", TestModel())),
                recommendation=build_recommendation_agent(model=sub_agent_models.get("recommendation", TestModel())),
                comparison=build_comparison_agent(model=sub_agent_models.get("comparison", TestModel())),
                policy_faq=build_policy_faq_agent(model=sub_agent_models.get("policy_faq", TestModel())),
            ),
        )

    return _build


@pytest.fixture
def client(app_state_factory, routing_decision: RoutingDecision, session_store: SessionStore) -> Iterator[TestClient]:
    """The default client for tests that aren't specifically about caching
    or rate limiting: a fresh ``TTLCache`` per test (Phase 4b's module-level
    cache singleton would otherwise leak state between tests sharing a query
    string) and rate limiting overridden to a no-op (so an unrelated test
    can never fail because a *different* test already used up the limit in
    the same process). ``tests/api/test_cache.py``/``test_rate_limit.py``
    build their own ``TestClient`` instead, deliberately *not* applying
    these two overrides, to exercise the real behavior."""

    app.dependency_overrides[get_app_state] = lambda: app_state_factory(routing_decision)
    app.dependency_overrides[get_query_cache] = lambda: TTLCache()
    app.dependency_overrides[check_rate_limit] = lambda: None
    app.dependency_overrides[get_session_store] = lambda: session_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
