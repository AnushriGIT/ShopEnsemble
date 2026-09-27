"""Tests for the product-comparison sub-agent."""

from pydantic_ai.models.test import TestModel

from app.agents.comparison_agent import (
    ComparisonAnalysis,
    build_comparison_agent,
    compare_products,
)
from app.agents.data import CatalogData
from app.agents.models import AgentErrorEnvelope, ComparisonRequest, ComparisonResponse
from app.models import Product


def _catalog() -> CatalogData:
    products = [
        Product(
            id="SP0001", name="Widget Pro", brand="TechCo", category="speaker",
            price="49.99", description="A fine speaker", stock=10, rating=4.5,
        ),
        Product(
            id="SP0004", name="Widget Max", brand="TechCo", category="speaker",
            price="79.99", description="A louder speaker", stock=2, rating=4.0,
        ),
    ]
    return CatalogData(products=products, reviews=[], policies=[])


async def test_compare_products_returns_real_catalog_products_and_llm_differences():
    analysis = ComparisonAnalysis(differences=["SP0004 is louder", "SP0001 is cheaper"])
    agent = build_comparison_agent(model=TestModel(custom_output_args=analysis))
    request = ComparisonRequest(product_ids=["SP0001", "SP0004"])

    result = await compare_products(agent, _catalog(), request)

    assert isinstance(result, ComparisonResponse)
    assert {product.id for product in result.products} == {"SP0001", "SP0004"}
    assert result.differences == ["SP0004 is louder", "SP0001 is cheaper"]


async def test_compare_products_returns_an_error_envelope_for_an_unknown_id():
    agent = build_comparison_agent(model=TestModel())
    request = ComparisonRequest(product_ids=["SP0001", "SP9999"])

    result = await compare_products(agent, _catalog(), request)

    assert isinstance(result, AgentErrorEnvelope)
    assert result.error.code == "unknown_product_id"
    assert "SP9999" in result.error.message
    assert result.error.sub_agent == "comparison_agent"


async def test_compare_products_returns_an_error_envelope_for_fewer_than_2_ids():
    # A single valid ID resolves fine on the lookup side, but there's nothing
    # to compare it against.
    agent = build_comparison_agent(model=TestModel())
    request = ComparisonRequest(product_ids=["SP0001"])

    result = await compare_products(agent, _catalog(), request)

    assert isinstance(result, AgentErrorEnvelope)
    assert result.error.code == "insufficient_product_ids"


async def test_compare_products_returns_products_in_the_requested_order():
    # Phase 5 spec B5: screen order must equal request order, because with
    # session memory "the first one" is a valid follow-up reference. The
    # catalog lists SP0001 first, so a request for SP0004-then-SP0001 only
    # passes if results follow the *request*, not the catalog.
    agent = build_comparison_agent(model=TestModel(custom_output_args=ComparisonAnalysis(differences=["x"])))
    request = ComparisonRequest(product_ids=["SP0004", "SP0001"])

    result = await compare_products(agent, _catalog(), request)

    assert isinstance(result, ComparisonResponse)
    assert [product.id for product in result.products] == ["SP0004", "SP0001"]
