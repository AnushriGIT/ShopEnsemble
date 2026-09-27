"""Routing-accuracy eval set (Phase 3a implementation plan, "Design" section).

Each case is a ``(query, expected_tool)`` pair. ``test_routing_accuracy.py``
runs the coordinator's classification call alone (not full dispatch) for
every case and asserts the aggregate pass rate, tolerant of the occasional
LLM misclassification rather than requiring every single case to pass.

Product IDs and categories are drawn from the real ``data/products.csv``
catalog (see ``app/agents/data.py``) so extraction-heavy cases have a real
ground truth to be judged against by inspection.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.agents.conversation import TurnFacts
from app.agents.models import ToolName

# (query, expected_tool)
ROUTING_CASES: list[tuple[str, ToolName]] = [
    # review_summary_agent — "what do people say / reviews" about one product
    ("What do people say about SP0001?", "review_summary_agent"),
    ("Summarize the reviews for LP0002.", "review_summary_agent"),
    ("Are customers happy with TV0003?", "review_summary_agent"),
    ("Give me a review summary for SPK0012.", "review_summary_agent"),
    ("What's the general sentiment on SP0004 from reviews?", "review_summary_agent"),
    ("How do reviewers feel about LP0007?", "review_summary_agent"),
    # Phase 5 regression: reviews of SEVERAL named products are a review
    # request, not a comparison (live misrouting seen 2026-09-26).
    ("Provide the review summary of SP0001 and LP0002.", "review_summary_agent"),
    ("What do people say about SP0004 and TV0003?", "review_summary_agent"),
    # recommendation_agent — "recommend / suggest / looking for" with filters
    ("Recommend a laptop under $800.", "recommendation_agent"),
    ("I'm looking for a cheap speaker.", "recommendation_agent"),
    ("Suggest a good smart TV.", "recommendation_agent"),
    ("What smartphone would you recommend under $600?", "recommendation_agent"),
    ("Can you recommend some laptops for under $1000?", "recommendation_agent"),
    ("I need a new speaker, any suggestions?", "recommendation_agent"),
    # comparison_agent — compare 2+ named product IDs
    ("Compare SP0001 and SP0004.", "comparison_agent"),
    ("What's the difference between LP0002 and LP0007?", "comparison_agent"),
    ("Compare TV0003, TV0005, and TV0009.", "comparison_agent"),
    ("How does SPK0012 compare to SPK0014?", "comparison_agent"),
    ("Compare LP0008 and LP0013 for me.", "comparison_agent"),
    ("SP0001 vs SP0024 — which is better?", "comparison_agent"),
    # policy_faq_agent — store-policy questions
    ("What's your return policy for laptops?", "policy_faq_agent"),
    ("How does financing work?", "policy_faq_agent"),
    ("Do you offer price matching?", "policy_faq_agent"),
    ("What's covered under the smartphone warranty?", "policy_faq_agent"),
    ("Can I exchange a product for a different model?", "policy_faq_agent"),
    ("How long is shipping and is it free?", "policy_faq_agent"),
    # none / out-of-scope — expected to land on "none" or the clarify band
    ("What's the weather like today?", "none"),
    ("Tell me a joke.", "none"),
    ("Cancel my order number 12345.", "none"),
    ("hi", "none"),
    ("Can you help me?", "none"),
]


@dataclass(frozen=True)
class MultiTurnCase:
    """One routing case that carries earlier conversation (Phase 5 spec, "Verification").

    ``history`` is the list of already-handled turns, each ``(customer message,
    TurnFacts)``; the test replays them through ``ConversationContext.with_turn``
    against the real catalog and then classifies ``query`` with that context
    rendered into the prompt — exactly what ``handle_turn`` does in production.
    Only the fields a case sets are checked, so each case asserts precisely the
    behavior it exists to protect.
    """

    description: str
    query: str
    expected_tool: ToolName
    history: list[tuple[str, TurnFacts]] = field(default_factory=list)
    expected_ids: frozenset[str] | None = None  # the exact set of product IDs the model must resolve to
    expected_category: str | None = None
    expected_max_price: Decimal | None = None
    expect_unresolved: bool = False  # True: must NOT confidently act (clarify band or "none")


_COMPARED = [("compare SP0001 with LP0002", TurnFacts(tool="comparison_agent", product_ids=["SP0001", "LP0002"]))]

# Catalog facts these cases rely on (data/products.csv): SP0001 "Mobile Z"
# smartphone $588.48; LP0002 "Ultra Thin" laptop $372.50 — so "the cheaper one"
# is LP0002 and "the second one" (in request order) is LP0002.
MULTI_TURN_ROUTING_CASES: list[MultiTurnCase] = [
    MultiTurnCase(
        description="the reported failure: 'both products' after a comparison",
        query="Provide the review summary of both products",
        history=_COMPARED,
        expected_tool="review_summary_agent",
        expected_ids=frozenset({"SP0001", "LP0002"}),
    ),
    MultiTurnCase(
        description="positional reference: 'the second one'",
        query="What do reviewers say about the second one?",
        history=_COMPARED,
        expected_tool="review_summary_agent",
        expected_ids=frozenset({"LP0002"}),
    ),
    MultiTurnCase(
        description="attribute reference: 'the cheaper one'",
        query="Give me the review summary of the cheaper one",
        history=_COMPARED,
        expected_tool="review_summary_agent",
        expected_ids=frozenset({"LP0002"}),
    ),
    MultiTurnCase(
        description="refinement inherits the earlier category",
        query="what about under $500?",
        history=[
            (
                "recommend a laptop under $800",
                TurnFacts(
                    tool="recommendation_agent",
                    product_ids=["LP0002"],
                    category="laptop",
                    max_price=Decimal(800),
                ),
            )
        ],
        expected_tool="recommendation_agent",
        expected_category="laptop",
        expected_max_price=Decimal(500),
    ),
    MultiTurnCase(
        description="a topic change is not overridden by stale product context",
        query="recommend a speaker under $50",
        history=_COMPARED,
        expected_tool="recommendation_agent",
        expected_category="speaker",
        expected_max_price=Decimal(50),
    ),
    MultiTurnCase(
        description="a policy question mid-conversation is not hijacked by product context",
        query="what's your return policy for laptops?",
        history=_COMPARED,
        expected_tool="policy_faq_agent",
    ),
    MultiTurnCase(
        description="the answer to a clarification completes the earlier request",
        query="SP0001 and LP0002",
        history=[
            (
                "compare them",
                TurnFacts(tool="clarification", clarification="Which products would you like to compare?"),
            )
        ],
        expected_tool="comparison_agent",
        expected_ids=frozenset({"SP0001", "LP0002"}),
    ),
    MultiTurnCase(
        description="an unresolvable reference in a brand-new session must ask, never guess",
        query="Provide the review summary of both products",
        history=[],
        expected_tool="review_summary_agent",
        expect_unresolved=True,
    ),
    # --- Phase 6: focus-scoped follow-ups -----------------------------------
    MultiTurnCase(
        description="a bare group reference routes to reviews, not comparison (the reported bug)",
        query="and their reviews",
        history=_COMPARED,
        expected_tool="review_summary_agent",
        # IDs aren't checked here: the Phase 6 deterministic override (tested
        # directly in tests/agents/test_coordinator.py, and end to end in
        # tests/agents/eval/test_golden_qa.py) resolves them AFTER
        # classification — this case only protects tool *selection*.
    ),
    MultiTurnCase(
        description="a superlative about shown products routes to evaluate_products_agent",
        query="which one is the cheapest",
        history=[
            (
                "recommend a laptop under $1000",
                TurnFacts(
                    tool="recommendation_agent",
                    product_ids=["SP0001", "LP0002"],
                    category="laptop",
                    max_price=Decimal(1000),
                ),
            )
        ],
        expected_tool="evaluate_products_agent",
    ),
    MultiTurnCase(
        description="'which one is best' with no prior products must ask, never search fresh",
        query="which one is best",
        history=[],
        expected_tool="evaluate_products_agent",
        expect_unresolved=True,
    ),
]
