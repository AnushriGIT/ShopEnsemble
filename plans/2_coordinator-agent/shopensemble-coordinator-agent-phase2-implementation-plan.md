# Phase 2 — Expansion: Recommendation, Comparison, and Policy/FAQ Agents

**Status:** ✅ Implemented and verified (2026-09-14) — 56/56 tests passing, all 4 sub-agents verified end-to-end against the real OpenAI API
**Governing spec:** [shopensemble-coordinator-agent-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md) (Section 13, Phase 2 row)
**Precedes:** Scatter-gather/composite routing (Section 8) — deliberately out of scope here, deferred to its own future plan
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (v5 entry)

## Implementation Notes (added post-implementation)

- **Sub-agent output reconstruction, redesigned before first test was even written**: the plan's sketch of each sub-agent had the LLM output the public `*Response` schema directly. Caught during design review (before coding): `Product` has fields (`stock`) never shown to the model, so asking it to reconstruct full `Product`/`StorePolicy` objects risked fabrication. Redesigned all 3 new sub-agents around a module-local "reference-only" output type (`RecommendationPick`, `ComparisonAnalysis`, `PolicyAnswer`) that the LLM populates with IDs or a list position; Python resolves the real records. Documented in the spec's Section 3 and Appendix A.
- **`policy_faq_agent`'s first version of that pattern still had a bug**: asking the model to freely echo back a policy's `description` text (`matched_policy_description: str | None`) reliably failed to match in practice — manual smoke testing (`"what's your return policy for laptops?"`) showed the model echoing the *entire* formatted candidate line (description + timeframe + conditions) rather than isolating the description. Fixed by switching to an explicit 1-based `matched_policy_number` against a numbered list — the same clean-key idiom `product_id` already gave the other two agents. Caught and fixed before moving on, with a regression test added (`test_answer_policy_question_ignores_an_out_of_range_policy_number`).
- **A real extraction bug, only caught by the manual CLI smoke test, not the unit tests**: `"recommend a cheap speaker"` returned zero products. The coordinator had extracted `extracted_category="speakers"` (plural) against the catalog's exact `"speaker"` (singular) — `filter_products` did an exact `==` match, so a natural plural silently zeroed out every candidate. Fixed two ways: the coordinator's system prompt now states the 4 exact catalog category values explicitly, and `filter_products` gained a case-insensitive, trailing-`s`-tolerant fallback as defense-in-depth (mocked unit tests alone couldn't have caught this — the coordinator's own extraction behavior, not application logic, was the bug).
- All 3 bugs above were caught and fixed *before* being reported as complete — consistent with `AGENTS.md` Rule 9 ("verify against reality... run at least one real end-to-end execution").

## Context

`specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` Section 13 marks **Phase 2** as "⏳ Planned": the 3 remaining sub-agents (recommendation, comparison, policy/FAQ) plus scatter-gather composite routing. Per your scoping decision, **this plan covers only the 3 sub-agents**, single-dispatch, same architecture as Phase 1's review agent — scatter-gather stays deferred to its own future plan, matching Section 8's own trigger condition ("once recommendation/comparison/policy agents exist").

Per your extraction-design decision, **`RoutingDecision` gains flat optional fields** (one classify+extract LLM call, no added round-trip), continuing the exact pattern Phase 1 established and that the spec's Appendix A already anticipated ("Phase 2 will need to generalize this field").

Verified current state (via Explore agent): Phase 1's `app/agents/` (7 files, 26 tests) is unchanged since implementation; `app/pipeline/ingestion.py`/`etl.py` already have `POLICY_HEADERS`/`normalize_policy_row`, symmetric with the product/review loaders `app/agents/data.py` already reuses — so policy loading is a straight extension of the existing pattern, not new plumbing.

---

## Design

### 1. Extract `PolicyType` in `app/models.py` (small, shared-file touch)
`StorePolicy.policy_type` is currently an inline `Literal[8 values]`. Pull it out to a named alias (`PolicyType = Literal["exchanges", ...]`, next to `ProductId`/`Rating`) and use it in both `StorePolicy` and the new `PolicyRequest` — avoids the 8-value list drifting out of sync between two files. No behavior change.

