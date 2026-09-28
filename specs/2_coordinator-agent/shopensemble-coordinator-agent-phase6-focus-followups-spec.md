# Coordinator Agent — Phase 6: Focus-Scoped Follow-Ups Spec

**Status:** ✅ Implemented and verified (2026-09-26) — 261 fast + 11 integration + 13 eval tests; routing accuracy 100% (42/42, up from 39/39); both reported conversations verified live against the real OpenAI API. See the [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase6-focus-followups-implementation-plan.md)'s Implementation Notes.
**Governing spec:** [shopensemble-coordinator-agent-spec.md](shopensemble-coordinator-agent-spec.md), extending [shopensemble-coordinator-agent-phase5-session-memory-spec.md](shopensemble-coordinator-agent-phase5-session-memory-spec.md) — Phase 5 built session memory and reference resolution ("both", "the second one", "the cheaper one"); this phase closes two gaps Phase 5 didn't cover, found by live use immediately after Phase 5 shipped.
**Implementation plan:** [shopensemble-coordinator-agent-phase6-focus-followups-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase6-focus-followups-implementation-plan.md).

---

## Context / Narrative

Two failures were reported from real use of the Phase 5 chat, both reproduced against the live app before this spec was written (a practice this project follows for every new feature).

**Failure A — no tool answers a question about products already shown.** After a recommendation ("suggest me a laptop under $1000"), asking "which one is best" or "which is the cheapest" returned the generic fallback about half the time, and a *fresh, unrelated* recommendation the other half. Reproduced live, 2 runs. Root cause: the coordinator has exactly 4 tools (reviews, recommend, compare, policy), and none of them means "judge the products already on screen" — `recommendation_agent` always re-searches the whole catalog from scratch, discarding what was just shown.

**Failure B — reported: after comparing two products, asking for their reviews pulled reviews for every product from an earlier, larger recommendation, not just the two compared.** Reproduced attempt: 22 live runs of *recommend → compare 2 → "reviews for them"/"and their reviews"/etc.* against the current app returned the correct two products in 20 runs, a fallback in 1, and an unrelated crash in 1 (Appendix: found bug, see below) — the failure did not reproduce on demand, which points to an intermittent LLM misresolution rather than a structural bug: Phase 5's memory holds a merged pool of up to 10 recently-seen products, and a bare "them"/"these" asks the model to pick the right subset out of that pool from a rendered history rather than reading a single unambiguous fact. The fix below removes the ambiguity by construction rather than trying to reduce its probability further.

