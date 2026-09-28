# Phase 3a — Validation: Routing-Accuracy & Golden Q&A Evaluation Harness

**Status:** ✅ Implemented and verified (2026-09-14) — 7/7 eval tests passing against the real OpenAI API; fast suite (101 tests) unaffected
**Governing spec:** [shopensemble-coordinator-agent-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md) (Section 13, Phase 3 row; Section 12 requirement)
**Precedes:** The FastAPI layer (Section 1/7) — deliberately out of scope here, deferred to its own follow-up plan (Phase 3b)
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (v6 entry)

## Implementation Notes (added post-implementation)

- **Observed routing-accuracy baseline (2026-09-14, `gpt-4o-mini`, 29 cases)**: 27/29 correct (93.1%). One further case (`"What's the difference between LP0002 and LP0007?"`) raised `pydantic_ai.exceptions.UnexpectedModelBehavior: Exceeded maximum output retries (1)` — the model's structured output failed PydanticAI's own retry-validation loop, a real and occasional failure mode of a live LLM call rather than a simple misclassification. The one clear miss: `"Cancel my order number 12345."` routed to `policy_faq_agent` instead of the expected `"none"`.
- **Design adjustment made during this run, not anticipated in the draft plan**: the aggregate test originally called `agent.run(query)` unguarded — the `UnexpectedModelBehavior` case above then crashed the whole test instead of counting as one miss. Wrapped each call in `try/except Exception`, recording a failed call as a miss with the exception repr in the failure message — consistent with the eval harness's purpose (measuring real-world reliability, including validation failures) rather than only measuring classification correctness.
- **Threshold set from the observed baseline**: 93.1% observed → asserted at **80%** (allows up to ~5 more misses out of 29 before failing), giving headroom for normal LLM run-to-run variance without going flaky while still catching a real regression. See spec Section 11/Appendix A.
- All 6 golden Q&A cases — including both known-bug regressions (category pluralization, policy-number matching) — passed on first real run; no further fixes needed.

## Context

`specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` Section 13 marks **Phase 3** as "⏳ Planned": an evaluation harness (Section 12) and a FastAPI layer (Section 1/7). Per your scoping decision, **this plan covers only the evaluation harness** — it measures what Phases 1-2 actually built, needs no new production surface, and its result (a real baseline number) is what Section 11's "Routing accuracy: TBD — set once a baseline exists" is waiting on. The FastAPI layer is deferred to its own follow-up plan.

Verified via Explore agent: no eval/golden-dataset file exists anywhere yet; `app/agents/coordinator.py`, `models.py`, `cli.py` are unchanged since Phase 2; both governing specs (`shopensemble-coordinator-agent-spec.md` Section 12, `shopensemble-project-requirements.md` Section 9) explicitly require this work to go through a discovery-then-plan-then-build test-generation process — this plan **is** that process's Step 1-2 output (discovery already done via Explore agent above; the plan below is the draft test plan), so implementation should generate directly from it rather than re-deriving.

