"""Tests for the product-recommendation sub-agent."""

from decimal import Decimal

from pydantic_ai.models.test import TestModel

from app.agents.data import CatalogData
from app.agents.models import RecommendationRequest, RecommendationResponse
from app.agents.recommendation_agent import (
    RecommendationPick,
    build_recommendation_agent,
    recommend_products,
)
from app.models import Product


def _catalog() -> CatalogData:
    products = [
        Product(
            id="LP0001", name="Laptop Pro", brand="TechCo", category="laptop",
            price="799.99", description="A fast laptop", stock=3, rating=4.8,
        ),
        Product(
            id="LP0002", name="Laptop Air", brand="TechCo", category="laptop",
            price="1299.99", description="A light laptop", stock=5, rating=4.2,
        ),
    ]
    return CatalogData(products=products, reviews=[], policies=[])


async def test_recommend_products_resolves_picked_ids_to_real_catalog_data():
    """The LLM only ever picks IDs (RecommendationPick); the returned Product
    objects must come from the catalog, not be reconstructed by the model."""

    pick = RecommendationPick(product_ids=["LP0001"], rationale="Fits your budget.")
    agent = build_recommendation_agent(model=TestModel(custom_output_args=pick))
    request = RecommendationRequest(query="recommend a laptop under 800", max_price=Decimal(800))

    result = await recommend_products(agent, _catalog(), request)

    assert isinstance(result, RecommendationResponse)
    assert [product.id for product in result.products] == ["LP0001"]
    assert result.products[0].stock == 3  # real catalog data, not model-fabricated
    assert result.rationale == "Fits your budget."


async def test_recommend_products_ignores_a_picked_id_outside_the_filtered_candidates():
    """Defensive: even if the model hallucinates an ID not in what it was
    shown, the response never includes it (candidates_by_id lookup misses)."""

    pick = RecommendationPick(product_ids=["LP0001", "SP9999"], rationale="...")
    agent = build_recommendation_agent(model=TestModel(custom_output_args=pick))
    request = RecommendationRequest(query="recommend a laptop under 800", max_price=Decimal(800))

    result = await recommend_products(agent, _catalog(), request)

    assert [product.id for product in result.products] == ["LP0001"]


async def test_recommend_products_returns_empty_without_calling_the_model_when_no_candidates_match():
    # A bare TestModel() would fail schema validation if actually invoked,
    # so a valid empty result here proves the no-candidates path short-circuits.
    agent = build_recommendation_agent(model=TestModel())
    request = RecommendationRequest(query="recommend a laptop under 800", max_price=Decimal(10))

    result = await recommend_products(agent, _catalog(), request)

    assert result.products == []
    assert result.rationale


# --- Phase 6: recommend_among_shown() — judge/pick from an ALREADY-given ------
# candidate set (products the customer was just shown), not a fresh catalog
# search. Shares all its logic with recommend_products() via the same refactor.

from app.agents.recommendation_agent import recommend_among_shown


async def test_recommend_among_shown_picks_only_from_the_given_candidates():
    # Even if the model hallucinates an ID outside the given set, it's dropped —
    # exactly recommend_products()'s existing "only pick from candidates"
    # contract, now shared code, so this also proves the refactor is safe.
    pick = RecommendationPick(product_ids=["LP0001", "SP9999"], rationale="LP0001 is the standout.")
    agent = build_recommendation_agent(model=TestModel(custom_output_args=pick))

    result = await recommend_among_shown(agent, _catalog().products, "which one is best")

    assert isinstance(result, RecommendationResponse)
    assert [product.id for product in result.products] == ["LP0001"]
    assert result.rationale == "LP0001 is the standout."


async def test_recommend_among_shown_with_no_candidates_returns_empty_without_a_model_call():
    agent = build_recommendation_agent(model=TestModel())  # would fail schema validation if invoked

    result = await recommend_among_shown(agent, [], "which one is best")

    assert result.products == []


# --- Phase 6 (found via eval): recommendations are capped to match memory ----
# A "which is best/cheapest" superlative can only be computed correctly over
# what session memory actually kept (MAX_PRODUCTS_IN_FOCUS). If a recommendation
# could return more than that, a later superlative query would silently miss
# whichever ones got truncated out of memory — found by a real-API eval failure
# (the true cheapest of 17 recommended laptops wasn't among the 10 remembered).

from app.agents.recommendation_agent import MAX_RECOMMENDATIONS


async def test_recommend_products_is_capped_to_what_memory_can_track():
    many_products = [
        Product(id=f"LP{n:04d}", name=f"Laptop {n}", brand="TechCo", category="laptop",
                price=f"{500 + n}.00", description="d", stock=1, rating=4.0)
        for n in range(1, MAX_RECOMMENDATIONS + 6)
    ]
    catalog = CatalogData(products=many_products, reviews=[], policies=[])
    pick = RecommendationPick(product_ids=[p.id for p in many_products], rationale="All of them fit.")
    agent = build_recommendation_agent(model=TestModel(custom_output_args=pick))
    request = RecommendationRequest(query="recommend a laptop")

    result = await recommend_products(agent, catalog, request)

    assert len(result.products) == MAX_RECOMMENDATIONS