**Also found, unrelated, while reproducing Failure B:** a real crash. `RoutingDecision.extracted_max_price` returned as `""` by the model produced an unhandled `pydantic_core.ValidationError` → a raw `500`. Independent of Phase 5/6; fixed here because it was found during this work (Rule 15's "fix the actual root cause you found," not deferred to a separate unscoped pass).

### Goals
1. A follow-up that names no product ("them", "these", "both", "it") right after an action that named specific products resolves to **exactly** those products, deterministically — not by asking the model to re-derive them from a larger history.
2. The customer can ask an evaluative question about products already shown ("which is best/cheapest/highest rated") and get an answer scoped to those products, without retyping IDs or triggering a fresh catalog search.
3. Both fit inside the existing Phase 5 architecture: no sub-agent needs to become stateful, the ID guard is unchanged, and stateless requests (no `session_id`) are unaffected.

### Non-goals
General scatter-gather (still Section 8, still unbuilt); a persistent "cart" or ranking across the whole conversation; subjective judgments beyond price/rating (e.g. "best for gaming") going anywhere but the LLM.

---

## Design

### B1. A second, narrower memory field: `last_product_ids`

`ConversationContext` gains `last_product_ids: list[ProductId]` alongside the existing `products_in_focus` pool. Semantics: **the exact product IDs from the most recent turn that mentioned any**, overwritten each such turn; a turn that mentions no products (a policy question, an unresolved clarification) leaves it unchanged, so it still points at the last real set rather than going empty. `products_in_focus` (the broader, deduplicated, capped pool) is unchanged and still backs Failure-A's "which is best" over a *recommendation's* candidate set.

### B2. Deterministic override for a bare group reference (fixes Failure B)

A **bare group reference** is a query that names no product and asks about "the group" with no positional or attribute qualifier — e.g. "reviews for them", "and their reviews", "what about these", "reviews for both of these". Detected by three checks on the sanitized query, case-insensitive:
- contains a group pronoun as a whole word: `them | these | those | both`;
- contains **no** explicit product-ID-shaped token (`[A-Z]{2,3}\d{4}`);
- contains **none** of the positional/attribute words Phase 5 already relies on the model for: `first | second | third | last | cheap(er|est)? | (most )?expensive | pricier | priciest | highest | lowest | best | worst | rated | rating`.

When the coordinator's chosen tool is `review_summary_agent` or `comparison_agent`, a conversation context is active, the query is a bare group reference, and `context.last_product_ids` has enough entries for that tool (≥1 for reviews, ≥2 for compare) — **the model's own `extracted_product_id(s)` is replaced with `context.last_product_ids`** before dispatch. This is an override, not a fallback-when-empty: it fires even if the model already returned some IDs, because the reported failure is over-inclusion, not silence, and there is no way to tell a "correct" model answer from an over-inclusive one after the fact. A query with a positional/attribute word, an explicit ID, or a single-item pronoun ("it") is **not** a bare group reference and keeps going through Phase 5's existing model-plus-guard path unchanged — that path is already covered by the Phase 5 eval cases (the cheaper one, the second one, ...).

If `last_product_ids` doesn't have enough entries (e.g. bare reference right at the start of a conversation), nothing overrides and the existing ID guard/clarification path runs exactly as in Phase 5.

### B3. A capability for judging products already shown (fixes Failure A)

New tool `evaluate_products_agent`. The coordinator's prompt describes it as: judge or pick among products **already shown or discussed in this conversation** ("which one is best", "which is the cheapest", "which has the best rating") — used **instead of** `recommendation_agent` when the request is about the existing conversation, not a new search. It needs no `extracted_*` fields.

Dispatch (`app/agents/coordinator.py`, alongside the existing branches):
- If there is no active context or `products_in_focus` is empty → `ClarificationResponse` ("Which products are you asking about?"), same "ask, don't guess" convention as everything else in Phase 5 — this can only be reached with a `session_id`, since a stateless caller has no reason to phrase a query this way.
- Otherwise, the candidate set is `products_in_focus` resolved against the catalog. The query is matched, in order, against a small set of **deterministic superlatives** — cheapest/most affordable → min price; most expensive/priciest → max price; highest/best rated → max rating; lowest/worst rated → min rating — computed directly in code with **no LLM call**, so these can never be wrong. Anything else (a general "which is best", "what do you recommend of these") calls the **existing** `recommendation_agent`, restricted to exactly the shown candidates instead of a fresh catalog filter — reusing its prompt, its ID-citation rule, and its "never invent an ID" contract as-is.
- The response type is the **existing** `RecommendationResponse` (no new `CoordinatorResponse` member, no UI change — Phase 5 already put the Product ID on every card).

### B4. `RoutingDecision.extracted_max_price` blank-string crash (found bug, fixed here)

A `field_validator(mode="before")` coerces an empty/whitespace string to `None` before Decimal parsing, matching the "leave unused `extracted_*` fields empty" instruction already in the coordinator prompt — the model was already following that instruction; the schema just couldn't parse its literal meaning for a Decimal field.

### Explicitly rejected
**Trusting the model to resolve bare references from the full pool, just with a better-worded prompt.** Already tried in Phase 5 (a general reference-resolution rule exists); the failure mode is intermittent by nature, so no prompt wording can be verified never to regress it. A deterministic override removes the failure mode instead of reducing its odds. **A new response schema for "evaluate_products_agent".** Reusing `RecommendationResponse` means zero UI work and the same tested rendering (IDs on every card) Phase 5 already verified.


## Observed verification results (2026-09-26)

| Check | Result |
| :--- | :--- |
| Fast suite | **261 passed** (up from 238) |
| Integration | **11 passed** (unchanged) |
| Eval, one process | **13 passed** across 3 separate full runs; 2 unrelated, already-documented pre-existing Phase 5 groundedness/ID-citation flakes recurred (not touching any Phase 6 code — no Phase-6-specific test failed in any run) |
| Routing accuracy | **100% (42/42)**, up from 39/39 — 3 new multi-turn cases added |
| Real end-to-end (live app, real API) | Scenario 1 (recommend → "which one is the cheapest" → "which one is best") and Scenario 2 (recommend many → compare 2 → "and their reviews") both matched the spec exactly; a brand-new session's "which one is best" correctly declined rather than guessing |

**A second real bug found and fixed during this work (not in the original spec):** `recommend_products`/`recommend_among_shown` had no cap on how many products a recommendation could return (observed up to ~20 live). Session memory only tracks the 10 most recent products, so a "which one is cheapest?" question could silently miss the true answer if it fell outside that window — caught by the new golden eval test, not assumed. Fixed by capping recommendations at `MAX_RECOMMENDATIONS = 10`, matching `MAX_PRODUCTS_IN_FOCUS` exactly, so what's shown is always exactly what's remembered. See the Decision Log.

---

## Scenarios (Gherkin)

```gherkin
Feature: A bare "them"/"these" resolves to exactly the most recently shown products
  Scenario: Reviews after a comparison (the reported failure)
    Given the customer compared SP0001 and LP0002 (in that order) and, before that, saw a larger recommendation list
    When the customer asks "and their reviews"
    Then the response is review summaries for exactly SP0001 and LP0002, in that order

  Scenario: A qualifier still goes through the existing reference-resolution path
    Given the customer compared SP0001 and LP0002
    When the customer asks "reviews for the cheaper one"
    Then the response is the single review summary for whichever of the two is cheaper (Phase 5 behavior, unchanged)

  Scenario: An explicit ID is never overridden
    Given the customer compared SP0001 and LP0002
    When the customer asks "reviews for SP0004"
    Then the response is about SP0004, not SP0001/LP0002

  Scenario: No prior product context
    Given a brand-new conversation with nothing said yet
    When the customer asks "reviews for them"
    Then the response is a clarification, not a guess

Feature: Judging products already shown, without a new search
  Scenario: A deterministic superlative
    Given the customer was just shown 5 laptops with different prices
    When the customer asks "which one is the cheapest"
    Then the response names exactly the lowest-priced of those 5, computed without any LLM call

  Scenario: A general "best" question
    Given the customer was just shown 5 laptops
    When the customer asks "which one is best"
    Then the response picks from only those 5 (never a product outside that set) with a rationale

  Scenario: No products shown yet
    Given a brand-new conversation
    When the customer asks "which one is best"
    Then the response is a clarification, not a fresh, unrelated search

Feature: A blank extracted_max_price never crashes the request
  Scenario: The model returns an empty string for a filter it isn't using
    When RoutingDecision is built with extracted_max_price=""
    Then it validates successfully with extracted_max_price = None
```

---

## Files

```
app/agents/conversation.py        # ConversationContext.last_product_ids; with_turn keeps it "sticky"
app/agents/models.py              # ToolName gains "evaluate_products_agent"; RoutingDecision blank-price validator
app/agents/coordinator.py         # bare-group-reference override; evaluate_products_agent dispatch + superlative detection; prompt update
app/agents/recommendation_agent.py  # factor out _recommend_from_candidates(); new recommend_among_shown()
tests/agents/test_conversation.py, test_coordinator.py, test_recommendation_agent.py, test_agent_models.py — extended
tests/agents/eval/{routing_cases.py, test_routing_accuracy.py, golden_qa_cases.py, test_golden_qa.py} — extended
```

---

## Decision Log

| Decision | Options considered | Selected option | Reason | Date |
| :--- | :--- | :--- | :--- | :--- |
| How to fix the bare-reference ambiguity | A better prompt; a deterministic override for a narrow, detectable pattern | **Deterministic override**, scoped to bare group pronouns with no qualifier/explicit ID | The failure is intermittent by construction (an LLM choosing among a rendered list); only removing the choice removes the risk | 2026-09-26 |
| Override vs. fallback-when-empty | Only substitute when the model returns zero IDs; always substitute for a detected bare reference | **Always substitute** for a detected bare reference | The reported failure is over-inclusion (the model returned too many, not none) — a fallback-only rule would not have caught it | 2026-09-26 |
| Which pool backs "which is best" | `last_product_ids` (narrow); `products_in_focus` (broader recent pool) | **`products_in_focus`** | "Which one is best" naturally means the set just discussed/recommended, which can be larger than the single most recent turn's set | 2026-09-26 |
| Response shape for evaluate_products_agent | New `CoordinatorResponse` member; reuse `RecommendationResponse` | **Reuse `RecommendationResponse`** | Zero UI change; Phase 5 already verified ID-on-card rendering for this exact shape | 2026-09-26 |
| Scope of deterministic superlatives | LLM for everything; deterministic for price/rating extremes, LLM only for subjective "best" | **Deterministic for price/rating extremes** | These have one objectively correct answer computable from the catalog; no reason to risk an LLM call for them | 2026-09-26 |
| Blank-price crash | Ignore (out of scope); fix now | **Fix now** | Found during this work's own reproduction runs (Rule 15); a one-line validator, fully test-covered | 2026-09-26 |
| Recommendation output size | Unbounded (as before); capped at `MAX_RECOMMENDATIONS = 10` | **Capped at 10, matching `MAX_PRODUCTS_IN_FOCUS`** | Found via a real-API eval failure: a recommendation of 17 laptops meant the true cheapest fell outside the 10 memory tracks, so "which one is cheapest?" silently answered over an incomplete set | 2026-09-26 |
| Bare group pronoun list | `them / these / those / both` | **+ `their`** | The natural phrasing "and their reviews" (used in the spec's own examples) didn't match the original regex — found immediately by the first unit test written against it | 2026-09-26 |

---

## Out of scope
General scatter-gather/composite routing; a running "cart" or cross-conversation ranking; subjective superlatives beyond price/rating going to a deterministic path.

---

**Version**: 2.0 (implemented; two additional fixes found and logged during implementation)
**Last Updated**: 2026-09-26
