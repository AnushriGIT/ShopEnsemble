"""Golden Q&A regression set (Phase 3a implementation plan).

Full ``handle_query()`` end-to-end (classify + dispatch) for a handful of
unambiguous, representative queries — one named test per case, each
asserting on the specific response fields that matter rather than just
"some answer came back". These should reliably pass every time; a failure
here is a real regression, not expected LLM noise (unlike the aggregate
routing-accuracy test).

Two cases are explicit regressions for bugs found during Phase 2
implementation (see ``.agents/memory-bank/testGenerationLog.md`` v5):
category pluralization in recommendations, and policy matching by number
instead of free-text echo.

Each case also carries a **groundedness** assertion (Phase 3a Part 2
implementation plan) on its free-text field (``summary``/``rationale``/
``differences``/``answer``) — the structured fields above are already
hallucination-proof by construction (the reference-only output pattern), but
nothing else checks that the generated prose stays faithful to the real
source records the sub-agent was actually shown.
"""

from decimal import Decimal

import pytest

from app.agents.conversation import ConversationContext
from app.agents.coordinator import handle_query, handle_turn
from app.agents.data import filter_products, products_by_ids, reviews_for_product
from app.agents.models import (
    ComparisonResponse,
    FallbackResponse,
    PolicyResponse,
    RecommendationResponse,
    ReviewSummariesResponse,
    ReviewSummaryResponse,
)
from tests.agents.eval.golden_qa_cases import (
    COMPARE_PRODUCT_IDS,
    COMPARE_QUERY,
    POLICY_LAPTOP_RETURN_QUERY,
    POLICY_LAPTOP_RETURN_TIMEFRAME_DAYS,
    POLICY_TYPE_WARRANTY,
    POLICY_WARRANTY_QUERY,
    RECOMMEND_CATEGORY_QUERY,
    RECOMMEND_LAPTOP_MAX_PRICE_QUERY,
    RECOMMEND_SPEAKER_CATEGORY,
    REVIEW_PRODUCT_ID,
)
from tests.agents.eval.groundedness import judge_groundedness

pytestmark = pytest.mark.eval


def _facts_for_products(products, selected_ids: set[str] | None = None) -> str:
    """Render real catalog product records as judge-readable facts.

    Mirrors exactly what ``recommendation_agent._build_prompt`` shows the
    model (id/name/brand/category/price/rating/description), including the
    product ID — a groundedness check is only meaningful against the same
    facts the sub-agent actually saw; omitting a field (e.g. ``rating``, or
    the ``id`` a rationale is free to cite) would produce a false positive.

    ``selected_ids``, when given, marks which of ``products`` were actually
    picked — without it, a comparative claim in the rationale about "the
    selected/recommended products" is unverifiable to the judge, since it
    has no way to know which entries in a larger candidate list the
    rationale is even talking about.
    """

    lines = []
    for product in products:
        marker = " [SELECTED/RECOMMENDED]" if selected_ids and product.id in selected_ids else ""
        lines.append(
            f"{product.id}{marker}: {product.name} ({product.brand}, {product.category}) "
            f"${product.price}, rating {product.rating}/5 - {product.description}"
        )
    return "\n".join(lines)


