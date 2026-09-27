"""Review-summarization sub-agent (spec Section 3, Phase 1 sub-agent).

Phase 5 adds ``summarize_reviews_many`` so a customer can ask for reviews of
several products in one turn ("review summary of both") — the single-product
``summarize_reviews`` below is unchanged and is reused once per product.
"""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.settings import ModelSettings

from app.agents.data import CatalogData, product_exists, reviews_for_product
from app.agents.models import (
    AgentError,
    AgentErrorEnvelope,
    ReviewSummariesResponse,
    ReviewSummaryRequest,
    ReviewSummaryResponse,
)
from app.agents.retry import LLM_CALL_TIMEOUT_SECONDS, call_with_retry
from app.models import Review

REVIEW_SYSTEM_PROMPT = (
    "You summarize customer reviews for a single product. Given a list of "
    "star ratings and review texts, write a concise summary (2-4 sentences) "
    "of what customers say, and classify the overall sentiment as one of "
    "'positive', 'neutral', 'negative', or 'mixed'. Base your answer strictly "
    "on the reviews given — never invent a criticism, caveat, reservation, or "
    "'room for improvement' that no review actually states, even to sound "
    "more balanced or nuanced. Never infer a customer's dissatisfaction or "
    "reservation merely from one rating being numerically lower than "
    "another — only from what the review text itself explicitly says; a "
    "lower rating with no stated complaint is still positive. Classify "
    "'mixed' only when reviews genuinely disagree (some clearly positive, "
    "some clearly negative or critical); reviews that are all similarly "
    "favorable (e.g. every rating above 3/5, no stated complaint) are "
    "'positive', not 'mixed', even if there are only one or two of them."
)

# Cap the number of reviews sent to the model per call to keep prompts
# bounded — most-recent reviews are the most relevant for a "what do people
# say" summary.
MAX_REVIEWS_PER_SUMMARY = 50

# Phase 5 spec B5: cap on products per multi-product review request. One
# /query still counts once against the per-IP rate limit, so this cap — not the
# rate limiter — is what bounds LLM spend for a single request (N products =
# N model calls).
MAX_REVIEW_PRODUCTS = 5


def build_review_agent(
    model: Model | KnownModelName | str = "openai:gpt-4o-mini",
) -> Agent[None, ReviewSummaryResponse]:
    return Agent(
        model,
        output_type=ReviewSummaryResponse,
        system_prompt=REVIEW_SYSTEM_PROMPT,
        model_settings=ModelSettings(timeout=LLM_CALL_TIMEOUT_SECONDS),
    )


def _build_prompt(product_id: str, reviews: list[Review]) -> str:
    recent = sorted(reviews, key=lambda review: review.date, reverse=True)[:MAX_REVIEWS_PER_SUMMARY]
    lines = [f"Reviews for product {product_id} ({len(reviews)} total, showing {len(recent)}):"]
    for review in recent:
        lines.append(f"- [{review.rating}/5] {review.text}")
    return "\n".join(lines)


async def summarize_reviews(
    agent: Agent[None, ReviewSummaryResponse],
    catalog: CatalogData,
    request: ReviewSummaryRequest,
) -> ReviewSummaryResponse | AgentErrorEnvelope:
    """Summarize reviews for ``request.product_id``.

    An unknown product is a contract violation (error envelope, spec Section
    6). A known product with zero reviews is a valid, non-error result.
    """

    if not product_exists(catalog, request.product_id):
        return AgentErrorEnvelope(
            error=AgentError(
                code="unknown_product_id",
                message=f"No product with id {request.product_id!r} in the catalog.",
                sub_agent="review_summary_agent",
            )
        )

    reviews = reviews_for_product(catalog, request.product_id)
    if not reviews:
        return ReviewSummaryResponse(
            product_id=request.product_id,
            summary="No reviews yet for this product.",
            sentiment="neutral",
            review_count=0,
        )

    prompt = _build_prompt(request.product_id, reviews)
    result, _ = await call_with_retry(lambda: agent.run(prompt), label="review_summary_agent")
    return result.output


async def summarize_reviews_many(
    agent: Agent[None, ReviewSummaryResponse],
    catalog: CatalogData,
    product_ids: list[str],
) -> ReviewSummariesResponse | ReviewSummaryResponse | AgentErrorEnvelope:
    """Summarize reviews for several products in one turn (Phase 5 spec B5).

    Inputs: the review agent, the catalog, and the requested product IDs.
    Output: a ``ReviewSummariesResponse`` (2+ distinct products, in request
    order), the plain ``ReviewSummaryResponse`` if the IDs collapse to one
    distinct product, or an ``AgentErrorEnvelope``.

    Rules (mirroring ``compare_products``' all-or-nothing convention):
    - repeated IDs are collapsed, keeping first-seen order;
    - more than ``MAX_REVIEW_PRODUCTS`` distinct IDs -> ``too_many_products``,
      checked *before* any lookup or model call;
    - any unknown ID -> ``unknown_product_id`` naming all of them, and no
      summary work starts at all;
    - otherwise one summary per product runs concurrently through the existing
      single-product ``summarize_reviews`` (each keeps its own retry/timeout);
      any sub-result that is an error envelope fails the whole request.

    Each summary's ``product_id`` is overwritten with the ID it was requested
    for: the model fills that field in its structured output, and the UI heading
    (and the session memory that later resolves "the second one") must never
    depend on the model echoing it back correctly.
    """

    unique_ids = list(dict.fromkeys(product_ids))

    if not unique_ids:
        return AgentErrorEnvelope(
            error=AgentError(
                code="missing_argument",
                message="Could not determine which products to summarize reviews for.",
                sub_agent="review_summary_agent",
            )
        )

    if len(unique_ids) > MAX_REVIEW_PRODUCTS:
        return AgentErrorEnvelope(
            error=AgentError(
                code="too_many_products",
                message=f"Please ask about at most {MAX_REVIEW_PRODUCTS} products at a time.",
                sub_agent="review_summary_agent",
            )
        )

    missing = [product_id for product_id in unique_ids if not product_exists(catalog, product_id)]
    if missing:
        return AgentErrorEnvelope(
            error=AgentError(
                code="unknown_product_id",
                message=f"Unknown product id(s): {', '.join(sorted(missing))}.",
                sub_agent="review_summary_agent",
            )
        )

    if len(unique_ids) == 1:
        return await summarize_reviews(agent, catalog, ReviewSummaryRequest(product_id=unique_ids[0]))

    results = await asyncio.gather(
        *(summarize_reviews(agent, catalog, ReviewSummaryRequest(product_id=product_id)) for product_id in unique_ids)
    )

    for result in results:
        if isinstance(result, AgentErrorEnvelope):
            return result

    return ReviewSummariesResponse(
        summaries=[
            result.model_copy(update={"product_id": product_id})
            for product_id, result in zip(unique_ids, results, strict=True)
        ]
    )
