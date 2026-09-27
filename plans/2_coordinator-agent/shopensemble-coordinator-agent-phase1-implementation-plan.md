# Phase 1 — Foundation: Coordinator + Review-Summarization Agent

**Status:** ✅ Implemented and verified (2026-09-13) — 26/26 tests passing, verified end-to-end against the real OpenAI API via `python -m app.agents.cli`
**Governing spec:** [shopensemble-coordinator-agent-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md) (Section 13, Phase 1 row)
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (v4 entry)

## Implementation Notes (added post-implementation)

- `pydantic-ai` resolved to `2.43.0`; `Agent(model=...)` eagerly calls `infer_model` at construction, so tests pass a `pydantic_ai.models.test.TestModel` instance directly as `model=` (no `OPENAI_API_KEY` needed) rather than overriding after construction.
- `Agent.run(...)`'s return type is `AgentRunResult` with an `.output` attribute (not `.data` — that was an older API).
- Two real design decisions surfaced during implementation and were added to the spec's Appendix A rather than silently baked in: (1) `RoutingDecision` needed an `extracted_product_id` field since dispatch is manual, not native tool-calling; (2) a confident `chosen_tool="none"` must return a `FallbackResponse`, not an `AgentError` — this was caught only by the manual CLI smoke test (a policy question was being mislabeled as a routing error), not by the unit tests, since the unit tests had been written to match the code's original (incorrect) behavior rather than the intended one.
- `tests/agents/test_models.py` was renamed to `test_agent_models.py` — pytest's default (non-package) test discovery can't distinguish two files both named `test_models.py` (the existing `tests/test_models.py` already claimed that name).

## Context

`specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` defines the coordinator agent's full target architecture; its Section 13 Roadmap marks **Phase 1** (Sections 3/4/6/7/12, review-agent-only scope) as "⏳ Planned — not yet started." This plan turns that row into working code: a PydanticAI coordinator that classifies a query with a self-reported confidence score and dispatches to a single review-summarization sub-agent, per the spec's already-approved design (Pattern B, PydanticAI, structured-output confidence routing).

Confirmed via codebase exploration: this is genuinely greenfield (no `app/agents/`, no `pydantic_ai` import anywhere) and there's one real prerequisite gap — **`pydantic-ai` is not in `requirements.txt` or installed**, despite the spec assuming it.

## Prerequisite

Add `pydantic-ai` to `requirements.txt` (unpinned, like most of the file — only `sqlalchemy>=2.0` carries a pin today; record the resolved version as an inline comment once installed). Install it and confirm no conflict with the project's unpinned `pydantic`/`openai`. `OPENAI_API_KEY` is already set in `.env` and loadable via the existing `load_dotenv()` convention (`app/main.py`) — no new secret needed. Add `OPENAI_API_KEY=` to `.env.example` (currently missing despite being used — small hygiene gap the exploration surfaced).

## Design refinement to the spec (small, worth calling out)

The spec's Section 4 commits to a single structured-output call returning `RoutingDecision {chosen_tool, confidence, clarification_question}`, gated by confidence *before* any sub-agent runs (so a clarify/fallback query never reaches the sub-agent at all). That rules out relying on PydanticAI's native automatic tool-calling for dispatch (which is binary called/not-called, with no continuous confidence to threshold against) — so dispatch is manual: classify first via structured output, then call the matching Python function directly once confidence clears the threshold.

That means `RoutingDecision` needs to carry whatever argument the chosen tool requires, extracted in the same call that classifies intent (a query like "what do people say about SP0001?" has to yield `product_id="SP0001"` from the classification step itself, not a separate step). Adding **`extracted_product_id: ProductId | None = None`** to `RoutingDecision` is the smallest change that satisfies this for Phase 1's one sub-agent. Phase 2 (multiple sub-agents with different argument shapes) will need to generalize this — flag it as a new Decision Log row rather than solving it now.

## New files

