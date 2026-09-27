"""Policy/FAQ sub-agent (spec Section 3, Phase 2 sub-agent)."""

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.settings import ModelSettings

from app.agents.data import CatalogData, policies_by_type
from app.agents.models import PolicyRequest, PolicyResponse
from app.agents.retry import LLM_CALL_TIMEOUT_SECONDS, call_with_retry
from app.models import ShopEnsembleModel, StorePolicy

POLICY_SYSTEM_PROMPT = (
    "You answer store-policy questions using only the numbered policies "
    "given to you. Write a concise, direct answer (2-4 sentences) grounded "
    "only in the policy descriptions and conditions shown — never invent a "
    "policy detail not present in them. If exactly one numbered policy is "
    "clearly what the question is about, set matched_policy_number to its "
    "number; if several could apply or none clearly matches, leave "
    "matched_policy_number empty and answer generally from what's available."
)


class PolicyAnswer(ShopEnsembleModel):
    """Internal LLM output: an answer plus a reference to a shown policy.

    The model never reconstructs a full ``StorePolicy`` (its ``conditions``
    list, etc.) — it only returns the 1-based position of the matching
    policy in the numbered list it was shown, which Python then resolves to
    the real ground-truth record. A free-text echo of the description was
    tried first and found (via manual smoke testing) to be unreliable — the
    model tended to echo back the whole formatted candidate line rather than
    just the description — so an unambiguous numeric reference replaces it,
    matching the clean-key idiom (``product_id``) already used by
    ``recommendation_agent``/``comparison_agent``.
    """

    matched_policy_number: int | None = Field(default=None, ge=1)
    answer: str


def build_policy_faq_agent(
    model: Model | KnownModelName | str = "openai:gpt-4o-mini",
) -> Agent[None, PolicyAnswer]:
    return Agent(
        model,
        output_type=PolicyAnswer,
        system_prompt=POLICY_SYSTEM_PROMPT,
        model_settings=ModelSettings(timeout=LLM_CALL_TIMEOUT_SECONDS),
    )


def _build_prompt(request: PolicyRequest, candidates: list[StorePolicy]) -> str:
    lines = [f'Customer question: "{request.question}"']
    lines.append(f"Available policies ({len(candidates)}):")
    for number, policy in enumerate(candidates, start=1):
        conditions = "; ".join(policy.conditions)
        lines.append(
            f"{number}. [{policy.policy_type}] {policy.description} "
            f"(timeframe: {policy.timeframe} days) - conditions: {conditions}"
        )
    return "\n".join(lines)


async def answer_policy_question(
    agent: Agent[None, PolicyAnswer],
    catalog: CatalogData,
    request: PolicyRequest,
) -> PolicyResponse:
    """Answer a policy/FAQ question, grounded in the matching policies.

    No policies matching the (optional) ``policy_type`` filter is still a
    valid, non-error result — the LLM answers generally from an empty set
    rather than the coordinator treating it as a contract violation.
    """

    candidates = policies_by_type(catalog, request.policy_type)
    if not candidates:
        return PolicyResponse(
            policy=None,
            answer="I don't have a specific policy on file for that — please contact support for details.",
        )

    prompt = _build_prompt(request, candidates)
    result, _ = await call_with_retry(lambda: agent.run(prompt), label="policy_faq_agent")
    answer = result.output

    matched_policy = None
    number = answer.matched_policy_number
    if number is not None and 1 <= number <= len(candidates):
        matched_policy = candidates[number - 1]

    return PolicyResponse(policy=matched_policy, answer=answer.answer)
