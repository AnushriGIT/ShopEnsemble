"""Contract tests for coordinator/sub-agent I/O models."""

import pytest
from pydantic import ValidationError

from app.agents.models import (
    AgentError,
    AgentErrorEnvelope,
    ComparisonRequest,
    ComparisonResponse,
    PolicyRequest,
    PolicyResponse,
    RecommendationRequest,
    RecommendationResponse,
    ReviewSummaryRequest,
    ReviewSummaryResponse,
    RoutingDecision,
)
from app.agents.sanitize import MAX_QUERY_LENGTH


def test_review_summary_request_accepts_a_valid_product_id():
    request = ReviewSummaryRequest(product_id="SP0001")
    assert request.product_id == "SP0001"


def test_review_summary_request_rejects_a_malformed_product_id():
    with pytest.raises(ValidationError):
        ReviewSummaryRequest(product_id="not-a-product-id")


def test_review_summary_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ReviewSummaryRequest(product_id="SP0001", extra_field="nope")


def test_review_summary_response_accepts_a_valid_payload():
    response = ReviewSummaryResponse(
        product_id="SP0001", summary="Customers like it.", sentiment="positive", review_count=3
    )
    assert response.review_count == 3


def test_review_summary_response_rejects_an_invalid_sentiment():
    with pytest.raises(ValidationError):
        ReviewSummaryResponse(
            product_id="SP0001", summary="...", sentiment="ecstatic", review_count=1
        )


def test_review_summary_response_rejects_a_negative_review_count():
    with pytest.raises(ValidationError):
        ReviewSummaryResponse(product_id="SP0001", summary="...", sentiment="neutral", review_count=-1)


def test_routing_decision_accepts_a_valid_payload():
    decision = RoutingDecision(
        chosen_tool="review_summary_agent",
        confidence=0.9,
        clarification_question=None,
        extracted_product_id="SP0001",
    )
    assert decision.confidence == 0.9


def test_routing_decision_rejects_an_unregistered_tool_name():
    with pytest.raises(ValidationError):
        RoutingDecision(chosen_tool="not_a_real_agent", confidence=0.9)


def test_routing_decision_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        RoutingDecision(chosen_tool="none", confidence=1.5)


def test_routing_decision_defaults_are_none_when_omitted():
    decision = RoutingDecision(chosen_tool="none", confidence=0.1)
    assert decision.clarification_question is None
    assert decision.extracted_product_id is None
    assert decision.extracted_product_ids is None
    assert decision.extracted_max_price is None
    assert decision.extracted_category is None
    assert decision.extracted_policy_type is None


def test_routing_decision_accepts_every_new_tool_name():
    for tool in ("recommendation_agent", "comparison_agent", "policy_faq_agent"):
        RoutingDecision(chosen_tool=tool, confidence=0.8)


def test_routing_decision_accepts_extracted_product_ids_list():
    decision = RoutingDecision(
        chosen_tool="comparison_agent", confidence=0.9, extracted_product_ids=["SP0001", "SP0002"]
    )
    assert decision.extracted_product_ids == ["SP0001", "SP0002"]


def test_recommendation_request_accepts_optional_filters():
    request = RecommendationRequest(query="a laptop", max_price="800", category="laptop")
    assert request.max_price == 800


def test_recommendation_request_rejects_a_non_positive_max_price():
    with pytest.raises(ValidationError):
        RecommendationRequest(query="a laptop", max_price="0")


def test_recommendation_request_rejects_a_query_over_the_max_length():
    """review-fix-loop finding (2026-09-16): query had no upper bound at all."""
    with pytest.raises(ValidationError):
        RecommendationRequest(query="a" * (MAX_QUERY_LENGTH + 1))


def test_recommendation_response_accepts_an_empty_product_list():
    response = RecommendationResponse(products=[], rationale="Nothing matched.")
    assert response.products == []


def test_comparison_request_rejects_a_malformed_product_id():
    with pytest.raises(ValidationError):
        ComparisonRequest(product_ids=["SP0001", "not-a-product-id"])


def test_comparison_response_accepts_a_valid_payload():
    response = ComparisonResponse(products=[], differences=["a", "b"])
    assert response.differences == ["a", "b"]


def test_policy_request_rejects_an_unknown_policy_type():
    with pytest.raises(ValidationError):
        PolicyRequest(policy_type="not_a_real_policy_type", question="what's your policy?")


def test_policy_request_rejects_a_question_over_the_max_length():
    """review-fix-loop finding (2026-09-16): question had no upper bound at all."""
    with pytest.raises(ValidationError):
        PolicyRequest(question="a" * (MAX_QUERY_LENGTH + 1))


def test_policy_response_accepts_a_null_policy():
    response = PolicyResponse(policy=None, answer="I'm not sure — please contact support.")
    assert response.policy is None


def test_agent_error_envelope_round_trips_to_the_spec_shape():
    envelope = AgentErrorEnvelope(
        error=AgentError(code="unknown_product_id", message="No such product.", sub_agent="review_summary_agent")
    )
    assert envelope.model_dump() == {
        "error": {
            "code": "unknown_product_id",
            "message": "No such product.",
            "sub_agent": "review_summary_agent",
        }
    }


def test_agent_error_rejects_an_empty_code():
    with pytest.raises(ValidationError):
        AgentError(code="", message="No such product.")


# --- Phase 6: RoutingDecision.extracted_max_price tolerates a blank string ----
# Found by real-API testing (2026-09-26): the model sometimes returns "" for an
# unused optional field instead of omitting it, which raised an unhandled
# pydantic_core.ValidationError (decimal_parsing) all the way to a raw 500 —
# the coordinator prompt already says "leave unused extracted_* fields empty",
# the schema just couldn't parse that literal instruction for a Decimal field.



def test_routing_decision_treats_a_blank_extracted_max_price_as_none():
    decision = RoutingDecision.model_validate(
        {"chosen_tool": "recommendation_agent", "confidence": 0.9, "extracted_max_price": ""}
    )

    assert decision.extracted_max_price is None


def test_routing_decision_treats_whitespace_extracted_max_price_as_none():
    decision = RoutingDecision.model_validate(
        {"chosen_tool": "recommendation_agent", "confidence": 0.9, "extracted_max_price": "   "}
    )

    assert decision.extracted_max_price is None


def test_routing_decision_still_rejects_a_genuinely_invalid_max_price():
    with pytest.raises(ValidationError):
        RoutingDecision.model_validate(
            {"chosen_tool": "recommendation_agent", "confidence": 0.9, "extracted_max_price": "not-a-number"}
        )
