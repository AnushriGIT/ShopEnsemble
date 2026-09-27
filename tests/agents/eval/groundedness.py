"""Groundedness LLM-as-judge (Phase 3a Part 2 implementation plan).

Every sub-agent's *structured* response fields are hallucination-proof by
construction (the reference-only output pattern — see
``specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`` Section 3).
Their *free-text* fields (``summary``, ``rationale``, ``differences``,
``answer``) are not — nothing checks that the generated prose stays faithful
to the real source records the sub-agent was shown. This module is a single
shared judge for that: same idiom as every other agent in ``app/agents/``
(``build_*_agent()`` returning an ``Agent[None, <output type>]``), but kept
here rather than in ``app/agents/`` because it's an evaluation tool — no
production dispatch path ever calls it.
"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.settings import ModelSettings

from app.agents.retry import call_with_retry
from app.models import ShopEnsembleModel

GROUNDEDNESS_SYSTEM_PROMPT = (
    "You are grading whether a STUDENT ANSWER is grounded in a set of FACTS. "
    "Here is the grade criteria to follow:\n"
    "(1) Ensure the STUDENT ANSWER is grounded in the FACTS.\n"
    "(2) Ensure the STUDENT ANSWER does not contain information outside the "
    "scope of the FACTS (no hallucinated claims the FACTS don't support).\n"
    "(3) Reasonable synthesis or summarization of the FACTS is fine — the "
    "answer does not need to quote them verbatim, only stay faithful to them.\n"
    "(4) A comparative or superlative claim (e.g. 'the most affordable', "
    "'the best rated') is grounded as long as the FACTS actually support "
    "that comparison (e.g. the cited items really are the cheapest/highest- "
    "rated among the FACTS shown) — do not mark it ungrounded merely for "
    "being confidently worded; only mark it ungrounded if the comparison "
    "the FACTS show contradicts it, or the FACTS don't contain enough other "
    "items to support a comparison at all.\n"
    "(5) A subjective, fuzzy qualitative descriptor (e.g. 'affordable', "
    "'budget-friendly', 'good value', 'high quality') is a matter of "
    "reasonable characterization, not a precise factual claim — grade it "
    "grounded whenever a person could reasonably describe the cited FACTS "
    "that way (e.g. calling a mid-low-priced item 'affordable' relative to "
    "much pricier items in the same FACTS is grounded even if cheaper items "
    "also exist). Only mark such a descriptor ungrounded if it is clearly "
    "wrong given the FACTS (e.g. calling the single most expensive item in "
    "the FACTS 'the cheapest', or a low-rated item 'highly rated'). Do not "
    "penalize an answer for not being maximally precise about *degree*.\n"
    "A grounded value of True means the student's answer meets all of the "
    "criteria; False means it does not. Explain your reasoning before giving "
    "your verdict."
)


class GroundednessGrade(ShopEnsembleModel):
    """Internal-only judge output — never part of any sub-agent's public contract."""

    explanation: str
    grounded: bool


def build_groundedness_judge(
    model: Model | KnownModelName | str = "openai:gpt-4o",
) -> Agent[None, GroundednessGrade]:
    """Build the judge.

    Deliberately a stronger, more careful model than the ``gpt-4o-mini``
    every sub-agent uses — the roles are asymmetric (a cheap model can
    generate a plausible rationale, but reliably *grading* a multi-item
    numeric/comparative claim needs more care), matching the reference
    RAG-evaluation notebook's own choice of a stronger grader model.
    ``temperature=0`` for consistent, low-variance grading — unlike a
    customer-facing rationale, a judge's verdict should not vary run to run
    for the same input.
    """

    return Agent(
        model,
        output_type=GroundednessGrade,
        system_prompt=GROUNDEDNESS_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0),
    )


async def judge_groundedness(
    agent: Agent[None, GroundednessGrade],
    facts: str,
    answer: str,
) -> GroundednessGrade:
    """Judge whether ``answer`` is faithful to ``facts`` — the real source records shown to a sub-agent."""

    prompt = f"FACTS:\n{facts}\n\nSTUDENT ANSWER:\n{answer}"
    result, _ = await call_with_retry(lambda: agent.run(prompt), label="groundedness_judge")
    return result.output
