"""Typed I/O contracts for the coordinator agent and its sub-agents.

Every model here extends :class:`app.models.ShopEnsembleModel` so agent
boundaries get the same strict configuration (``extra="forbid"``,
``str_strip_whitespace=True``) as the catalog domain models, per
``specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`` Section 6.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.agents.sanitize import MAX_QUERY_LENGTH
from app.models import PolicyType, Product, ProductId, ShopEnsembleModel, StorePolicy

Sentiment = Literal["positive", "neutral", "negative", "mixed"]

# Phase 5 spec, Part A4: one shared sentence appended to every prompt whose
# model-written text can name a product (coordinator clarification questions,
# recommendation rationale, comparison differences). Defined once so all three
# prompts carry the identical convention and the eval can assert on exactly one
# format. The Product ID is the key customers use for follow-up questions, so
# text that names a product must also carry its ID. Best-effort by nature (a
# prompt rule) — the deterministic guarantee is the UI card, and the eval
# checks this rule instead of trusting it. The "only the ID inside the
# parentheses" clause exists because the data lines the models read look like
# 'SP0001: Mobile Z (TechCo, smartphone) ...', so without it the model wrote
# 'Mobile Z (TechCo)' — brand in the parentheses, no ID (measured 2026-09-26:
# the comparison eval failed ~1 run in 4 before this clause).
PRODUCT_ID_CITATION_RULE = (
    " Whenever your text names a product, write it as 'Name (ID)' using the "
    "product's ID from the data given — e.g. 'Mobile Z (SP0001)' — and put "
    "nothing but the ID inside those parentheses (never the brand or a "
    "category); never refer to a product by name alone."
)

# The set of sub-agents the coordinator can currently dispatch to. Extend this
# (and RoutingDecision.chosen_tool below) as later phases register more sub-agents.
ToolName = Literal[
    "review_summary_agent",
    "recommendation_agent",
    "comparison_agent",
    "policy_faq_agent",
    "evaluate_products_agent",
    "none",
]


class ReviewSummaryRequest(ShopEnsembleModel):
    """Input to the review-summarization sub-agent."""

    product_id: ProductId


class ReviewSummaryResponse(ShopEnsembleModel):
    """Output of the review-summarization sub-agent."""

    product_id: ProductId
    summary: str = Field(min_length=1, max_length=1000)
    sentiment: Sentiment
    review_count: int = Field(ge=0)


class ReviewSummariesResponse(ShopEnsembleModel):
    """Output of a review request covering 2+ products (Phase 5 spec B5).

    A separate response shape (not a widened ``ReviewSummaryResponse``) so a
    single-product request keeps returning exactly what it always has. Its
    distinguishing key, ``summaries``, overlaps no other response shape's first
    key, so the UI dispatcher in ``app/ui/components.py`` stays unambiguous.
    ``min_length=2`` makes it impossible to wrap a single product in this shape.
    """

    summaries: list[ReviewSummaryResponse] = Field(min_length=2)


class RecommendationRequest(ShopEnsembleModel):
    """Input to the product-recommendation sub-agent."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    max_price: Decimal | None = Field(default=None, gt=0)
    category: str | None = None


class RecommendationResponse(ShopEnsembleModel):
    """Output of the product-recommendation sub-agent."""

    products: list[Product]
    rationale: str = Field(min_length=1, max_length=1000)


class ComparisonRequest(ShopEnsembleModel):
    """Input to the product-comparison sub-agent."""

    product_ids: list[ProductId]


class ComparisonResponse(ShopEnsembleModel):
    """Output of the product-comparison sub-agent."""

    products: list[Product]
    differences: list[str]


class PolicyRequest(ShopEnsembleModel):
    """Input to the policy/FAQ sub-agent."""

    policy_type: PolicyType | None = None
    question: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


class PolicyResponse(ShopEnsembleModel):
    """Output of the policy/FAQ sub-agent."""

    policy: StorePolicy | None = None
    answer: str = Field(min_length=1, max_length=1000)


class RoutingDecision(ShopEnsembleModel):
    """Structured output of the coordinator's own classification call.

    ``confidence`` is the model's self-reported certainty in its own
    structured output (spec Section 4) — not a separately computed metric.
    The ``extracted_*`` fields carry whatever argument the chosen tool needs,
    extracted in the same call that classifies intent, rather than a second
    round-trip (see the spec's Appendix A decision log). Only the field(s)
    relevant to ``chosen_tool`` are expected to be populated for any one
    query — the rest stay ``None``.
    """

    chosen_tool: ToolName
    confidence: float = Field(ge=0, le=1)
    clarification_question: str | None = None
    extracted_product_id: ProductId | None = None
    """Used by ``review_summary_agent``."""
    extracted_product_ids: list[ProductId] | None = None
    """Used by ``comparison_agent`` — needs at least 2 to proceed."""
    extracted_max_price: Decimal | None = Field(default=None, gt=0)
    """Optional filter for ``recommendation_agent``."""

    @field_validator("extracted_max_price", mode="before")
    @classmethod
    def _blank_price_is_none(cls, value: object) -> object:
        """Coerce a blank/whitespace string to ``None`` before Decimal parsing.

        Found via real-API testing (Phase 6): the model sometimes writes ``""``
        for an unused optional field instead of omitting it — matching the
        coordinator prompt's own "leave unused extracted_* fields empty"
        instruction literally, just not in a shape Decimal can parse. Without
        this, that valid intent raised an unhandled ``ValidationError`` all the
        way to a raw 500 (a real crash found and reproduced, not hypothetical).
        """

        if isinstance(value, str) and value.strip() == "":
            return None
        return value
    extracted_category: str | None = None
    """Optional filter for ``recommendation_agent``."""
    extracted_policy_type: PolicyType | None = None
    """Optional filter for ``policy_faq_agent``."""


class AgentError(ShopEnsembleModel):
    """The JSON error envelope returned on a schema/contract violation.

    Matches the shape specified in
    ``specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`` Section 6.
    """

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    sub_agent: str | None = None


class AgentErrorEnvelope(ShopEnsembleModel):
    """Wrapper matching the spec's literal ``{"error": {...}}`` shape."""

    error: AgentError


class ClarificationResponse(ShopEnsembleModel):
    """Returned when confidence falls in the clarify band (spec Section 4)."""

    question: str = Field(min_length=1)


class FallbackResponse(ShopEnsembleModel):
    """Returned when confidence falls below the clarify threshold."""

    message: str = Field(min_length=1)