Known-bug mining (test-generation Step 1.2, from `testGenerationLog.md`'s `v5` entry) surfaces 2 real bugs worth encoding as explicit golden-set regression cases: the category-pluralization miss (`"recommend a cheap speaker"`) and the policy-matching fix (`"what's your return policy for laptops?"`).

---

## Design

### Two distinct eval artifacts, per spec Section 12

1. **Routing-accuracy eval set** — tests *classification only* (`coordinator_agent.run(query).output.chosen_tool`), not full dispatch. An aggregate metric (Section 11's "Routing accuracy" target), tolerant of a few misses — LLM classification has inherent non-determinism, so this is one aggregate `%% correct >= threshold` assertion, not one hard assertion per query.
2. **Golden Q&A regression set** — tests full `handle_query()` end-to-end for a handful of unambiguous, representative queries per sub-agent (especially policy/FAQ, per `shopensemble-project-requirements.md` Section 9). These *should* reliably pass every time — individual hard assertions per case, written as named test functions (not a generic data-driven loop — each case checks different response fields, so explicit is more readable here, matching `test_review_agent.py`'s style over `test_data.py`'s parametrized style).

### Both run against the real OpenAI API — opt-in, not part of the default suite

New `pytest.ini_options` marker `eval` in `pyproject.toml` (alongside the existing `integration` marker), with a session-scoped fixture skipping cleanly (`pytest.skip(...)`) if `OPENAI_API_KEY` is absent — mirrors `tests/conftest.py`'s `postgres_available` skip-if-unreachable idiom exactly (Rule 12). Update the project's documented "fast" test command from `pytest -q -m "not integration"` to `pytest -q -m "not integration and not eval"` (real API calls cost money and add latency — never run by default).

### Setting the actual accuracy threshold

No pre-existing baseline exists. Implementation runs the routing-accuracy set once for real, observes the actual pass rate, and sets the asserted threshold with headroom below that observed number (e.g. an 95% baseline → assert ≥85%, tolerating normal LLM run-to-run variance without being flaky while still catching a real regression). The concrete numbers get written into the spec (Section 11) and Appendix A as part of this plan's "after implementation" step — not guessed now.

### Eval set composition (sized to keep real-API runs fast/affordable)

- **Routing-accuracy set** (`tests/agents/eval/routing_cases.py`): ~6 queries per tool × 4 tools (varied phrasing, including the extraction-heavy ones — multi-ID comparisons, price+category recommendations, specific `policy_type` questions) + ~4-6 deliberately ambiguous/out-of-scope queries expected to route to `"none"` or land in the clarify band. ~30 cases total.
- **Golden Q&A set** (`tests/agents/eval/golden_qa_cases.py`, as named test functions in `test_golden_qa.py`): 2-3 cases per sub-agent (8-12 total), including the 2 known-bug regression queries above, each asserting on the specific response fields that matter (e.g. a policy query asserts `response.policy.timeframe` matches the real catalog data, not just that *some* answer came back).

---

## Files

```
tests/agents/eval/
├── conftest.py              # session-scoped real catalog/coordinator_agent/sub_agents fixtures
│                             # (real agents, not TestModel — this is the one place in the
│                             # test suite that intentionally calls the real API) + the
│                             # OPENAI_API_KEY skip guard
├── routing_cases.py         # ROUTING_CASES: list[tuple[query: str, expected_tool: ToolName]]
├── test_routing_accuracy.py # one aggregate test: loop, tally, assert overall % >= threshold,
│                             # failure message lists exactly which queries misrouted
├── golden_qa_cases.py       # shared real product-id/policy-type constants used by both files
└── test_golden_qa.py        # 8-12 named tests, one per representative query, via handle_query()
```

`pyproject.toml`: add `"eval: requires OPENAI_API_KEY and makes real, billed OpenAI calls"` to `markers`.

Building the session-scoped fixtures reuses exactly what already exists — `load_catalog_data()`, `build_coordinator_agent()`, `build_review_agent()`/`build_recommendation_agent()`/`build_comparison_agent()`/`build_policy_faq_agent()`, `SubAgents(...)` — no new production code, this plan is test-only.

---

## Verification

```bash
# Fast suite unaffected (eval tests skip without a key; excluded from "fast" by convention)
.venv/bin/python -m pytest -q -m "not integration and not eval"

# Run the eval harness for real (costs real OpenAI calls)
.venv/bin/python -m pytest tests/agents/eval -m eval -v

# Confirm clean skip behavior without a key
OPENAI_API_KEY= .venv/bin/python -m pytest tests/agents/eval -m eval -v
```

Expect: the routing-accuracy test reports the observed %% and passes against the threshold set from that same run; all golden Q&A tests pass individually; re-running the golden set's 2 known-bug regression queries confirms the Phase 2 fixes hold.

## After implementation — update in place (established convention)

- `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`: Section 11's "Routing accuracy: TBD" → the real observed target; Section 13's Phase 3 row → partial ✅ (eval harness shipped, FastAPI still ⏳); new Appendix A rows for the threshold decision and the eval-set-composition decision.
- `.agents/memory-bank/testGenerationLog.md`: append a `v6` entry, same format as `v5`.
- `Reference/Learning/coordinator-agent/` pair: update in place — add an "Evaluation" section to the reference doc (how to run it, what the baseline is) and, if warranted, a small diagram addition.
- Copy this approved plan into `specs/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md`, matching the Phase 1/2 precedent.

## Out of scope for this plan

The FastAPI layer (health + query endpoints, contract tests) — deferred to its own follow-up plan per your scoping decision. Prompt tuning is *conditional*, not a guaranteed deliverable: only if the observed baseline reveals a clear systematic misrouting pattern, not open-ended iteration. Scatter-gather (still deferred from Phase 2). No Postgres wiring — still CSV in-memory.
