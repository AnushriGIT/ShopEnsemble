"""Tests for the review-summarization sub-agent.

Uses PydanticAI's built-in ``TestModel`` (no real OpenAI call, no
``OPENAI_API_KEY`` required) with ``custom_output_args`` to return a fixed
structured output, per the spec's Section 12 mocking policy.
"""

import pytest
from pydantic_ai.models.test import TestModel

from app.agents import review_agent as review_agent_module
from app.agents.data import CatalogData
from app.agents.models import (
    AgentErrorEnvelope,
    ReviewSummariesResponse,
    ReviewSummaryRequest,
    ReviewSummaryResponse,
)
from app.agents.review_agent import (
    MAX_REVIEW_PRODUCTS,
    build_review_agent,
    summarize_reviews,
    summarize_reviews_many,
)
from app.models import Product, Review


def _catalog() -> CatalogData:
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
    reviews = [
        Review(product_id="SP0001", rating=5.0, text="Loved it!", date="2025-01-01"),
        Review(product_id="SP0001", rating=4.0, text="Pretty good.", date="2025-01-02"),
    ]
    return CatalogData(products=[product], reviews=reviews, policies=[])


async def test_summarize_reviews_returns_the_agent_output_for_a_known_product():
    fake_output = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=2
    )
    agent = build_review_agent(model=TestModel(custom_output_args=fake_output))

    result = await summarize_reviews(agent, _catalog(), ReviewSummaryRequest(product_id="SP0001"))

    assert result == fake_output


async def test_summarize_reviews_handles_a_product_with_zero_reviews_without_calling_the_model():
    product = Product(
        id="SP0002",
        name="Widget Lite",
        brand="TechCo",
        category="speaker",
        price="29.99",
        description="A lighter speaker",
        stock=5,
        rating=4.0,
    )
    catalog = CatalogData(products=[product], reviews=[], policies=[])
    # A TestModel with no custom_output_args would fail schema validation if
    # actually invoked, so reaching a valid response here proves the
    # zero-reviews path short-circuits before any model call.
    agent = build_review_agent(model=TestModel())

    result = await summarize_reviews(agent, catalog, ReviewSummaryRequest(product_id="SP0002"))

    assert isinstance(result, ReviewSummaryResponse)
    assert result.review_count == 0
    assert result.sentiment == "neutral"


async def test_summarize_reviews_returns_an_error_envelope_for_an_unknown_product():
    agent = build_review_agent(model=TestModel())

    result = await summarize_reviews(agent, _catalog(), ReviewSummaryRequest(product_id="SP9999"))

    assert isinstance(result, AgentErrorEnvelope)
    assert result.error.code == "unknown_product_id"
    assert result.error.sub_agent == "review_summary_agent"


# --- Phase 5 spec B5: summaries for several products in one turn --------------

def _two_product_catalog() -> CatalogData:
    products = [
        Product(id="SP0001", name="Widget Pro", brand="TechCo", category="speaker",
                price="49.99", description="A fine speaker", stock=10, rating=4.5),
        Product(id="LP0002", name="Ultra Thin", brand="TechCo", category="laptop",
                price="372.50", description="A thin laptop", stock=3, rating=3.7),
    ]
    reviews = [
        Review(product_id="SP0001", rating=5.0, text="Loved it!", date="2025-01-01"),
        Review(product_id="LP0002", rating=4.0, text="Solid laptop.", date="2025-01-02"),
    ]
    return CatalogData(products=products, reviews=reviews, policies=[])


async def test_many_returns_one_summary_per_product_in_request_order_labelled_with_its_own_id():
    # The fake model returns product_id="SP0001" for EVERY call. Passing proves
    # summarize_reviews_many stamps each summary with the product it was asked
    # about (deterministic label) instead of trusting the model's echo.
    fixed = ReviewSummaryResponse(product_id="SP0001", summary="Fine.", sentiment="positive", review_count=1)
    agent = build_review_agent(model=TestModel(custom_output_args=fixed))

    result = await summarize_reviews_many(agent, _two_product_catalog(), ["LP0002", "SP0001"])

    assert isinstance(result, ReviewSummariesResponse)
    assert [summary.product_id for summary in result.summaries] == ["LP0002", "SP0001"]


async def test_many_with_one_unknown_id_fails_the_whole_request_naming_it(monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}

    async def counting_summarize(agent, catalog, request):
        calls["count"] += 1

    monkeypatch.setattr(review_agent_module, "summarize_reviews", counting_summarize)
    agent = build_review_agent(model=TestModel())

    result = await summarize_reviews_many(agent, _two_product_catalog(), ["SP0001", "ZZ9999"])

    assert isinstance(result, AgentErrorEnvelope)
    assert result.error.code == "unknown_product_id"
    assert "ZZ9999" in result.error.message
    assert calls["count"] == 0  # all-or-nothing: no summary work starts if any ID is bad


async def test_many_over_the_cap_is_rejected_before_any_model_call(monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}

    async def counting_summarize(agent, catalog, request):
        calls["count"] += 1

    monkeypatch.setattr(review_agent_module, "summarize_reviews", counting_summarize)
    agent = build_review_agent(model=TestModel())
    too_many = [f"SP{n:04d}" for n in range(1, MAX_REVIEW_PRODUCTS + 2)]

    result = await summarize_reviews_many(agent, _two_product_catalog(), too_many)

    assert isinstance(result, AgentErrorEnvelope)
    assert result.error.code == "too_many_products"
    assert calls["count"] == 0  # the cap is what bounds LLM spend per request


async def test_many_with_repeated_ids_collapses_to_the_single_product_response():
    # ["SP0001", "SP0001"] is really one product — must not be wrapped in a
    # ReviewSummariesResponse (whose contract is 2+ summaries).
    fixed = ReviewSummaryResponse(product_id="SP0001", summary="Fine.", sentiment="positive", review_count=1)
    agent = build_review_agent(model=TestModel(custom_output_args=fixed))

    result = await summarize_reviews_many(agent, _two_product_catalog(), ["SP0001", "SP0001"])

    assert isinstance(result, ReviewSummaryResponse)
    assert result.product_id == "SP0001"


async def test_many_propagates_a_sub_agent_error_envelope(monkeypatch: pytest.MonkeyPatch):
    boom = AgentErrorEnvelope.model_validate(
        {"error": {"code": "llm_failure", "message": "model down", "sub_agent": "review_summary_agent"}}
    )

    async def failing_summarize(agent, catalog, request):
        return boom

    monkeypatch.setattr(review_agent_module, "summarize_reviews", failing_summarize)
    agent = build_review_agent(model=TestModel())

    result = await summarize_reviews_many(agent, _two_product_catalog(), ["SP0001", "LP0002"])

    assert result == boom
