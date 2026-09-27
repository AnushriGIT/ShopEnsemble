# Coordinator Agent — Phase 3a Part 2: Groundedness Evaluation Spec

**Status:** ✅ Implemented and verified (2026-09-14) — see the [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-part2-groundedness-implementation-plan.md)'s Implementation Notes for the real bugs found and fixed along the way.
**Governing spec:** [shopensemble-coordinator-agent-spec.md](shopensemble-coordinator-agent-spec.md) — Section 12 "Evaluation strategy" (the applicability analysis this spec is the output of) and Appendix A (the per-metric Decision Log rows).
**Extends:** The Phase 3a eval harness (`tests/agents/eval/`, see the [Phase 3a implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md)) — this is additional coverage on top of it, not a parallel harness.
**Test generation log:** `.agents/memory-bank/testGenerationLog.md` (will land as `v7` once implemented).

**Why a separate file, not folded into the one living spec**: `AGENTS.md` Rule 10 and this project's own `skills/SpecToolBox/4_COORDINATOR_AGENT_SPEC_TEMPLATE.md` are explicit that the domain's *spec* stays one file, updated in place — no `-v2`/`-phase2` forks. This file isn't a fork of that spec; it's a feature-scoped BDD spec (Rule 1: "formulate a technical BDD specification... before generating or modifying code") for the one new capability the Section 12 analysis identified, the same way `shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md` is its own file rather than a section wedged into the main spec. The main spec (`shopensemble-coordinator-agent-spec.md`) remains the single authoritative document — this file exists *because* Rule 1 requires a spec before code, and the main spec's Section 12 already points here rather than duplicating this content in place.

---

## Context / Narrative

