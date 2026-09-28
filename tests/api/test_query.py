"""Contract tests for POST /query.

Covers a valid dispatch, the two validation-error boundaries (empty query,
over-``MAX_QUERY_LENGTH`` query), and — the actual point of the global
exception handler added in this plan — that an unexpected internal error
never leaks its raw message to the caller.
"""

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app.agents.models import ReviewSummaryResponse, RoutingDecision
from app.agents.sanitize import MAX_QUERY_LENGTH
from app.api import routes as routes_module
from app.api.dependencies import get_app_state
from app.api.main import app


def test_query_dispatches_and_returns_the_coordinator_response(app_state_factory):
    decision = RoutingDecision(chosen_tool="review_summary_agent", confidence=0.9, extracted_product_id="SP0001")
    fake_response = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=1
    )
    app.dependency_overrides[get_app_state] = lambda: app_state_factory(
        decision, review=TestModel(custom_output_args=fake_response)
    )

    with TestClient(app) as client:
        response = client.post("/query", json={"query": "What do people say about SP0001?"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == fake_response.model_dump()


def test_query_rejects_an_empty_query(client: TestClient):
    response = client.post("/query", json={"query": ""})

    assert response.status_code == 422
    # Clear, safe field-level detail — never a raw internal exception (spec
    # Section 7's "clear validation errors without leaking internals").
    assert response.json()["detail"][0]["loc"] == ["body", "query"]


def test_query_rejects_a_query_over_the_max_length(client: TestClient):
    response = client.post("/query", json={"query": "a" * (MAX_QUERY_LENGTH + 1)})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "query"]


def test_query_never_leaks_a_raw_internal_exception_message(app_state_factory, routing_decision, monkeypatch):
    """code-review follow-through: the global exception handler is the
    actual fix for the info-disclosure risk Appendix A flagged against
    reusing app/agents/cli.py's raw-exception-print pattern here.

    Builds its own ``TestClient(app, raise_server_exceptions=False)`` rather
    than using the shared ``client`` fixture — that flag is constructor-only
    in this Starlette version (setting it post-construction has no effect,
    confirmed by running this test both ways). Every other test in this
    suite intentionally keeps the default (an unhandled route bug should
    surface as a test failure, not a silently-swallowed 500)."""

    async def fake_handle_turn(coordinator_agent, sub_agents, catalog, query, context=None):
        raise RuntimeError("some sensitive internal detail: connection string, stack frame, etc.")

    monkeypatch.setattr(routes_module, "handle_turn", fake_handle_turn)

    app.dependency_overrides[get_app_state] = lambda: app_state_factory(routing_decision)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/query", json={"query": "anything"})
    app.dependency_overrides.clear()

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred.", "sub_agent": None}
    }
    assert "sensitive internal detail" not in response.text


def test_query_serializes_the_multi_product_review_response(app_state_factory):
    # Phase 5 spec B5: ReviewSummariesResponse is the 8th member of the
    # CoordinatorResponse union — /query's response_model must serialize it.
    from app.agents.data import CatalogData
    from app.api.dependencies import AppState
    from app.models import Product, Review

    def _product(pid: str, name: str) -> Product:
        return Product(id=pid, name=name, brand="TechCo", category="speaker",
                       price="10.00", description="d", stock=1, rating=4.0)

    catalog = CatalogData(
        products=[_product("SP0001", "One"), _product("SP0002", "Two")],
        reviews=[
            Review(product_id="SP0001", rating=5.0, text="Great", date="2025-01-01"),
            Review(product_id="SP0002", rating=4.0, text="Good", date="2025-01-02"),
        ],
        policies=[],
    )
    decision = RoutingDecision(
        chosen_tool="review_summary_agent", confidence=0.9, extracted_product_ids=["SP0001", "SP0002"]
    )
    base = app_state_factory(decision)
    fixed = ReviewSummaryResponse(product_id="SP0001", summary="ok", sentiment="positive", review_count=1)
    from app.agents.review_agent import build_review_agent

    state = AppState(
        catalog=catalog,
        coordinator_agent=base.coordinator_agent,
        sub_agents=type(base.sub_agents)(
            review=build_review_agent(model=TestModel(custom_output_args=fixed)),
            recommendation=base.sub_agents.recommendation,
            comparison=base.sub_agents.comparison,
            policy_faq=base.sub_agents.policy_faq,
        ),
    )
    app.dependency_overrides[get_app_state] = lambda: state

    with TestClient(app) as client:
        response = client.post("/query", json={"query": "review summary of SP0001 and SP0002"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [summary["product_id"] for summary in body["summaries"]] == ["SP0001", "SP0002"]
