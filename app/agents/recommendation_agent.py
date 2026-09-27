"""Product-recommendation sub-agent (spec Section 3, Phase 2 sub-agent)."""

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.settings import ModelSettings

from app.agents.data import CatalogData, filter_products
from app.agents.models import (
    PRODUCT_ID_CITATION_RULE,
    RecommendationRequest,
    RecommendationResponse,
)
from app.agents.retry import LLM_CALL_TIMEOUT_SECONDS, call_with_retry
from app.models import Product, ProductId, ShopEnsembleModel

RECOMMENDATION_SYSTEM_PROMPT = (
    "You recommend products from a pre-filtered candidate list. Given the "
    "customer's request and a list of candidate products (with product ID, "
    "name, brand, category, price, rating, and description), pick the "
    "product IDs that best match the request and write a short rationale "
    "(2-4 sentences) explaining the picks. Only pick IDs from the candidate "
    "list — never invent one. If no candidate fits well, return an empty "
    "list of IDs and explain why in the rationale. Never state a specific "
    "price, price range, or price threshold (e.g. 'from $X to $Y', 'all "
    "under $X') as applying to every one of several picked products in the "
    "rationale — verifying a numeric claim holds for every item in a "
    "multi-item pick is easy to get wrong, so describe pricing only in "
    "qualitative, relative terms instead (e.g. 'among the more affordable "
    "options', 'budget-friendly compared to the other candidates'). Only "
    "name products you actually picked — never name a candidate you did not "
    "pick."
    + PRODUCT_ID_CITATION_RULE
)


# Phase 6 (found via a real-API eval failure): session memory only tracks the
# MAX_PRODUCTS_IN_FOCUS most recent products (app.agents.conversation), so a
# recommendation that returns more than that could show a product a later
# "which one is cheapest?"/"reviews of them" query would never see. Keep this
# equal to MAX_PRODUCTS_IN_FOCUS so what's shown always fits what's remembered.
MAX_RECOMMENDATIONS = 10


class RecommendationPick(ShopEnsembleModel):
    """Internal LLM output: which candidates to recommend, not the full records.

    The agent only ever sees candidates already filtered by Python
    (``filter_products``), and only ever returns which of those IDs it
    picked — never full ``Product`` objects. Reconstructing full records
    (price, stock, etc.) from the model's own output would risk it
    fabricating fields it was never even shown (``stock`` isn't in the
    prompt at all); looking the picked IDs back up against the *already
    ground-truth* candidate list guarantees the returned data is real.
    """

    product_ids: list[ProductId]
    rationale: str = Field(min_length=1, max_length=1000)


def build_recommendation_agent(
    model: Model | KnownModelName | str = "openai:gpt-4o-mini",
) -> Agent[None, RecommendationPick]:
    return Agent(
        model,
        output_type=RecommendationPick,
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        model_settings=ModelSettings(timeout=LLM_CALL_TIMEOUT_SECONDS),
    )


def _build_prompt(request: RecommendationRequest, candidates: list[Product]) -> str:
    lines = [f'Customer request: "{request.query}"']
    if request.max_price is not None:
        lines.append(f"Max price: {request.max_price}")
    if request.category is not None:
        lines.append(f"Category filter: {request.category}")
    lines.append(f"Candidate products ({len(candidates)}):")
    for product in candidates:
        lines.append(
            f"- {product.id}: {product.name} ({product.brand}, {product.category}) "
            f"${product.price}, rating {product.rating}/5 - {product.description}"
        )
    return "\n".join(lines)


async def recommend_products(
    agent: Agent[None, RecommendationPick],
    catalog: CatalogData,
    request: RecommendationRequest,
) -> RecommendationResponse:
    """Recommend products matching ``request`` (a fresh catalog search).

    An empty candidate list after filtering is a valid, non-error result —
    same "empty is valid" precedent as ``review_agent``'s zero-reviews case.
    """

    candidates = filter_products(catalog, max_price=request.max_price, category=request.category)
    return await _recommend_from_candidates(agent, candidates, request)


async def recommend_among_shown(
    agent: Agent[None, RecommendationPick],
    candidates: list[Product],
    query_text: str,
) -> RecommendationResponse:
    """Judge/pick among products already shown in the conversation (Phase 6
    spec B3) — e.g. "which one is best?" after a recommendation or comparison.

    Deliberately NOT a fresh catalog search: ``candidates`` is exactly the set
    the customer was already shown (the coordinator resolves this from session
    memory), never re-filtered from the catalog. Shares every other rule with
    ``recommend_products`` (only ever picks from the given candidates, never
    invents one, cites "Name (ID)") via the same underlying helper — no
    separate agent/prompt to maintain.
    """

    request = RecommendationRequest(query=query_text)  # no max_price/category — not a new filter
    return await _recommend_from_candidates(agent, candidates, request)


async def _recommend_from_candidates(
    agent: Agent[None, RecommendationPick],
    candidates: list[Product],
    request: RecommendationRequest,
) -> RecommendationResponse:
    """Shared core of ``recommend_products``/``recommend_among_shown``: given a
    candidate list already decided by the caller, run the LLM pick and resolve
    it back to real catalog records.

    The result is capped at ``MAX_RECOMMENDATIONS`` (found via a real-API eval
    failure, Phase 6): session memory (``app.agents.conversation``) only tracks
    the ``MAX_PRODUCTS_IN_FOCUS`` most recent products, so a recommendation that
    returned more than that could show a product a later "which one is
    cheapest?"/"reviews of them" query would then silently never see. Capping
    what's shown to what memory can track keeps every later focus-scoped
    follow-up (Phase 6) answerable over the *same* set the customer saw, never
    a truncated subset of it.
    """

    if not candidates:
        return RecommendationResponse(
            products=[],
            rationale="No products matched your filters. Try a higher price limit or a different category.",
        )

    prompt = _build_prompt(request, candidates)
    result, _ = await call_with_retry(lambda: agent.run(prompt), label="recommendation_agent")
    pick = result.output

    candidates_by_id = {product.id: product for product in candidates}
    selected = [candidates_by_id[pid] for pid in pick.product_ids if pid in candidates_by_id][:MAX_RECOMMENDATIONS]
    return RecommendationResponse(products=selected, rationale=pick.rationale)