async def test_review_summary_for_a_known_product(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    response = await handle_query(
        eval_coordinator_agent,
        eval_sub_agents,
        eval_catalog,
        f"What do people say about {REVIEW_PRODUCT_ID}?",
    )

    assert isinstance(response, ReviewSummaryResponse)
    assert response.product_id == REVIEW_PRODUCT_ID
    assert response.sentiment in {"positive", "neutral", "negative", "mixed"}
    assert response.review_count >= 0

    facts = "\n".join(
        f"[{review.rating}/5] {review.text}"
        for review in reviews_for_product(eval_catalog, REVIEW_PRODUCT_ID)
    )
    grade = await judge_groundedness(eval_groundedness_judge, facts, response.summary)
    assert grade.grounded, grade.explanation


async def test_recommendation_for_a_cheap_speaker_resolves_the_plural_category(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    """Known-bug regression: 'speakers' must resolve to the catalog's 'speaker'."""

    response = await handle_query(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, RECOMMEND_CATEGORY_QUERY
    )

    assert isinstance(response, RecommendationResponse)
    assert response.products, "expected at least one speaker recommendation"
    assert all(product.category == RECOMMEND_SPEAKER_CATEGORY for product in response.products)

    # Facts = the full candidate list the sub-agent was actually shown (not
    # just the picked subset), with the actual picks marked — its rationale
    # is entitled to make comparative claims ("the most affordable") against
    # every candidate it saw, but the judge can only verify those claims if
    # it also knows which entries are "the selected products" being described.
    candidates = filter_products(eval_catalog, category=RECOMMEND_SPEAKER_CATEGORY)
    selected_ids = {product.id for product in response.products}
    facts = _facts_for_products(candidates, selected_ids)
    grade = await judge_groundedness(eval_groundedness_judge, facts, response.rationale)
    assert grade.grounded, grade.explanation


async def test_recommendation_respects_a_max_price_filter(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    response = await handle_query(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, RECOMMEND_LAPTOP_MAX_PRICE_QUERY
    )

    assert isinstance(response, RecommendationResponse)
    assert response.products, "expected at least one laptop recommendation under $700"
    assert all(product.price <= 700 for product in response.products)

    # Same reasoning as the speaker case above: facts = the full filtered
    # candidate set with the actual picks marked, not just the picked subset.
    candidates = filter_products(eval_catalog, max_price=Decimal(700), category="laptop")
    selected_ids = {product.id for product in response.products}
    facts = _facts_for_products(candidates, selected_ids)
    grade = await judge_groundedness(eval_groundedness_judge, facts, response.rationale)
    assert grade.grounded, grade.explanation


async def test_comparison_of_two_known_products(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    response = await handle_query(eval_coordinator_agent, eval_sub_agents, eval_catalog, COMPARE_QUERY)

    assert isinstance(response, ComparisonResponse)
    assert {product.id for product in response.products} == set(COMPARE_PRODUCT_IDS)
    assert response.differences

    facts = "\n".join(
        f"{product.name} ({product.brand}, {product.category}): ${product.price}, "
        f"rating {product.rating}/5, stock {product.stock} — {product.description}"
        for product in products_by_ids(eval_catalog, COMPARE_PRODUCT_IDS)
    )
    grade = await judge_groundedness(eval_groundedness_judge, facts, "; ".join(response.differences))
    assert grade.grounded, grade.explanation


def _facts_for_policy(policy) -> str:
    """Render a real matched StorePolicy record as judge-readable facts."""

    conditions = "; ".join(policy.conditions)
    return f"{policy.description} (timeframe: {policy.timeframe} days) - conditions: {conditions}"


async def test_policy_faq_laptop_return_timeframe_matches_the_catalog(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    """Known-bug regression: the agent must resolve a real matched policy, not just answer generally."""

    response = await handle_query(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, POLICY_LAPTOP_RETURN_QUERY
    )

    assert isinstance(response, PolicyResponse)
    assert response.policy is not None, "expected a matched policy, not a general answer"
    assert response.policy.policy_type == "returns"
    assert response.policy.timeframe == POLICY_LAPTOP_RETURN_TIMEFRAME_DAYS

    grade = await judge_groundedness(
        eval_groundedness_judge, _facts_for_policy(response.policy), response.answer
    )
    assert grade.grounded, grade.explanation


async def test_policy_faq_warranty_question_answers_from_the_matching_policy(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    response = await handle_query(eval_coordinator_agent, eval_sub_agents, eval_catalog, POLICY_WARRANTY_QUERY)

    assert isinstance(response, PolicyResponse)
    assert response.answer
    if response.policy is not None:
        assert response.policy.policy_type == POLICY_TYPE_WARRANTY

        # Groundedness only makes sense against a specific matched policy — a
        # general answer (no policy matched) has no single source record to
        # check it against, per the groundedness spec's "no matched policy"
        # scenario.
        grade = await judge_groundedness(
            eval_groundedness_judge, _facts_for_policy(response.policy), response.answer
        )
        assert grade.grounded, grade.explanation


# --- Phase 5: session memory and product-ID citing (real API, real catalog) ----


def _names_cited_without_their_id(text: str, products) -> list[str]:
    """Product names that appear in ``text`` with none of that name's IDs also
    appearing in the same text — the Part A4 prompt rule ("write 'Name (ID)'")
    is checked here, not trusted.

    Grouped by NAME because the catalog reuses names across many products (e.g.
    several laptops are called "Pro Book"): "Pro Book (LP0031)" is correctly
    cited even though another picked "Pro Book" has a different ID that the
    text doesn't mention.
    """

    ids_by_name: dict[str, set[str]] = {}
    for product in products:
        ids_by_name.setdefault(product.name, set()).add(product.id)
    return [
        name
        for name, ids in ids_by_name.items()
        if name.lower() in text.lower() and not any(product_id in text for product_id in ids)
    ]


async def test_followup_review_of_both_products_uses_conversation_memory(
    eval_coordinator_agent, eval_sub_agents, eval_catalog, eval_groundedness_judge
):
    """The customer's own reported conversation, end to end against the real
    model: compare two products, then ask for "the review summary of both
    products" without naming them. Before Phase 5 this returned the generic
    fallback ("I'm not sure how to help with that")."""

    context = ConversationContext()

    first_query = "compare SP0001 with LP0002"
    first = await handle_turn(eval_coordinator_agent, eval_sub_agents, eval_catalog, first_query, context=context)
    assert isinstance(first.response, ComparisonResponse)
    context = context.with_turn(first_query, first.facts, eval_catalog)

    second = await handle_turn(
        eval_coordinator_agent,
        eval_sub_agents,
        eval_catalog,
        "Provide the review summary of both products",
        context=context,
    )

    assert isinstance(second.response, ReviewSummariesResponse), second.response
    assert [summary.product_id for summary in second.response.summaries] == ["SP0001", "LP0002"]
    for summary in second.response.summaries:
        facts = "\n".join(
            f"[{review.rating}/5] {review.text}" for review in reviews_for_product(eval_catalog, summary.product_id)
        )
        grade = await judge_groundedness(eval_groundedness_judge, facts, summary.summary)
        assert grade.grounded, f"{summary.product_id}: {grade.explanation}"


async def test_review_of_two_named_products_returns_two_summaries_not_a_comparison(
    eval_coordinator_agent, eval_sub_agents, eval_catalog
):
    """Regression for the live misrouting: with both IDs typed and NO session
    memory at all, the request used to be routed to the comparison agent."""

    response = await handle_query(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, "Provide the review summary of SP0001 and LP0002"
    )

    assert isinstance(response, ReviewSummariesResponse), response
    assert [summary.product_id for summary in response.summaries] == ["SP0001", "LP0002"]


async def test_comparison_text_cites_product_ids_next_to_product_names(
    eval_coordinator_agent, eval_sub_agents, eval_catalog
):
    response = await handle_query(eval_coordinator_agent, eval_sub_agents, eval_catalog, COMPARE_QUERY)

    assert isinstance(response, ComparisonResponse)
    for difference in response.differences:
        uncited = _names_cited_without_their_id(difference, response.products)
        assert not uncited, f"{difference!r} names {uncited} without their Product ID"


async def test_recommendation_rationale_cites_product_ids_next_to_product_names(
    eval_coordinator_agent, eval_sub_agents, eval_catalog
):
    response = await handle_query(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, RECOMMEND_LAPTOP_MAX_PRICE_QUERY
    )

    assert isinstance(response, RecommendationResponse)
    uncited = _names_cited_without_their_id(response.rationale, response.products)
    assert not uncited, f"rationale names {uncited} without their Product ID: {response.rationale!r}"


# --- Phase 6: focus-scoped follow-ups (real API, real catalog) ----------------


async def test_reviews_after_a_comparison_using_a_bare_group_reference(
    eval_coordinator_agent, eval_sub_agents, eval_catalog
):
    """The second reported conversation, end to end: compare two, then ask for
    "their reviews" with no IDs typed. Before Phase 6 this could pull in
    products from an earlier, larger recommendation instead of just the two
    just compared."""

    context = ConversationContext()
    first = await handle_turn(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, COMPARE_QUERY, context=context
    )
    assert isinstance(first.response, ComparisonResponse)
    context = context.with_turn(COMPARE_QUERY, first.facts, eval_catalog)

    second = await handle_turn(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, "and their reviews", context=context
    )

    assert isinstance(second.response, ReviewSummariesResponse), second.response
    assert [summary.product_id for summary in second.response.summaries] == list(COMPARE_PRODUCT_IDS)


async def test_which_one_is_the_cheapest_after_a_recommendation(
    eval_coordinator_agent, eval_sub_agents, eval_catalog
):
    """The first reported conversation: recommend several, then ask which is
    cheapest — must answer about only the shown products, computed exactly
    (no LLM judgment needed for a plain price comparison)."""

    context = ConversationContext()
    first = await handle_turn(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, RECOMMEND_LAPTOP_MAX_PRICE_QUERY, context=context
    )
    assert isinstance(first.response, RecommendationResponse)
    assert first.response.products, "expected at least one recommended laptop to test against"
    context = context.with_turn(RECOMMEND_LAPTOP_MAX_PRICE_QUERY, first.facts, eval_catalog)

    second = await handle_turn(
        eval_coordinator_agent, eval_sub_agents, eval_catalog, "which one is the cheapest?", context=context
    )

    assert isinstance(second.response, RecommendationResponse), second.response
    expected_cheapest = min(first.response.products, key=lambda product: product.price)
    assert [product.id for product in second.response.products] == [expected_cheapest.id]


# --- Phase 7: a plain greeting gets a warm, useful reply (no LLM call) --------


async def test_a_greeting_gets_a_warm_reply_and_no_coordinator_call(eval_coordinator_agent, eval_sub_agents, eval_catalog):
    """Deterministic — no real API call is actually made for this path (the
    short-circuit happens before the coordinator agent ever runs), but this
    still exercises the full real handle_query() stack end to end."""

    response = await handle_query(eval_coordinator_agent, eval_sub_agents, eval_catalog, "HI how are you you")

    assert isinstance(response, FallbackResponse)
    assert "ShopEnsemble" in response.message
    assert "find products" in response.message
