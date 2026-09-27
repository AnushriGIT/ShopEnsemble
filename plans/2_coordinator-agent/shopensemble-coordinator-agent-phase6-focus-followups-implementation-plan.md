# Phase 6 — Focus-Scoped Follow-Ups Implementation Plan

**Status:** ✅ Implemented and verified (2026-09-26). 261 fast + 11 integration + 13 eval tests; routing accuracy 100% (42/42). See Implementation Notes below.
**Governing spec:** [shopensemble-coordinator-agent-phase6-focus-followups-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-phase6-focus-followups-spec.md).
**Baseline before starting:** fast 238 passed, integration 11 passed, eval 11 passed (all from Phase 5).

## Implementation Notes (added post-implementation)

- **Built as designed, with 3 corrections, all logged in the spec's Decision Log:**
  1. **`their` added to the group-pronoun regex** — the spec's own example phrasing ("and their reviews") didn't match the original `them|these|those|both` list; caught immediately by the first unit test.
  2. **A pre-existing Phase 5 unit test's query changed** (`test_the_id_guard_rejects_an_id_nobody_mentioned_and_calls_no_sub_agent`: `"review both"` → `"review it"`) — "both" is now a bare group reference, so the Phase 6 override correctly resolves it from real context instead of the guard blocking it; the guard itself still has its own dedicated, now-passing test with a query that isn't also a bare reference.
  3. **`MAX_RECOMMENDATIONS = 10` added to `recommendation_agent.py`** (Task 4a) — found by the new "which one is the cheapest" golden eval test, not anticipated in the original design: recommendations were unbounded (~20 observed live) while memory only tracks 10, so a superlative could silently miss the true answer. One line + one regression unit test.
- **Lint discovery (process bug, not code):** the file list built via `find -newermt` for the lint step swept in unrelated tracked files last touched by an even earlier mis-scoped Phase 5 lint run (`app/models.py`, 4 `app/pipeline/*.py` files, 3 test files — pure import-order/blank-line fixes, functionally harmless but not part of either change). Both sweeps were caught by inspecting `git diff --stat` before finishing and reverted with `git checkout --`. Going forward, lint file lists are named explicitly, never derived from file mtimes.
- **Eval note:** 2 of 3 full eval runs hit an already-documented, pre-existing Phase 5 groundedness/ID-citation flake (unrelated code paths) — not re-litigated here since it's accepted residual risk per the Phase 5 spec's own Decision Log; every Phase-6-specific test passed in all 3 runs.
- **Not committed.** All work is in the working tree; the user asked to defer git/GitHub check-in to a later step.

## Working rules
Same as the Phase 5 plan: test-first, `python -m` via the local venv, real end-to-end verification before calling anything done, one commit per task only if asked, AGENTS.md docstring/comment conventions on every new/changed function.

---

## Task 1 — `RoutingDecision.extracted_max_price` blank-string fix (independent, do first)

Test: `RoutingDecision.model_validate({..., "extracted_max_price": ""})` → `extracted_max_price is None`, no exception; also `"   "` (whitespace-only). A real (non-blank) string still fails validation as before (regression guard).
Implement: `field_validator("extracted_max_price", mode="before")` in `app/agents/models.py` coercing a blank/whitespace string to `None`.

## Task 2 — `ConversationContext.last_product_ids`

Tests (`tests/agents/test_conversation.py`): a turn with products sets `last_product_ids` to exactly that turn's IDs, in order; a later turn with different products overwrites it; a turn with **no** products (e.g. a policy-question `TurnFacts`) leaves it unchanged ("sticky"); a brand-new context has it empty; it's capped the same way `products_in_focus` is (reuses the existing per-turn cap already applied to `facts.product_ids`).
Implement: new field on `ConversationContext`; `with_turn` sets `last_product_ids = facts.product_ids[:MAX_PRODUCTS_IN_FOCUS] if facts.product_ids else self.last_product_ids`.

## Task 3 — Bare-group-reference override (fixes the reported review-scoping issue)

