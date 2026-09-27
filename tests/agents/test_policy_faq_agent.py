"""Tests for the policy/FAQ sub-agent."""

from pydantic_ai.models.test import TestModel

from app.agents.data import CatalogData
from app.agents.models import PolicyRequest, PolicyResponse
from app.agents.policy_faq_agent import PolicyAnswer, answer_policy_question, build_policy_faq_agent
from app.models import StorePolicy


def _catalog() -> CatalogData:
    policies = [
        StorePolicy(
            policy_type="returns",
            description="Speaker Return Policy",
            conditions=["No physical damage", "Original packaging"],
            timeframe=15,
        ),
        StorePolicy(
            policy_type="warranty",
            description="Laptop Warranty",
            conditions=["1 year manufacturer warranty"],
            timeframe=365,
        ),
    ]
    return CatalogData(products=[], reviews=[], policies=policies)


async def test_answer_policy_question_resolves_the_matched_policy_by_number():
    # policy_type="returns" filters _catalog()'s 2 policies down to 1
    # candidate, so "number 1" in the numbered prompt is that one policy.
    answer = PolicyAnswer(
        matched_policy_number=1,
        answer="You can return speakers within 15 days if undamaged and in original packaging.",
    )
    agent = build_policy_faq_agent(model=TestModel(custom_output_args=answer))
    request = PolicyRequest(policy_type="returns", question="what's your return policy?")

    result = await answer_policy_question(agent, _catalog(), request)

    assert isinstance(result, PolicyResponse)
    assert result.policy is not None
    assert result.policy.description == "Speaker Return Policy"
    assert result.policy.timeframe == 15  # real catalog data, not model-fabricated
    assert "15 days" in result.answer


async def test_answer_policy_question_leaves_policy_none_when_no_match_identified():
    answer = PolicyAnswer(matched_policy_number=None, answer="It depends on the product category.")
    agent = build_policy_faq_agent(model=TestModel(custom_output_args=answer))
    request = PolicyRequest(policy_type=None, question="what are your policies?")

    result = await answer_policy_question(agent, _catalog(), request)

    assert result.policy is None
    assert result.answer == "It depends on the product category."


async def test_answer_policy_question_ignores_an_out_of_range_policy_number():
    # Defensive: an out-of-range number (e.g. the model miscounting) resolves
    # to no match rather than raising an IndexError.
    answer = PolicyAnswer(matched_policy_number=99, answer="...")
    agent = build_policy_faq_agent(model=TestModel(custom_output_args=answer))
    request = PolicyRequest(policy_type=None, question="what are your policies?")

    result = await answer_policy_question(agent, _catalog(), request)

    assert result.policy is None


async def test_answer_policy_question_returns_a_default_answer_without_calling_the_model_when_no_policies_match():
    # A bare TestModel() would fail schema validation if actually invoked,
    # so a valid response here proves the no-candidates path short-circuits.
    agent = build_policy_faq_agent(model=TestModel())
    catalog = CatalogData(products=[], reviews=[], policies=[])
    request = PolicyRequest(policy_type="financing", question="do you offer financing?")

    result = await answer_policy_question(agent, catalog, request)

    assert result.policy is None
    assert result.answer