### 2. `app/agents/models.py` — new I/O models + `RoutingDecision` extension
```python
class RecommendationRequest(ShopEnsembleModel):
    query: str
    max_price: Decimal | None = None
    category: str | None = None

class RecommendationResponse(ShopEnsembleModel):
    products: list[Product]
    rationale: str

class ComparisonRequest(ShopEnsembleModel):
    product_ids: list[ProductId]

class ComparisonResponse(ShopEnsembleModel):
    products: list[Product]
    differences: list[str]

class PolicyRequest(ShopEnsembleModel):
    policy_type: PolicyType | None = None
    question: str

class PolicyResponse(ShopEnsembleModel):
    policy: StorePolicy | None
    answer: str
```
`ToolName` grows to `Literal["review_summary_agent", "recommendation_agent", "comparison_agent", "policy_faq_agent", "none"]`. `RoutingDecision` gains `extracted_product_ids: list[ProductId] | None`, `extracted_max_price: Decimal | None`, `extracted_category: str | None`, `extracted_policy_type: PolicyType | None` (existing `extracted_product_id` stays, used only by `review_summary_agent`).

**Only `review_summary_agent` and `comparison_agent` have a "missing required argument" error path** — recommendation's `query` and policy's `question` are just the original user text (always present); `max_price`/`category`/`policy_type` are optional filters. `comparison_agent` requires ≥2 valid `extracted_product_ids` to proceed.

### 3. `app/agents/data.py` — load policies, add lookup helpers
Extend `CatalogData` with `policies: list[StorePolicy]`; extend `load_catalog_data()` to also load `store_policies.csv` via `iter_csv_rows(..., POLICY_HEADERS, ...)` + `iter_validated_batches(..., normalize_policy_row, ...)` — identical shape to the existing product/review loading, reusing `app.pipeline.etl.normalize_policy_row` (confirmed already implemented and symmetric). Add:
- `products_by_ids(catalog, product_ids) -> list[Product]` (comparison)
- `filter_products(catalog, max_price=None, category=None) -> list[Product]` (recommendation)
- `policies_by_type(catalog, policy_type) -> list[StorePolicy]` (policy/FAQ; returns all 22 if `policy_type` is `None`)

### 4. Three new sub-agent modules (one file each, mirroring `review_agent.py`'s shape exactly)

**`app/agents/recommendation_agent.py`**: `build_recommendation_agent()`, `recommend_products(agent, catalog, request) -> RecommendationResponse`. Filters the catalog deterministically first (`filter_products`, capped to top ~20 by rating), then asks the LLM to select/rank from that filtered set and write a rationale — same "filter in Python, reason in the LLM over a bounded set" idiom as `review_agent._build_prompt`'s review cap. No candidates matching → `RecommendationResponse(products=[], rationale="...")`, not an error (same "empty is valid" precedent as review's zero-reviews case).

**`app/agents/comparison_agent.py`**: `build_comparison_agent()`, `compare_products(agent, catalog, request) -> ComparisonResponse | AgentErrorEnvelope`. Looks up each `product_id` via `products_by_ids`; any unknown ID → `AgentErrorEnvelope(code="unknown_product_id")`; fewer than 2 resolve → `AgentErrorEnvelope(code="insufficient_product_ids")`; otherwise sends the found products to the LLM for a `differences` list.

**`app/agents/policy_faq_agent.py`**: `build_policy_faq_agent()`, `answer_policy_question(agent, catalog, request) -> PolicyResponse`. Sends `policies_by_type(catalog, request.policy_type)` (filtered set, or all 22 if no `policy_type` extracted) plus the question to the LLM; the LLM synthesizes `answer` and may identify a single best-matching `policy`, or leave it `None` if ambiguous — consistent with the "don't fabricate, ground in provided data" instruction already used in `REVIEW_SYSTEM_PROMPT`.

