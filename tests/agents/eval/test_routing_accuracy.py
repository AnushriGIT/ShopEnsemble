"""Aggregate routing-accuracy eval (Phase 3a implementation plan).

Runs the coordinator's classification call (not full dispatch) for every
case in ``ROUTING_CASES`` against the real OpenAI API and asserts the
overall pass rate meets a threshold set with headroom below the observed
baseline (see the "Setting the actual accuracy threshold" design note and
spec Section 11).
"""

import pytest

from app.agents.conversation import ConversationContext
from app.agents.coordinator import handle_turn
from app.agents.models import ClarificationResponse, FallbackResponse
from tests.agents.eval.routing_cases import (
    MULTI_TURN_ROUTING_CASES,
    ROUTING_CASES,
    MultiTurnCase,
)

pytestmark = pytest.mark.eval

# Observed baseline on 2026-09-14: 27/29 correct (93.1%) — see spec Section 11
# and Appendix A for the run this threshold was set from. One further case
# raised UnexpectedModelBehavior (the model's structured output failed
# PydanticAI's own retry-validation loop) rather than returning a wrong
# chosen_tool — a real, occasional failure mode of a real LLM call, counted
# as a miss below rather than left to crash the whole aggregate test.
# Asserted with headroom below that baseline to tolerate normal run-to-run
# variance without going flaky, while still catching a real regression.
ROUTING_ACCURACY_THRESHOLD = 0.80


def _multi_turn_miss(case: MultiTurnCase, decision) -> str | None:
    """Return why ``decision`` fails ``case`` (None if it passes).

    Checks only what the case sets, so each case asserts exactly the behavior
    it exists to protect. (``expect_unresolved`` cases are not judged here — they
    are run end to end through ``handle_turn`` instead; see the test below.)
    """

    if decision.chosen_tool != case.expected_tool:
        return f"expected {case.expected_tool!r}, got {decision.chosen_tool!r}"

    if case.expected_ids is not None:
        resolved = set(decision.extracted_product_ids or [])
        if decision.extracted_product_id is not None:
            resolved.add(decision.extracted_product_id)
        if resolved != set(case.expected_ids):
            return f"expected product IDs {sorted(case.expected_ids)}, got {sorted(resolved)}"

    if case.expected_category is not None and decision.extracted_category != case.expected_category:
        return f"expected category {case.expected_category!r}, got {decision.extracted_category!r}"

    if case.expected_max_price is not None and decision.extracted_max_price != case.expected_max_price:
        return f"expected max_price {case.expected_max_price}, got {decision.extracted_max_price}"

    return None


async def test_routing_accuracy_meets_threshold(eval_coordinator_agent, eval_sub_agents, eval_catalog):
    agent = eval_coordinator_agent
    misses: list[str] = []

    for query, expected_tool in ROUTING_CASES:
        try:
            result = await agent.run(query)
        except Exception as error:  # noqa: BLE001 - a failed real-API call is itself a miss
            misses.append(f"{query!r}: expected {expected_tool!r}, agent.run raised {error!r}")
            continue

        actual_tool = result.output.chosen_tool
        if actual_tool != expected_tool:
            misses.append(f"{query!r}: expected {expected_tool!r}, got {actual_tool!r}")

    # Phase 5: multi-turn cases run through the SAME aggregate gate (not a
    # separate set) — the coordinator prompt now carries reference-resolution
    # rules, and this is what proves they didn't hurt single-turn routing.
    for case in MULTI_TURN_ROUTING_CASES:
        if case.expect_unresolved:
            # End to end, in a brand-new session (empty context): the raw model
            # was seen inventing IDs here, so the real behavior under test is the
            # prompt AND the deterministic ID guard together — the customer must
            # get a question back, never a guess (and never a sub-agent call).
            try:
                turn = await handle_turn(
                    agent, eval_sub_agents, eval_catalog, case.query, context=ConversationContext()
                )
            except Exception as error:  # noqa: BLE001 - a failed real-API call is itself a miss
                misses.append(f"[multi-turn: {case.description}] {case.query!r}: handle_turn raised {error!r}")
                continue
            if not isinstance(turn.response, ClarificationResponse | FallbackResponse):
                misses.append(
                    f"[multi-turn: {case.description}] {case.query!r}: expected a clarification/fallback, "
                    f"got {type(turn.response).__name__}"
                )
            continue

        context = ConversationContext()
        for message, facts in case.history:
            context = context.with_turn(message, facts, eval_catalog)
        prompt = context.render_for_prompt(case.query) if not context.is_empty else case.query
        try:
            result = await agent.run(prompt)
        except Exception as error:  # noqa: BLE001 - a failed real-API call is itself a miss
            misses.append(f"[multi-turn: {case.description}] {case.query!r}: agent.run raised {error!r}")
            continue
        reason = _multi_turn_miss(case, result.output)
        if reason is not None:
            misses.append(f"[multi-turn: {case.description}] {case.query!r}: {reason}")

    total = len(ROUTING_CASES) + len(MULTI_TURN_ROUTING_CASES)
    correct = total - len(misses)
    accuracy = correct / total
    # Printed (visible with `-rP`) so the observed number can be recorded in the
    # spec's Decision Log the way the 93.1% baseline was.
    print(f"routing_accuracy {accuracy:.1%} ({correct}/{total}); misses: {misses}")

    assert accuracy >= ROUTING_ACCURACY_THRESHOLD, (
        f"Routing accuracy {accuracy:.1%} ({correct}/{total}) fell below the "
        f"{ROUTING_ACCURACY_THRESHOLD:.0%} threshold. Misrouted queries:\n"
        + "\n".join(misses)
    )