Tests (`tests/agents/test_coordinator.py`, using the existing `capturing_model`/`TestModel` fakes):
- "and their reviews" after a comparison of SP0001, LP0002 → dispatches `summarize_reviews_many` with **exactly** `["SP0001", "LP0002"]`, even when the fake model returns a different/larger ID list (proves the override actually replaces the model's answer, not just fills a gap).
- "reviews for the cheaper one" (a qualifier) → **not** overridden; the existing Phase 5 model-plus-guard path still runs unchanged (regression test pinning Phase 5 behavior).
- "reviews for SP0004" (explicit ID) → not overridden.
- Bare reference with `last_product_ids` empty (new conversation) → falls through to the existing guard/clarification path, unchanged.
- Bare reference with no active context (`context=None`, no session) → untouched, stateless behavior byte-for-byte.
Implement (`app/agents/coordinator.py`): a compiled regex set (`_GROUP_PRONOUN_RE`, `_PRODUCT_ID_TOKEN_RE`, `_QUALIFIER_RE`, all module constants with a comment explaining the exact reported failure they exist to prevent) and a `_is_bare_group_reference(query) -> bool` helper; in `_dispatch`, before the existing ID guard, override `decision.extracted_product_ids`/`extracted_product_id` from `context.last_product_ids` when the tool is review/comparison, context is active, the query is a bare group reference, and enough IDs exist.

## Task 4 — `evaluate_products_agent`

**4a. `recommendation_agent.py` refactor + new function.** Tests: `recommend_among_shown(agent, candidates, "which is best")` returns a `RecommendationResponse` picking only from `candidates` (never a product outside it — assert via a `TestModel` fixed to return an ID **not** in candidates, and confirm it's silently dropped, matching `recommend_products`' own existing "only pick from candidates" behavior since both now share the same underlying code path — this is a refactor-safety test, not new behavior). Implement: extract `_recommend_from_candidates(agent, candidates, request)` out of `recommend_products`; add `recommend_among_shown(agent, candidates, query_text)` building a bare `RecommendationRequest(query=query_text)` and calling the shared helper. `recommend_products` itself keeps its exact signature and behavior (regression: existing `test_recommendation_agent.py` tests untouched and green).

**4b. Deterministic superlatives + dispatch.** Tests: "which one is the cheapest" over a known candidate set → the response's single product is the actual min-price one, **with no model call** (assert via a `TestModel()` with no `custom_output_args` — if the deterministic path called it, the bare model would raise a schema error, so a clean pass proves it wasn't called); same for most-expensive/highest-rated/lowest-rated; "which one is best" (no keyword match) → falls through to `recommend_among_shown` (asserted via a fake returning a fixed pick); empty `products_in_focus` or `context=None` → `ClarificationResponse`, zero calls to either path.
Implement: `_SUPERLATIVE_MATCHERS: list[tuple[re.Pattern, Callable[[Product], ...], bool]]` (attribute getter + min/max direction) checked in order against the sanitized query; `_evaluate_products(...)` dispatch function in `coordinator.py` wired into `_dispatch`'s tool branches.

**4c. Coordinator prompt + `ToolName`.** `ToolName` gains `"evaluate_products_agent"`; prompt gains its description (spec B3's exact wording). `CoordinatorResponse`/`_facts_for` need no change — `RecommendationResponse` already has a branch; only its `tool` label there is corrected to reflect `decision.chosen_tool` instead of being hardcoded, so memory records the real path taken.

## Task 5 — Eval coverage (real API)

Add to the same aggregate sets, not a new one (matching Phase 5's own convention):
- `routing_cases.py`/`test_routing_accuracy.py`: 3 new multi-turn cases — "and their reviews" after a comparison must resolve to exactly the compared 2 (checked against the deterministic override's output, not just the raw decision, since the override runs after classification); "which one is the cheapest" after a recommendation must route to `evaluate_products_agent`; "which one is best" with no context must not act confidently.
- `golden_qa_cases.py`/`test_golden_qa.py`: the two reported conversations end to end through `handle_turn`, real catalog, real API — (1) recommend → compare 2 → "and their reviews" → exactly those 2; (2) recommend 5 → "which one is the cheapest" → the true min-price one of those 5, zero-cost path.
Run the full `-m eval` in one process; routing-accuracy gate stays ≥ 80% (currently 100%, 39/39 — record the new total).

## Task 6 — Completion gates
Fast + integration + eval green; lint the touched files; real end-to-end against the live app reproducing both originally-reported conversations exactly as pasted by the user; update the Phase 6 spec's Status, the governing spec's roadmap row, `activeContext.md`, `testGenerationLog.md`, and the knowledge artifact (one more Mermaid diagram + key-concept card, same trio updated in place).

## Risks
| Risk | Containment |
| :--- | :--- |
| Regex over-matches a legitimate query | Narrow, tested allowlist; qualifier/explicit-ID/no-context all opt out; Phase 5's existing eval cases (the cheaper one, the second one, ...) re-run unchanged as a regression check |
| Superlative regex misses a phrasing | Falls through safely to the LLM path (`recommend_among_shown`), never to an error |
| Deterministic price/rating tie | Take the first match in candidate order (documented, not asserted as "the" tie-break — no test depends on a specific tie outcome) |

---

**Version**: 2.0 (implemented)
**Last Updated**: 2026-09-26