The Phase 3a eval harness hard-asserts every *structured* response field against real catalog ground truth — `policy.timeframe == 14`, `{p.id for p in products} == {"SP0001", "SP0004"}`. That pattern is intentionally being kept, not replaced: wherever the exact correct value is known in advance from the CSV, a deterministic assertion is strictly stronger and cheaper than an LLM judge scoring the same field (see the governing spec's Section 12 analysis and Appendix A).

What that pattern doesn't reach is the **free-text fields** every sub-agent also returns:

- `ReviewSummaryResponse.summary` — prose synthesized from the actual review texts for a product
- `RecommendationResponse.rationale` — prose explaining why the picked products fit the request
- `ComparisonResponse.differences` — a list of prose statements about how two products differ
- `PolicyResponse.answer` — prose synthesized from the matched policy's actual description/conditions/timeframe

The reference-only output pattern (governing spec Section 3/Appendix A — the LLM only ever picks an ID or a numbered-list position, Python resolves the real record) already makes every *structured* field hallucination-proof by construction. It does nothing for these four prose fields — nothing today verifies that the generated text stays faithful to the real source records the sub-agent was actually shown. A summary could describe a rating trend no review supports; a policy answer could state a timeframe that doesn't match the matched policy's real `timeframe` value, even while the structured `policy` field returned alongside it is correct.

This is the one gap the Section 12 evaluation-strategy analysis (walking Correctness / Relevance / Groundedness / Retrieval relevance against this project's actual architecture) found to be both real and currently unaddressed — the other 3 metrics were evaluated and rejected as either redundant with what Phase 3a already does deterministically, or inapplicable to a non-RAG, structured-lookup architecture. See Appendix A of the governing spec for the full per-metric reasoning.

---

## Design

**One shared judge, not four.** A single reusable evaluator — same idiom as every other agent in `app/agents/`: a PydanticAI agent with a small structured output type, not a bespoke check per sub-agent.

```python
class GroundednessGrade(ShopEnsembleModel):
    explanation: str
    grounded: bool

async def judge_groundedness(facts: str, answer: str) -> GroundednessGrade: ...
```

`facts` is the real source text the sub-agent was actually shown for that case (not a re-derivation) — the same review texts `_build_prompt()` sent, the same candidate product fields, the same matched policy's description/conditions/timeframe. `answer` is the specific free-text field from the sub-agent's actual response for that case.

**Reuses the 6 existing golden Q&A cases — no parallel eval set.** Per the "implement this additionally" scoping, each of `test_golden_qa.py`'s 6 existing cases gains one *additional* assertion rather than a new case list living alongside it: the case already runs the real query and already has (or can trivially derive from `eval_catalog`) the real source records to check the free-text field against. No new coordinator calls — one extra judge call per existing test.

| Existing golden Q&A case | Free-text field checked | `facts` source |
| :--- | :--- | :--- |
| `test_review_summary_for_a_known_product` | `response.summary` | `reviews_for_product(eval_catalog, REVIEW_PRODUCT_ID)` — the actual review texts |
| `test_recommendation_for_a_cheap_speaker_resolves_the_plural_category` | `response.rationale` | The actual picked products' name/description/price |
| `test_recommendation_respects_a_max_price_filter` | `response.rationale` | The actual picked products' name/description/price |
| `test_comparison_of_two_known_products` | `response.differences` (joined) | The two actual products' full field values |
| `test_policy_faq_laptop_return_timeframe_matches_the_catalog` | `response.answer` | `response.policy`'s actual description/conditions/timeframe (already resolved by the test) |
| `test_policy_faq_warranty_question_answers_from_the_matching_policy` | `response.answer` | `response.policy`'s actual fields, when a policy was matched |

**Stays inside the existing `eval` marker — no new marker.** The judge itself calls the real API (an LLM-as-judge inherently needs no ground truth, but it is a real model call, same cost/latency category as the sub-agent calls already being made). It lives in `tests/agents/eval/`, not `app/agents/` — it's an evaluation tool, not a coordinator capability; no production dispatch path calls it.

---

## Scenarios (Gherkin)

```gherkin
Feature: Groundedness of sub-agent free-text output
  Every sub-agent response field that is LLM-synthesized prose (not a
  structural reference Python resolves from the catalog) must be judged
  faithful to the real source records the sub-agent was actually shown —
  no claim the records don't support.

  Scenario: Review summary stays grounded in the actual reviews
    Given a known product with real reviews in the catalog
    When the review-summarization sub-agent answers "What do people say about it?"
    Then the groundedness judge finds the summary grounded in those reviews' actual text

  Scenario: Recommendation rationale stays grounded in the picked products
    Given a recommendation query that resolves to real catalog products
    When the recommendation sub-agent answers
    Then the groundedness judge finds the rationale grounded in the picked products' actual name, description, and price

  Scenario: Comparison differences stay grounded in the two products' real data
    Given two known products
    When the comparison sub-agent compares them
    Then the groundedness judge finds the stated differences grounded in the two products' actual field values

  Scenario: Policy answer stays grounded in the matched policy
    Given a policy question that resolves to one specific matched policy
    When the policy/FAQ sub-agent answers
    Then the groundedness judge finds the answer grounded in that policy's actual description, conditions, and timeframe

  Scenario: A response with no matched policy is not checked against a policy that doesn't exist
    Given a policy question broad enough that no single policy is matched
    When the policy/FAQ sub-agent answers generally
    Then the groundedness check is skipped for that case, since there is no specific matched-policy record to be grounded in
```

---

## Files (for the eventual implementation plan — nothing is built by this spec)

```
tests/agents/eval/groundedness.py   # GroundednessGrade + judge_groundedness() (new)
tests/agents/eval/test_golden_qa.py # each of the 6 existing tests gains one groundedness assertion (modified)
```

No changes to `app/`, `pyproject.toml`, or the `eval` marker — this is additive within files the Phase 3a implementation plan already established.

---

## Verification (once implemented)

```bash
# Still opt-in, still real-API, still excluded from the default run
.venv/bin/python -m pytest tests/agents/eval -m eval -v
```

Expect: all 6 golden Q&A tests still pass their existing structured-field assertions, plus one additional groundedness assertion each (7th case exempted per the last scenario above, if its policy resolves to `None` on that run).

---

## Out of scope

- **Relevance and Retrieval-relevance evaluators** — evaluated as not applicable in the governing spec's Section 12/Appendix A; not revisited here.
- **A standalone Correctness LLM-judge** — redundant with the existing deterministic field assertions in `test_golden_qa.py`, which are strictly stronger wherever ground truth is known in advance.
- **Any production code path** — this is eval-harness-only, mirroring Phase 3a; the groundedness judge is never called from `coordinator.py`/`cli.py`.
- **A routing-accuracy-style aggregate groundedness metric** — 6 cases is small enough that named per-case assertions (matching the existing golden Q&A style) are more useful than an aggregate percentage; revisit only if the case count grows substantially.

---

## Next step

This is a spec, not an implementation plan — per `AGENTS.md` Rule 1, no code should be written until it's approved. Once approved, the follow-up is a short implementation plan (same Plan Mode process as Phase 3a) covering the actual `judge_groundedness()` build and the `test_golden_qa.py` edits, followed by a real run to confirm all 6+ assertions pass against the live API.

---

**Version**: 1.0
**Last Updated**: 2026-09-14