```
app/agents/
├─ __init__.py
├─ models.py       # RoutingDecision, ReviewSummaryRequest, ReviewSummaryResponse, AgentError/error envelope
├─ data.py         # load_catalog_data() + reviews_for_product() — in-memory loader
├─ retry.py        # call_with_retry() — tenacity wrapper for OpenAI/PydanticAI calls
├─ review_agent.py # build_review_agent(), summarize_reviews()
├─ coordinator.py  # build_coordinator_agent(), handle_query()
└─ cli.py          # manual smoke-test entry point (no FastAPI yet — Phase 3)
```

**`app/agents/models.py`** — all extend `ShopEnsembleModel` (`app/models.py`), reusing `ProductId`:
- `ReviewSummaryRequest {product_id: ProductId}`
- `ReviewSummaryResponse {product_id: ProductId, summary: str, sentiment: Literal["positive","neutral","negative","mixed"], review_count: int}`
- `RoutingDecision {chosen_tool: Literal["review_summary_agent", "none"], confidence: float (0-1), clarification_question: str | None, extracted_product_id: ProductId | None}`
- `AgentError {code: str, message: str, sub_agent: str | None}` — the JSON error envelope from spec Section 6

**`app/agents/data.py`** — reuses the exact load pattern from `app/pipeline/orchestrator.py::_run_validation_phase` (confirmed via exploration — no existing "load all reviews" helper exists, so this assembles `iter_csv_rows` + `iter_validated_batches(..., normalize_product_row/normalize_review_row, ...)` directly, ignoring the quarantine/report machinery Phase 1 doesn't need):
```python
@dataclass(frozen=True)
class CatalogData:
    products: list[Product]
    reviews: list[Review]

def load_catalog_data(data_root=None, batch_size=500, max_invalid_rows=0) -> CatalogData: ...
def reviews_for_product(catalog: CatalogData, product_id: str) -> list[Review]: ...
```
Called once at process start (CLI/tests) and passed in — matches Section 7's singleton/DI requirement; no hidden global state.

**`app/agents/retry.py`** — mirrors `app/pipeline/persistence.py::persist_batch_with_retry`'s exact `tenacity` idiom (same `AsyncRetrying` + `retry_if_exception_type` + `stop_after_attempt` + `wait_exponential_jitter` + `reraise=True` shape, same `RetryStats(retries, latency_seconds)` return dataclass), retrying only `openai.RateLimitError`/`APITimeoutError`/`APIConnectionError` — never on a schema/validation failure, per spec Section 9.

**`app/agents/review_agent.py`**:
```python
def build_review_agent(model: str = "openai:gpt-4o-mini") -> Agent[None, ReviewSummaryResponse]: ...
async def summarize_reviews(agent, catalog: CatalogData, request: ReviewSummaryRequest) -> ReviewSummaryResponse: ...
```
A `product_id` with zero matching reviews returns `ReviewSummaryResponse(review_count=0, summary="No reviews yet for this product.", sentiment="neutral")` — a valid empty result, not an error. A `product_id` not present in the catalog at all returns the `AgentError` envelope (`code="unknown_product_id"`).

**`app/agents/coordinator.py`**:
```python
CONFIDENCE_EXEC = 0.75
CONFIDENCE_CLARIFY = 0.50

def build_coordinator_agent(model: str = "openai:gpt-4o-mini") -> Agent[None, RoutingDecision]: ...
async def handle_query(coordinator_agent, review_agent, catalog: CatalogData, query: str) -> ReviewSummaryResponse | dict: ...
```
`handle_query` calls the coordinator via `call_with_retry`, then branches on `RoutingDecision.confidence` exactly per the spec's Section 4 table (dispatch / clarify / fallback), dispatching to `summarize_reviews` only in the exec-confidence branch. An unrecognized `chosen_tool` value returns the `AgentError` envelope (`code="unknown_tool"`).

**`app/agents/cli.py`** — mirrors `app/main.py`'s `load_dotenv()` → `async def _run()` → sync `def main() -> int` → `if __name__ == "__main__": raise SystemExit(main())` shape. Loads `CatalogData` once, builds both agents once, takes a query from `sys.argv`, prints the result. This is the Phase 1 manual-verification path (`Reference/ProjectDocs/Week 3/...` milestone is explicit that Phase 1 is invoked in-process, not via an API).

## Tests (`tests/agents/`, matching `tests/pipeline/test_persistence.py`'s exact style: `_Fake*` minimal async stand-ins, `monkeypatch.setattr`, closures for call counts, no `@pytest.mark.asyncio` needed — `asyncio_mode = "auto"`)

- `test_models.py` — contract tests: each model rejects an invalid payload (bad `product_id` pattern, out-of-range `confidence`, an extra/unknown field via `extra="forbid"`) and accepts a valid one.
- `test_data.py` — `load_catalog_data()` against tiny synthetic tmp-path CSVs (same pattern as `tests/pipeline/test_orchestrator.py`'s fixtures); `reviews_for_product()` filters correctly and returns `[]` for a product with no reviews.
- `test_review_agent.py` — mocked via PydanticAI's own `pydantic_ai.models.test.TestModel`/`FunctionModel` (confirm exact API against the pinned version once installed) so no real OpenAI call happens; covers a normal summary, the zero-review case, and the unknown-product-id error envelope.
- `test_coordinator.py` — same `TestModel`/`FunctionModel` mocking, asserting: high confidence → dispatches and returns the review agent's response; mid confidence → returns `clarification_question`, review agent is **not** called (assert via a call-count spy, matching the persistence tests' `calls = {"count": 0}` idiom); low confidence → fallback message, not called; unrecognized `chosen_tool` → `AgentError` envelope.
- `test_retry.py` — directly ports `test_persistence.py`'s three-test shape onto `call_with_retry`: recovers after N transient OpenAI errors then succeeds; fails after exhausting `max_retries`; does not retry (zero backoff) a non-transient exception.

No test in this suite makes a real OpenAI call or requires `OPENAI_API_KEY` at test time — matches spec Section 12's mocking policy. This test plan is the "present the plan before generating" checkpoint the `test-suite-generator` convention calls for; implementation should generate directly from this list rather than re-deriving it.

## Verification

```bash
# 1. Install the new dependency
uv pip install pydantic-ai --python .venv/bin/python
# then add it to requirements.txt with the resolved version as a comment

# 2. New tests only
.venv/bin/python -m pytest tests/agents -q

# 3. Full existing suite unaffected
.venv/bin/python -m pytest -q -m "not integration"

# 4. Manual smoke test (real OpenAI call, needs OPENAI_API_KEY — already in .env)
.venv/bin/python -m app.agents.cli "What do people say about SP0001?"
.venv/bin/python -m app.agents.cli "What's your return policy?"   # expect clarify/fallback — no matching sub-agent yet
```

## After implementation — update specs in place (established project convention)

- `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`: flip Phase 1's row in Section 13 to ✅, check off the applicable Section 14/15 boxes, add the `extracted_product_id` refinement as a new Appendix A row.
- `.agents/memory-bank/testGenerationLog.md`: append a `v4` entry in the established format (Target source / Generated tests / Discovery / Coverage rationale / Mocks / Environment adjustments / Final execution / Committed).
- Copy this approved plan into `specs/2_coordinator-agent/shopensemble-coordinator-agent-phase1-implementation-plan.md` for git-tracked reference, matching the `shopensemble-persistence-implementation-plan.md` precedent from the data-pipeline phase.

## Out of scope for this phase (already deferred by the spec)

Recommendation/comparison/policy agents (Phase 2), FastAPI integration (Phase 3), streaming/circuit-breakers/PII/telemetry (Phase 4). No Postgres wiring — Phase 1 reads CSV in-memory per the spec's explicit Decision Log entry.