### 5. `app/agents/coordinator.py` — dispatch + a `SubAgents` container
`handle_query`'s parameter list would grow to 6 positional agent/catalog/query args across 4 sub-agents; introduce a small container instead:
```python
@dataclass(frozen=True)
class SubAgents:
    review: Agent[None, ReviewSummaryResponse]
    recommendation: Agent[None, RecommendationResponse]
    comparison: Agent[None, ComparisonResponse]
    policy_faq: Agent[None, PolicyResponse]
```
`handle_query(coordinator_agent, sub_agents: SubAgents, catalog, query)` — one parameter instead of four, and stays stable as more sub-agents arrive later. This changes Phase 1's existing signature; update its 2 call sites (`cli.py`, `tests/agents/test_coordinator.py`) accordingly. Add one dispatch branch per new tool, following the exact existing "check required extracted args → dispatch or `missing_argument` error" shape. Update `COORDINATOR_SYSTEM_PROMPT` to describe all 4 sub-agents and which fields to extract for each.

### 6. `app/agents/cli.py`
Build the 3 new agents at startup alongside the existing 2, wrap in `SubAgents(...)`.

---

## Tests (`tests/agents/`, matching the exact established style: `TestModel(custom_output_args=...)`, catalog fixtures, `monkeypatch` + call-count spies)

- `test_data.py`: extend for policy loading + the 3 new lookup helpers (including the "no `policy_type` filter → all 22" case).
- `test_recommendation_agent.py`, `test_comparison_agent.py`, `test_policy_faq_agent.py` (new): one file each, mirroring `test_review_agent.py`'s 3-test shape — happy path, an edge case specific to that agent (empty recommendation results / <2 product IDs for comparison / no `policy_type` filter for policy), and an error path where one exists.
- `test_coordinator.py`: extend with 2 new tests per new tool (dispatch on high confidence + valid args; `missing_argument` error where applicable) — same monkeypatch-and-count-calls pattern as the existing 5 tests. Update all 5 existing tests' `build_review_agent(...)` calls to pass a `SubAgents(...)` instead of separate params.
- `test_agent_models.py`: contract tests for the 3 new request/response models + the extended `RoutingDecision` fields.

## Verification

```bash
.venv/bin/python -m pytest tests/agents -q                 # expect existing 26 + new tests, all passing
.venv/bin/python -m pytest -q -m "not integration"          # no regressions elsewhere

# Manual smoke tests (real OpenAI calls)
.venv/bin/python -m app.agents.cli "recommend a laptop under 800"
.venv/bin/python -m app.agents.cli "compare SP0001 and SP0002"
.venv/bin/python -m app.agents.cli "what's your return policy for laptops?"
.venv/bin/python -m app.agents.cli "What do people say about SP0001?"   # re-verify Phase 1 still works post-SubAgents refactor
```

## After implementation — update in place (established convention)

- `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`: Section 3's "Roadmap phase" column for the 3 newly-shipped sub-agents; Section 13's Phase 2 row (partial ✅ — scatter-gather still ⏳); new Appendix A rows for the flat-fields extraction decision (now resolved) and the `SubAgents` container refactor.
- `.agents/memory-bank/testGenerationLog.md`: append a `v5` entry, same format as `v4`.
- `Reference/Learning/coordinator-agent/` pair: update in place (not a new file) — add the 3 new sub-agents to the reference doc's module table and a new diagram/section for their dispatch flow, per the project's knowledge-artifact convention.
- Copy this approved plan into `specs/2_coordinator-agent/shopensemble-coordinator-agent-phase2-implementation-plan.md`, matching the Phase 1 precedent.

## Out of scope for this plan

Scatter-gather/composite multi-agent routing (Section 8) — deferred to its own future plan once these 3 agents exist, per your scoping decision. FastAPI (Phase 3), evaluation harness (Phase 3), UI/hardening (Phase 4). No Postgres wiring — still CSV in-memory, same as Phase 1.
