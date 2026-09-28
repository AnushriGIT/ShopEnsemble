# ShopEnsemble Coordinator Agent Specification

Built from a standard coordinator-agent spec template. This is one holistic document covering the coordinator agent's full target architecture — Section 13 tracks what's actually built vs. planned. **Update this file in place** as each phase's work lands; do not fork a new spec per phase.

**Plans moved out of `specs/` into `plans/` (2026-09-17)** — `specs/` now holds only specifications; every implementation plan below lives in the mirrored `plans/2_coordinator-agent/` folder instead.

**Phase 1 implementation plan**: [shopensemble-coordinator-agent-phase1-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase1-implementation-plan.md) (implemented and verified).

**Phase 1 sequence flow & command reference**: [Reference/Learning/coordinator-agent/](../../Reference/Learning/coordinator-agent/INDEX.md) — visual diagrams + copy-paste commands.

**Phase 2 implementation plan**: [shopensemble-coordinator-agent-phase2-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase2-implementation-plan.md) (implemented and verified).

**Phase 3a (evaluation harness) implementation plan**: [shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md) (implemented and verified).

**Phase 3a Part 2 (groundedness evaluator) spec**: [shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md](shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md). **Implementation plan**: [shopensemble-coordinator-agent-phase3a-part2-groundedness-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-part2-groundedness-implementation-plan.md) (both implemented and verified).

**Phase 3b (FastAPI layer) implementation plan**: [shopensemble-coordinator-agent-phase3b-api-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3b-api-implementation-plan.md) (implemented and verified).

**Phase 4a (Streamlit UI) implementation plan**: [shopensemble-coordinator-agent-phase4a-ui-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4a-ui-implementation-plan.md) (implemented and verified).

**Phase 4b (backend hardening) implementation plan**: [shopensemble-coordinator-agent-phase4b-backend-hardening-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4b-backend-hardening-implementation-plan.md) (implemented and verified).

**Phase 4c (catalog browse) spec + implementation plan**: [shopensemble-coordinator-agent-phase4c-catalog-browse-spec.md](shopensemble-coordinator-agent-phase4c-catalog-browse-spec.md), [shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md) (implemented and verified).

**Phase 5 (session memory + product-ID visibility) spec + implementation plan** — ✅ implemented and verified (2026-09-26): [shopensemble-coordinator-agent-phase5-session-memory-spec.md](shopensemble-coordinator-agent-phase5-session-memory-spec.md), [shopensemble-coordinator-agent-phase5-session-memory-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase5-session-memory-implementation-plan.md). Session-scoped, in-process, ephemeral memory for the Chat Assistant, a multi-product review path, and the Product ID on every product card.

**Phase-to-course-milestone mapping** (this project follows an 8-week course; phases are the generalized, schedule-independent grouping used throughout this document):

| Phase | Course milestone(s) |
| :--- | :--- |
| Phase 1 — Foundation | Week 3 |
| Phase 2 — Expansion | Week 4 |
| Phase 3 — Validation & Integration | Weeks 5-6 |
| Phase 4 — Production Readiness | Weeks 7-8 |

---

## Table of Contents
1. Meta and Scope
2. Architecture Pattern Selection
3. Sub-Agent Registry & Tool Contract
4. Routing & Intent Classification
5. State Management & Memory Hierarchy
6. Schema Typing & Validation
7. Dependency Injection & Resource Lifecycle
8. Cognitive Features (Tier 2)
9. Resiliency & Graceful Degradation
10. Data Governance & Security
11. Telemetry, Tracing & Operational SLA
12. Required Test Suite & Evaluation
13. Roadmap / Phase Mapping
14. Acceptance Criteria (pre-build gate)
15. Production Verification Checklist (post-build gate)
16. Appendix A: Decision Log
17. Appendix B: Out-of-Scope / Non-Goals

---

## 1. Meta and Scope

| Field | Value |
| :--- | :--- |
| Document Version | 1.0 |
| System ID / Code Name | SHOPENSEMBLE-COORD-AGENT |
| Lead System Architect | Development Team |
| Runtime Target | Python 3.12, **PydanticAI** (see Appendix A — resolves project requirements' Open Decision #4) |
| Deployment Topology | Local dev / CLI, **and** a FastAPI service (`app/api/`, Phase 3b ✅, 2026-09-16) — both entry points wrap the same `handle_query()`, neither is deprecated |
| LLM Provider(s) + Model(s) | OpenAI (already in `requirements.txt`); exact model TBD at implementation time |

### Required discovery — answered
- **Domains/sub-agents at launch (Phase 1)**: coordinator + review-summarization agent only. Recommendation, price/feature comparison, and policy/FAQ agents follow in Phase 2 (see Section 3).
- **Expected QPS/latency**: no production load target yet — this is a capstone project, not a live service. Revisit before Phase 3's FastAPI integration.
- **Evaluation dataset**: does not exist yet. Phase 3 milestone per the delivery roadmap; Section 12 defines the contract now so Phase 1 code is written test-first against it.
- **API layer** ✅ implemented (Phase 3b, 2026-09-16): `app/api/` — `GET /health`, `POST /query`. Phase 1's coordinator was invoked in-process only (script/notebook/tests, matching the actual Phase 1 milestone `Reference/ProjectDocs/Week 3/ShopEnsembleAIWeek3_Updated.ipynb`); `app/agents/cli.py` remains the separate manual entry point, unchanged — the API layer is additive, not a replacement.

---

## 2. Architecture Pattern Selection

**Selected pattern**: **B — Supervisor / Orchestrator (Hierarchical)**

**Justification**: The capstone's own target queries are composite by nature — "compare product A and B and verify the warranty policy" spans comparison + policy domains in one turn (`specs/shopensemble-project-requirements.md` Section 2 Capstone Outcomes lists recommendation, comparison, review summarization, and policy Q&A as separate capabilities the *same* coordinator must unify). Pattern A (pure router) can't synthesize across more than one sub-agent's output; Pattern C (ReAct loop) is more machinery than a bounded, known set of 4 sub-agent domains needs. Phase 1 only exercises the single-dispatch case (coordinator → review agent), but the architecture is chosen for where Phase 2+ is going, not just Phase 1's minimum.

---

## 3. Sub-Agent Registry & Tool Contract

| Sub-agent | Trigger intents / example queries | Input schema | Output schema | Data it owns | Roadmap phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `review_summary_agent` | "What do people say about SP0001?", "summarize reviews for this speaker" | `ReviewSummaryRequest {product_id: ProductId}` | `ReviewSummaryResponse {product_id: ProductId, summary: str, sentiment: Literal["positive","neutral","negative","mixed"], review_count: int}` | `data/reviews.csv` (via `Review` model, `app/models.py`) | **Phase 1** |
| `recommendation_agent` | "recommend a laptop under $800" | `RecommendationRequest {query: str, max_price: Decimal \| None, category: str \| None}` | `RecommendationResponse {products: list[Product], rationale: str}` | `data/products.csv` (`Product` model) | **Phase 2** ✅ |
| `comparison_agent` | "compare SP0001 and SP0002" | `ComparisonRequest {product_ids: list[ProductId]}` | `ComparisonResponse {products: list[Product], differences: list[str]}` | `data/products.csv` (`Product` model) | **Phase 2** ✅ |
| `policy_faq_agent` | "what's your return policy?" | `PolicyRequest {policy_type: Literal[...8 types...] \| None, question: str}` | `PolicyResponse {policy: StorePolicy \| None, answer: str}` | `data/store_policies.csv` (`StorePolicy` model) | **Phase 2** ✅ |

All request/response models extend the project's existing `ShopEnsembleModel` base (`app/models.py`: `extra="forbid"`, `str_strip_whitespace=True`) for consistency with the catalog models already in place.

**Tool-calling convention**: PydanticAI `@coordinator_agent.tool` per sub-agent, function name = table's `Sub-agent` column, docstring = the trigger-intent description the router classifies against. Each tool's parameter and return types are the schemas above, so PydanticAI validates the boundary automatically.

**Internal LLM-output pattern (Phase 2)**: each of `recommendation_agent`/`comparison_agent`/`policy_faq_agent`'s *actual* PydanticAI call uses a smaller, module-local output type (`RecommendationPick`, `ComparisonAnalysis`, `PolicyAnswer`) — never the public `*Response` schema above directly. The model only ever picks a reference (a product ID, or a 1-based position in a numbered candidate list) into data Python already resolved deterministically from the catalog; Python then assembles the real `*Response` from that reference. This avoids the model fabricating fields it was never shown (e.g. `Product.stock`) and was adopted after `policy_faq_agent`'s first version — which asked the model to freely echo back a policy's description text — was found via manual smoke testing to reliably fail to match (the model echoed the whole formatted candidate line, not just the description).

**Phase 1 data access**: sub-agents read from **in-memory data loaded from CSV at startup** (reusing `app.pipeline.ingestion`/`app.pipeline.etl`), not the PostgreSQL persistence layer — the Phase 1 milestone notebook is explicit that the coordinator "will load product, review, and policy data from the CSV files." Switching sub-agents to query Postgres instead is a later decision, not required for Phase 1.

---

## 4. Routing & Intent Classification

**Confidence source**: the coordinator's own PydanticAI call returns a structured `RoutingDecision` model — `{chosen_tool: str, confidence: float, clarification_question: str | None}` — as its output type. `confidence` is the model's self-reported certainty in its own structured output, not a separately computed metric. This is the simplest concrete mechanism available in PydanticAI without adding a second embedding-similarity system, and is sufficient for Phase 1's single-sub-agent case; revisit if Phase 3 evaluation (Section 12) shows self-reported confidence is poorly calibrated.

| Confidence range (`C`) | Route action | Threshold |
| :--- | :--- | :--- |
| `C ≥ τ_exec` | Direct sub-agent dispatch | 0.75 |
| `τ_clarify ≤ C < τ_exec` | Clarification / disambiguation turn | 0.50 – 0.75 |
| `C < τ_clarify` | Global fallback ("I'm not sure how to help with that") | < 0.50 |

No human-escalation path exists yet (Section 8) — below-threshold queries get the fallback message, not a queue handoff, until Section 8's HITL trigger is met.

Every routing decision (`chosen_tool`, `confidence`, action taken) is logged — this is the raw material for Section 12's routing-accuracy eval set once it exists.

---

## 5. State Management & Memory Hierarchy

- **Session identity**: no customer-account/login system exists anywhere in this project (`specs/shopensemble-project-requirements.md` has no such requirement). A session is a single coordinator invocation today (Phase 1, in-process); once FastAPI arrives (Phase 3), a `session_id` will be generated per HTTP session/conversation, not tied to a customer identity.
- **Context decoupling**: not yet applicable — Phase 1 has no multi-turn conversation loop, just single-shot query → routing → sub-agent → response. Revisit once a conversation loop exists. **Revisited and implemented (2026-09-26)**: see the [Phase 5 spec](shopensemble-coordinator-agent-phase5-session-memory-spec.md) — a client-generated `session_id` on `POST /query`, server-side in-process memory of structured facts (never model-written prose) with a sliding 30-min TTL, 6-turn / 10-product / 1000-session bounds, for the Chat Assistant only. The statements above describe the original Phase 1 baseline; long-term memory remains out of scope (Appendix B).
- **Long-term memory** (customer profile/order history): **out of scope** — see Appendix B. There is no order-history or customer-profile data source in this project.
- **Token sliding window**: not yet applicable at Phase 1's single-shot scale; needed once a multi-turn conversation loop is built.

---

## 6. Schema Typing & Validation

- Every sub-agent's request/response (Section 3) and the coordinator's own `RoutingDecision` (Section 4) are Pydantic v2 models extending `ShopEnsembleModel`.
- On a schema violation (e.g. an unknown `product_id`), return a JSON error envelope, not an unhandled exception:
  ```json
  {"error": {"code": "unknown_product_id", "message": "...", "sub_agent": "review_summary_agent"}}
  ```
- This mirrors the existing pipeline convention of quarantining bad rows with structured context rather than raising uncaught exceptions (`app/pipeline/etl.py`).

---

## 7. Dependency Injection & Resource Lifecycle

**Singleton resources (Phase 1)**:
- The OpenAI client / PydanticAI model client — instantiated once, injected into the coordinator and every sub-agent.
- The in-memory product/review/policy dataset (Section 3's "Phase 1 data access") — loaded once at process start via the existing `app.pipeline.ingestion`/`etl` functions, not re-read per query.

**Later**: an `asyncpg` connection pool, if/when sub-agents move from CSV to the Postgres persistence layer (`app/pipeline/persistence.py`, already built for the data pipeline — reusable here, not yet wired to the agents).

**API-layer mechanism (Phase 3b, ✅ 2026-09-16)**: the CLI (`app/agents/cli.py`) builds these singletons fresh per invocation, since each invocation is a separate process — the API layer needs them built once per **process**, not once per request. `app/api/main.py`'s FastAPI `lifespan` context manager builds the catalog, coordinator agent, and all 4 sub-agents exactly once at server startup, stored as an `AppState` (`app/api/dependencies.py`) on `app.state`. Routes read it back via a `Depends(get_app_state)` provider rather than `request.app.state` directly — that indirection is what lets contract tests swap in `TestModel`-built agents via `app.dependency_overrides`, mirroring `tests/agents/`'s existing fake-agent convention without a second mocking approach.

---

## 8. Cognitive Features (Tier 2)

| Feature | Trigger to build it | Status |
| :--- | :--- | :--- |
| Scatter-Gather / Fan-Out | A query needs >1 sub-agent (e.g. "compare X and Y, and what's the warranty policy") — expected once recommendation/comparison/policy agents exist | Phase 2+ |
| Vector Semantic Cache | Measured LLM cost/latency becomes a problem | Not triggered — revisit post-Phase 3 |
| Human-in-the-Loop (HITL) Intercept | Product requires a human fallback path | Not applicable — no human support queue exists in this project |
| Streaming (SSE/WebSocket) | A UI consumes this agent directly | **Trigger condition now met** (`app/ui/`, Phase 4a ✅, 2026-09-16) — still not built; the Streamlit UI works fully synchronously (a spinner while waiting), and streaming wasn't needed for a functional UI. Revisit only if response latency turns out to warrant it, per the Phase 4a implementation plan's Out of Scope note. |

---

## 9. Resiliency & Graceful Degradation

Phase 1 minimum: a per-call timeout on the OpenAI/PydanticAI call (avoid hanging indefinitely on a slow/stuck request) and a retry on rate-limit (`429`) errors only, matching the pattern already established for transient failures in `app/pipeline/persistence.py`'s `persist_batch_with_retry` (`tenacity`, exponential backoff+jitter — reusable here rather than hand-rolled).

Full circuit-breaker/fallback machinery (below) is **not** justified at Phase 1's scale (single in-process agent, no concurrent load) — defer to pre-launch hardening.

```
Coordinator Request ──► [Circuit Breaker: CLOSED] ──► Sub-Agent Execution
                              │
                              ├─► (Failures > N in window)
                              ▼
                      [Circuit Breaker: OPEN] ──► Graceful Fallback
```

| Control | Value | Roadmap phase |
| :--- | :--- | :--- |
| Sub-agent/LLM call timeout | 10s (generous default for a dev-stage LLM call; tune once real latency is measured) | Phase 1 — ✅ actually implemented in Phase 4b (2026-09-16), via `ModelSettings(timeout=...)` on all 5 agents; had been written down but not built until then |
| Retry on `429`/transient errors | `tenacity`, exponential backoff + jitter (reuse `persistence.py`'s pattern) | Phase 1 |
| Circuit breaker trip | Not built | Re-evaluated in Phase 4b (2026-09-16) — still not justified; the trigger condition ("single-process, no concurrent load") hasn't changed. Remains deferred, not skipped silently — see Appendix A |

---

## 10. Data Governance & Security

- **Input sanitization** ✅ implemented (2026-09-16): basic prompt-injection delimiter stripping and a length cap (`app/agents/sanitize.py::sanitize_query`, `MAX_QUERY_LENGTH=2000`) on the raw user query before it reaches the coordinator prompt, applied once in `handle_query`. Strips role/delimiter markers (`<|system|>`-style tokens, code fences, a line-start `system:`/`assistant:`/`developer:` prefix) — a deliberately "basic" measure, not a complete injection defense (no purely textual filter is). Verified via a code-review pass this had never actually been built despite this section committing to it "cheap to add now, do it in Phase 1" — see Appendix A.
- **PII redaction**: low priority for Phase 1 — the dataset is product/review/policy content, not customer PII, and there's no customer-data source in this project (Section 5). Revisit only if a customer-facing input field (e.g. a support ticket) is added later.
- **Credential handling**: `OPENAI_API_KEY` via `.env`/environment variable, matching the existing `SHOPENSEMBLE_DATABASE_URL` convention (`app/main.py`) — never hardcoded, never logged. A secrets manager is deployment-phase scope (Phase 4), not Phase 1. **RESOLVED (Phase 3b, 2026-09-16)**: the flagged risk was `app/agents/cli.py::main()`'s raw-exception-print pattern reaching an external caller if reused verbatim by the FastAPI layer. It was not reused — `app/api/main.py` has its own global `@app.exception_handler(Exception)` that logs the real error server-side and returns a generic `AgentErrorEnvelope` externally; `cli.py` itself is untouched (still fine for its own local-only use). Verified via a mocked contract test (`tests/api/test_query.py::test_query_never_leaks_a_raw_internal_exception_message`) asserting the raw message is absent from the response.

---

## 11. Telemetry, Tracing & Operational SLA

Deferred to Phase 3-4 (API/deployment phase) — no production SLA target exists for a capstone project pre-deployment. Phase 1 minimum: log each routing decision (Section 4) to stdout/a local log file, which is what Section 12's eval work will consume later.

**Real bug found and fixed in Phase 4b (2026-09-16)**: this "Phase 1 minimum" was never actually observable. No `logging.basicConfig`/level configuration existed anywhere in the project — Python's root logger defaults to `WARNING`, so every `logger.info(...)` call (the routing-decision log above, and this plan's new `llm_usage` cost log) was silently dropped in every real run of this project to date, including every "verified end-to-end" check in every prior phase's Implementation Notes. Found only by checking real server log output (Rule 9), not assumed from the code existing. Fixed with one `logging.basicConfig(level=logging.INFO, ...)` call in each of the 2 process entry points (`app/api/main.py`, `app/agents/cli.py`) — confirmed via a real run that both the routing-decision log and the new usage log now actually appear.

**Log persistence closed (2026-09-16)**: the "Phase 1 minimum" line above always said "stdout **or a local log file**" — only the stdout half was ever implemented (and, per the bug above, even that was silently broken until Phase 4b's fix). `app.agents.logging_setup.configure_logging()` now adds a `RotatingFileHandler` (5 MB × 3 backups per entry point) alongside the console handler, writing to `logs/cli.log` and `logs/api.log` respectively — verified for real by running both entry points and confirming real `llm_usage`/`routing_decision` lines land in the files, not just the console (`AGENTS.md` Rule 17).

| Metric | Collection mechanism | Target | Roadmap phase |
| :--- | :--- | :--- | :--- |
| Routing accuracy | Offline eval set (Section 12) | **≥80%** (observed baseline 2026-09-14: 27/29, 93.1%, `gpt-4o-mini` — see Appendix A) | Phase 3a ✅ |
| Total turn duration | APM/tracing tool | TBD | Phase 3+ |
| Token cost per turn | Real per-call `logger.info("llm_usage" ...)` via `app.agents.retry.call_with_retry`, using PydanticAI's own `AgentRunResult.usage`/`.cost` | ✅ Tracked (2026-09-16), no target yet | Phase 4b ✅ |
| Log persistence | `RotatingFileHandler` in `app.agents.logging_setup`, one file per entry point under `logs/` | ✅ Done (2026-09-16) | Phase 4b ✅ |

### Cost optimization strategy — technique applicability (evaluated 2026-09-15)

Per the spec template's cost-optimization-strategy guidance, the general techniques were walked against this project's actual architecture — **analysis only, per your scoping decision** (the requirement is Phase 4 / Production Readiness work, Section 13; nothing here is implemented yet). Verified directly against `app/agents/*.py` (2026-09-15): every one of the 5 production agents (coordinator + 4 sub-agents) already defaults to `model: ... = "openai:gpt-4o-mini"`; no `OpenAIEmbeddings`/`FAISS`/vector-store import exists anywhere in `app/`; no `ChatMessageHistory`/multi-turn memory exists anywhere — `handle_query()` is stateless, one query in, one response out.

| Technique | Applicable here? |
| :--- | :--- |
| Embedding-cost optimization (cheaper embedding model, persisting a vector index, multi-tenancy, hybrid search) | **Not applicable — no embedding/vector-store component exists.** This system has no semantic retrieval step (Section 12's Retrieval-relevance conclusion applies for the identical reason); there is nothing here to optimize the cost of. |
| Strategic model selection (don't default to the largest model) | **Already satisfied.** Every production agent already defaults to `gpt-4o-mini`, the cheaper of OpenAI's chat-capable models — no further model-tiering work is indicated. (The eval-only groundedness judge intentionally uses the pricier `gpt-4o` for grading reliability — a test-tool cost, not a production one; already justified in Appendix A.) |
| Memory-summarization optimization (`ConversationSummaryMemory`-style context capping) | **Not applicable yet — there is no multi-turn memory to summarize.** Each CLI/`handle_query()` invocation is a single stateless query; this technique would only become relevant if multi-turn conversational state is added, which is not currently planned. Revisit if that changes. |
| Caching frequently-repeated prompts/responses | **Applicable, not yet built.** A real, buildable technique (e.g. caching `policy_faq_agent` answers for repeated common questions, or `review_summary_agent` summaries per product) with no measured cost/latency problem driving it yet — deferred to Phase 4, consistent with Appendix B's existing "no vector semantic caching... not triggered by any measured cost/latency problem yet" entry for the same reason. |
| Continuous cost monitoring (track real per-turn token usage/cost) | **Applicable, not yet built.** This is exactly the gap the "Token cost per turn: Tracked, no target yet" row above already names — `handle_query()`'s existing `logger.info(...)` call logs the routing decision but no token/cost figures. Deferred to Phase 4 alongside the rest of this section's telemetry work. |

**Conclusion**: of the 5 general techniques, 1 doesn't apply to this architecture (no embedding component), 1 is already satisfied by the existing model defaults, 1 doesn't apply yet (no multi-turn memory), and 2 (caching, cost monitoring) are real, applicable gaps — both deferred to Phase 4 per the Roadmap (Section 13), not built now. Logged in Appendix A.

---

## 12. Required Test Suite & Evaluation

### Evaluation strategy — metric applicability (evaluated 2026-09-14)

Per the spec template's evaluation-strategy guidance, the 4 standard RAG/agentic eval metrics were walked against this project's actual architecture before building anything further:

| Metric | Compares | Needs ground truth? | Applicable here? |
| :--- | :--- | :--- | :--- |
| Correctness | response vs. reference answer | yes | **Already covered, deterministically** — every structured response field (`product_id`, `price`, `policy.timeframe`, `policy.policy_type`, matched IDs) has an exact, known-in-advance correct value from the CSV catalog; `test_golden_qa.py`'s hard field assertions are strictly stronger than an LLM-as-judge correctness pass over the same fields, and cheaper. Not worth adding as a separate LLM judge. |
| Relevance | response vs. input question | no | **Not needed as a separate check** — already implied by the routing-accuracy eval (right tool chosen) plus the golden Q&A shape assertions (right response type returned); an LLM-judge relevance pass on top would be redundant. |
| Groundedness | response vs. retrieved/source docs | no | **Applicable — a real, currently-unaddressed gap.** Every sub-agent's *structured* fields are hallucination-proof by construction (the reference-only output pattern, Section 3/Appendix A — the LLM only ever picks an ID/index, Python resolves the real record). But the **free-text** fields (`ReviewSummaryResponse.summary`, `RecommendationResponse.rationale`, `ComparisonResponse.differences`, `PolicyResponse.answer`) are LLM-synthesized prose that nothing currently checks against the real source records (review texts, picked products, matched policy) the sub-agent was shown. This is the one metric worth adding. |
| Retrieval relevance | retrieved docs vs. input question | no | **Not applicable — no retrieval step to score.** This system has no semantic/vector retrieval; sub-agents select candidates by exact lookup or structured filtering (`products_by_ids`, `filter_products`, `policies_by_type`) against the catalog, and the correct candidate set for any eval case is already known exactly from the CSV — covered deterministically by the existing golden Q&A field assertions, same reasoning as Correctness above. |

**Conclusion**: of the 4, only **Groundedness** is being added (see the [Phase 3a Part 2 groundedness spec](shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md)); the other 3 are either already covered by stronger deterministic checks or inapplicable to a non-RAG, structured-lookup architecture. Logged in Appendix A.

**Phase 1 (build now, test-first)**:
- Contract tests: `RoutingDecision`, `ReviewSummaryRequest`/`Response` reject invalid payloads (unknown `product_id`, wrong types) and accept valid ones.
- Routing test with a **mocked** PydanticAI/LLM response: a fixed-response fake model returns a known `RoutingDecision`, asserting the coordinator dispatches to the correct tool and constructs the right error envelope on a schema violation. No real OpenAI calls in unit tests — matches the mocking policy already used in `tests/pipeline/test_persistence.py`.
- Generate these using the project's standard test-generation workflow, presenting the test plan before generation, per this project's existing convention.

**Phase 3a (implemented 2026-09-14)** ✅:
- Routing-accuracy eval set: `(query, expected_sub_agent)` pairs, run against the real LLM (not mocked) to measure the Section 11 accuracy metric — `tests/agents/eval/test_routing_accuracy.py`, 29 cases, aggregate `≥80%` assertion.
- Golden Q&A regression set per sub-agent, especially policy/FAQ (`specs/shopensemble-project-requirements.md` Section 9 calls this out explicitly) — `tests/agents/eval/test_golden_qa.py`, 6 named cases including both Phase 2 known-bug regressions.
- Both opt-in via a new `eval` pytest marker (`OPENAI_API_KEY`-gated, never part of the default `-m "not integration and not eval"` run) — see [Phase 3a implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-eval-implementation-plan.md).

**Phase 3a Part 2 (groundedness evaluator, implemented 2026-09-14)** ✅:
- The one applicable metric from the evaluation-strategy analysis above — see the [spec](shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md) for the full narrative and Gherkin scenarios and the [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-part2-groundedness-implementation-plan.md) for the concrete build and real bugs found. Extends `test_golden_qa.py`'s 6 existing cases with an additional groundedness assertion each (`tests/agents/eval/groundedness.py`), rather than a parallel eval set. Judge model: `gpt-4o` (stronger than the `gpt-4o-mini` every sub-agent uses — a judge needs to grade multi-item comparative claims reliably), `temperature=0`.

Durable log: append results to `.agents/memory-bank/testGenerationLog.md`, following the existing `v1`-`v6` convention (Phase 3a's routing-accuracy/golden-Q&A work is the `v6` entry; Phase 3a Part 2's groundedness work is the `v7` entry).

---

## 13. Roadmap / Phase Mapping

| Sections | Capability | Phase | Status |
| :--- | :--- | :--- | :--- |
| 3 (review agent only), 4, 6, 7, 12 (contract tests) | Coordinator + review-summarization agent, first tool | **Phase 1 — Foundation** | ✅ Implemented (2026-09-13) — `app/agents/`, 26/26 tests passing, verified end-to-end against the real OpenAI API |
| 3 (remaining 3 sub-agents), 8 (scatter-gather) | Recommendation, comparison, policy/FAQ agents | **Phase 2 — Expansion** | 🔶 Partially implemented (2026-09-14) — all 3 sub-agents shipped, single-dispatch; scatter-gather (Section 8) still ⏳ Planned, deliberately deferred |
| 12 (eval harness + tuning), 1 (API layer) | Evaluation dataset/script, prompt tuning, FastAPI query routing | **Phase 3 — Validation & Integration** | ✅ Implemented (2026-09-16) — Phase 3a eval harness (`tests/agents/eval/`, 7/7 passing against the real API, including groundedness) and Phase 3b FastAPI layer (`app/api/`, `GET /health`/`POST /query`, contract-tested) both shipped. Prompt tuning stayed conditional per its own trigger (a systematic misrouting pattern) — the observed 93.1% baseline never revealed one, so none was done |
| 8 (streaming), 9, 10, 11 (hardening), UI | Streamlit/Gradio UI, scalability checks, resiliency/security/telemetry for production | **Phase 4 — Production Readiness** | ✅ Implemented (2026-09-17) — **Phase 4a (UI)** shipped (`app/ui/`, 5 workflows, 28/28 contract tests — see [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4a-ui-implementation-plan.md)); **Phase 4b (backend hardening)** shipped (rate limiting, caching, cost/telemetry logging, the Section 9 timeout gap, and a real logging-config bug found along the way — 16/16 new/extended contract tests, verified end-to-end against the real OpenAI API — see [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4b-backend-hardening-implementation-plan.md)); **Phase 4c (catalog browse)** shipped — a new, additive `GET /products` route and a Browse Catalog page that **replaces the chat assistant as the app's home page** (chat relocated to a regular sidebar page), a real gap surfaced live in conversation (no way to discover what the store carries without already knowing a product ID) rather than a written requirement — see [spec](shopensemble-coordinator-agent-phase4c-catalog-browse-spec.md) and [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md). Only scatter-gather/composite routing (Section 8) remains unimplemented project-wide |
| Phase 5 — 5 (session memory), 3 (multi-entity review cardinality), 4 (reference resolution), 8 (product-ID visibility) | Conversation memory for the Chat Assistant, multi-product review summaries, product ID on every product card | **Phase 5 — Conversational Context** | ✅ Implemented (2026-09-26) — 238 fast + 11 integration + 11 eval tests; routing accuracy 100 % (39/39, up from the 93.1 % baseline); verified live against the real OpenAI API. See the [Phase 5 spec](shopensemble-coordinator-agent-phase5-session-memory-spec.md) and [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase5-session-memory-implementation-plan.md). Scatter-gather (Section 8) is still the one unbuilt capability |
| Phase 6 — extends 4 (superlative cardinality), 5 (last_product_ids), 9 (evaluate_products_agent) | Deterministic bare-reference resolution; judging products already shown (cheapest/highest-rated/best) without a fresh search | **Phase 6 — Focus-Scoped Follow-Ups** | ✅ Implemented (2026-09-26) — [spec](shopensemble-coordinator-agent-phase6-focus-followups-spec.md), [plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase6-focus-followups-implementation-plan.md); 261/11/13 tests, routing accuracy 100% (42/42); also fixed a found bug (`RoutingDecision.extracted_max_price` blank-string crash) and a found gap (unbounded recommendations vs. memory's 10-product cap) |
| Phase 7 — extends 4 (chitchat short-circuit) | Deterministic greeting reply (no LLM call) and consistent, capability-describing wording for every unresolved response | **Phase 7 — Greeting & Fallback Wording** | ✅ Implemented (2026-09-27) — [spec](shopensemble-coordinator-agent-phase7-greeting-fallback-spec.md), [plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase7-greeting-fallback-implementation-plan.md); 273/11/14 tests, routing accuracy unchanged at 100% (42/42) |

See the phase-to-course-milestone table at the top of this document for how these map to the project's actual weekly schedule.

---

## 14. Acceptance Criteria (pre-build gate)

- [x] Section 1 discovery questions answered.
- [x] Section 2 pattern selected with justification tied to actual capstone requirements.
- [x] Section 3 registry lists every Phase 1-in-scope sub-agent with input/output schemas.
- [x] Section 4 confidence source concretely specified (PydanticAI structured-output field).
- [x] Section 5 session-identity contract defined (and long-term memory explicitly marked out of scope).
- [x] Section 12 mocking policy and draft eval set exist before agent code is written — **mocking policy defined here and applied (PydanticAI `TestModel`); eval set itself is Phase 3, not a Phase 1 blocker**.
- [x] Appendix A has no open rows relevant to Phase 1.
- [x] Appendix B is filled in.

---

## 15. Production Verification Checklist (post-build gate — apply once Phase 1 code exists)

- [x] Substring/keyword matching eliminated in favor of semantic (PydanticAI structured-output) classification.
- [x] Strict schemas enforced on the coordinator ↔ review-agent boundary.
- [x] OpenAI client and in-memory dataset injected as singletons, not re-instantiated per call (`app/agents/cli.py` builds each once).
- [x] Timeout + retry-with-backoff configured on the LLM call (`app/agents/retry.py`, mirrors `persist_batch_with_retry`).
- [x] Contract tests pass (Section 12, Phase 1 subset) — 26/26 in `tests/agents/`.
- [x] Routing decisions are logged (`coordinator.py::handle_query`, `logging.getLogger(__name__).info(...)`).

---

## Appendix A: Decision Log

| Decision | Options considered | Selected option | Reason | Date |
| :--- | :--- | :--- | :--- | :--- |
| Agent framework (resolves project requirements Open Decision #4) | PydanticAI, LangChain, custom (OpenAI SDK + Pydantic) | **PydanticAI** | Matches the course curriculum's own introduction of PydanticAI; native structured-output support makes Section 4's confidence field straightforward; consistent with the strict-Pydantic-v2 style already in `app/models.py` | 2026-09-13 |
| Architecture pattern | A (router), B (supervisor), C (ReAct) | **B — Supervisor/Orchestrator** | Capstone requires composite cross-domain queries (comparison + policy + reviews in one turn) | 2026-09-13 |
| Confidence source | Self-reported structured-output field, embedding cosine similarity, logprob of tool call | **Self-reported field on `RoutingDecision`** | Simplest mechanism natively available in PydanticAI; revisit after Phase 3 eval if miscalibrated | 2026-09-13 |
| Phase 1 sub-agent data access | Read CSV in-memory vs. query the Postgres persistence layer | **CSV in-memory** | Matches the Phase 1 milestone notebook's explicit description; Postgres wiring is a later, separate decision | 2026-09-13 |
| Dispatch mechanism | PydanticAI native `@agent.tool` auto-calling vs. manual dispatch after a structured-output classification call | **Manual dispatch** | Native tool-calling is binary (called/not-called) with no continuous confidence to threshold against; the Section 4 confidence gate must decide *whether* a sub-agent runs at all, before it runs — only a prior structured-output call allows that. `RoutingDecision` gained `extracted_product_id` to carry the one argument Phase 1's sub-agent needs, extracted in the same call that classifies intent. Phase 2 (multiple sub-agents, different argument shapes) will need to generalize this field. | 2026-09-13 (implementation) |
| Confident "none" handling | Treat as an `unknown_tool` error vs. a normal fallback | **Fallback, not error** | Caught during manual smoke-testing: a high-confidence `RoutingDecision(chosen_tool="none")` is the model correctly reporting no registered sub-agent covers the query (e.g. a policy question, before `policy_faq_agent` exists in Phase 2) — a normal, expected outcome, not a routing defect. `AgentError(code="unknown_tool")` is kept only as a defensive branch for future schema drift. | 2026-09-13 (implementation) |
| Phase 2 extraction generalization | Flat optional fields on `RoutingDecision` vs. a second classify-then-extract LLM call | **Flat optional fields** (`extracted_product_ids`, `extracted_max_price`, `extracted_category`, `extracted_policy_type`) | Continues Phase 1's one-call classify+extract pattern; a second round-trip per dispatched query would add latency/cost for no clear benefit at this scale | 2026-09-14 |
| `handle_query` signature growth | Keep growing individual sub-agent parameters vs. a `SubAgents` container | **`SubAgents` dataclass** (one parameter) | 4 sub-agents would mean 4+ positional params; a container stays stable as more sub-agents are added in later phases | 2026-09-14 (implementation) |
| Sub-agent output reconstruction | Let the LLM directly output the public `*Response` schema (full `Product`/`StorePolicy` objects) vs. a reference-only internal type Python resolves | **Reference-only** (`RecommendationPick`, `ComparisonAnalysis`, `PolicyAnswer` — product IDs or a numbered-list position, never full records) | The model was never shown every field it would need to reconstruct (e.g. `Product.stock`), risking fabrication; a first version of `policy_faq_agent` asking for a free-text description echo was found (via manual smoke testing) to unreliably match — the model echoed the whole formatted candidate line, not just the description. Switched to an unambiguous 1-based index. | 2026-09-14 (implementation) |
| Recommendation category matching | Trust the LLM-extracted `extracted_category` exactly vs. tolerate near-misses | **Tolerate near-misses** — `filter_products` falls back to a case-insensitive, trailing-`s`-stripped comparison if the exact value doesn't match | Manual smoke testing surfaced a real miss: the coordinator extracted `"speakers"` (plural) against the catalog's exact `"speaker"`, silently returning zero candidates. Fixed the coordinator prompt to state the 4 exact category values *and* added this fallback as defense-in-depth against future near-misses. | 2026-09-14 (implementation) |
| Routing-accuracy failure counting | Let `agent.run()` propagate an `UnexpectedModelBehavior` (structured-output retry exhaustion) vs. count it as a routing miss | **Count as a miss** | Observed for real during the Phase 3a baseline run — a live LLM call occasionally fails PydanticAI's own output-validation retry loop, independent of whether the classification itself would have been correct; the eval harness measures real-world reliability, so an unguarded exception crashing the whole aggregate test would understate the failure mode rather than report it | 2026-09-14 (implementation) |
| Routing-accuracy threshold | Assert against the exact observed baseline vs. a threshold with headroom below it | **Headroom below baseline** — 93.1% observed (27/29) → 80% asserted | No prior baseline existed to set a threshold before implementation (per this plan's own design note); running for real once and asserting with margin tolerates normal LLM run-to-run variance on a 29-case set without going flaky, while still catching a real regression | 2026-09-14 (implementation) |
| Evaluation metric: Correctness (response vs. reference) | Add as a separate LLM-as-judge pass vs. rely on existing deterministic field assertions | **Not applicable — already covered, more strongly, deterministically** | Every structured field's exact correct value is known in advance from the CSV catalog; a hard equality assertion (`test_golden_qa.py`) is stronger and cheaper than an LLM judge scoring the same fields | 2026-09-14 |
| Evaluation metric: Relevance (response vs. input) | Add a standalone LLM-as-judge relevance pass | **Not applicable — redundant** | Already implied by the routing-accuracy eval (right tool chosen) and the golden Q&A shape assertions (right response type returned); no concrete gap it would catch | 2026-09-14 |
| Evaluation metric: Groundedness (response vs. source docs) | Skip vs. add as a new evaluator | **Applicable — adding it** | The reference-only output pattern makes every *structured* field hallucination-proof, but the free-text fields (`summary`, `rationale`, `differences`, `answer`) are LLM-synthesized prose nothing currently checks against the real source records shown to the sub-agent — a genuine, unaddressed gap. See [Phase 3a Part 2 groundedness spec](shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md) | 2026-09-14 |
| Evaluation metric: Retrieval relevance (docs vs. input) | Add an LLM-as-judge retrieval-relevance pass | **Not applicable — no retrieval step exists** | This system has no semantic/vector retrieval; candidates are selected by exact lookup/structured filtering, and the correct candidate set is already known exactly from the CSV and hard-asserted, same reasoning as Correctness above | 2026-09-14 |
| Groundedness judge model | `gpt-4o-mini` (matching every sub-agent) vs. a stronger model | **`gpt-4o`, `temperature=0`** | Real repeated test runs showed `gpt-4o-mini` grading itself was inconsistent on multi-item numeric/comparative claims — flagging factually-supported "most affordable" claims as ungrounded, with internally inconsistent reasoning in its own explanation. Matches the reference RAG-evaluation notebook's own design (a stronger model grades even when a cheaper one generates); justified since the judge runs only a handful of times per suite run | 2026-09-14 (implementation) |
| Groundedness facts for multi-candidate cases | Pass only the picked products as facts vs. the full candidate list with picks marked | **Full candidate list, picks marked `[SELECTED/RECOMMENDED]`** | Caught via repeated real runs: a comparative rationale claim ("the selected products are the most affordable") is unverifiable to the judge unless it knows *which* of the shown candidates were actually picked — this, more than further prompt tuning, resolved the recommendation cases' remaining flakiness | 2026-09-14 (implementation) |
| Cost technique: Embedding-cost optimization | Build vs. skip | **Not applicable — no embedding/vector-store component exists in this architecture** | Verified directly against `app/agents/*.py`: no `OpenAIEmbeddings`/`FAISS`/vector-store import exists anywhere; candidates are selected by exact CSV lookup/filtering, same non-RAG reasoning as the Section 12 Retrieval-relevance conclusion | 2026-09-15 |
| Cost technique: Strategic model selection | Audit vs. skip | **Already satisfied — no change needed** | All 5 production agents (coordinator + 4 sub-agents) already default to `gpt-4o-mini`; verified directly against source, not assumed | 2026-09-15 |
| Cost technique: Memory-summarization optimization | Build vs. skip | **Not applicable yet — no multi-turn memory exists** | `handle_query()` is stateless (one query in, one response out); this technique has nothing to act on until multi-turn conversational state is added, which isn't currently planned | 2026-09-15 |
| Cost technique: Caching frequently-repeated prompts/responses | Build now vs. defer | **Applicable, deferred to Phase 4** | A real, buildable technique, but not triggered by any measured cost/latency problem yet — same reasoning already used in Appendix B for ruling out vector semantic caching | 2026-09-15 |
| Cost technique: Continuous cost monitoring (token usage/cost per turn) | Build now vs. defer | **Applicable, deferred to Phase 4** | This is the existing "Token cost per turn: Tracked, no target yet" gap in the table above — `handle_query()` logs the routing decision but not token/cost figures; bundled with the rest of Section 11's telemetry work rather than built in isolation now | 2026-09-15 |
| Prompt-injection input sanitization (Section 10) | Build now vs. defer to Phase 4 hardening | **Build now — the spec already committed to this in Phase 1** | A manual code-review security pass over `app/agents/` (2026-09-16, `AGENTS.md` Rule 13) found this section's own stated Phase 1 requirement had never actually been implemented — confirmed via a repo-wide grep for any sanitization/delimiter logic, none existed. Unlike the Phase-4-deferred cost techniques above, this wasn't a new decision to make, just a promised-but-unbuilt gap to close | 2026-09-16 (implementation) |
| Free-text query/question field length bound | Add `max_length` now vs. rely on the new sanitizer's truncation alone | **Add `max_length=2000` at the schema level too** | Same review surfaced `RecommendationRequest.query`/`PolicyRequest.question` as the only 2 free-text fields in `app/agents/models.py` with no upper bound, unlike every response field (capped at 1000). Defense-in-depth: a future caller that constructs these models directly (bypassing `handle_query`'s sanitizer) is still protected at the schema boundary | 2026-09-16 (implementation) |
| Phase 3b module layout | A single `app/api.py` vs. a package split by concern | **`app/api/` package** — `main.py` (app + lifespan + error handler), `dependencies.py` (injectable `AppState`), `schemas.py` (the one new `QueryRequest`), `routes.py` (endpoints) | Matches `shopensemble-project-requirements.md` Section 5's own recommended boundary, and this project's established one-concern-per-file granularity (`app/agents/` already splits `retry.py`/`data.py`/`sanitize.py`/per-sub-agent files rather than one large module) | 2026-09-16 (implementation) |
| Phase 3b response schema for `POST /query` | Define a new API-specific response model vs. reuse `CoordinatorResponse` | **Reuse `CoordinatorResponse` directly** (`response_model=CoordinatorResponse`) | It's already the exact 7-member union `handle_query()` returns; a second, API-only response schema would just be a lifecycle-free duplicate with no behavior difference — unlike the request side, where `QueryRequest` genuinely differs in lifecycle from the internal `*Request` models per the spec's own instruction | 2026-09-16 (implementation) |
| Phase 3b DI/testability mechanism | Read `request.app.state` directly in routes vs. a `Depends`-based provider | **`Depends(get_app_state)`** (`app/api/dependencies.py`) | Only the `Depends` indirection lets contract tests swap in `TestModel`-built agents via `app.dependency_overrides` — reading `app.state` directly in each route would have no clean override point, forcing either a real API key in tests or a different, second mocking mechanism from the rest of the project | 2026-09-16 (implementation) |
| Phase 3b test framework internals | Assumed `TestClient.raise_server_exceptions` was mutable post-construction | **Constructor-only in this pinned Starlette version (1.6.0)** — verified by testing both ways, not assumed | The one internal-error contract test needed its own `TestClient(app, raise_server_exceptions=False)` instance rather than reusing the shared fixture's client; every other test intentionally keeps the default (an unhandled route bug should fail the test, not be silently swallowed) | 2026-09-16 (implementation) |
| Phase 4a UI ↔ backend coupling | Import `app.agents`/`app.api` in-process vs. call `app/api/` over real HTTP | **Real HTTP, via `httpx`** | Bypassing the API layer in-process would duplicate Phase 3b's singleton-building logic and defeat the entire reason that layer was built; running the full stack costs 2 processes (`uvicorn` + `streamlit run`) in exchange for a genuinely layered architecture | 2026-09-16 (implementation) |
| Phase 4a response rendering | One render function per page vs. one shared dispatcher | **One shared `render_coordinator_response()`, dispatching on which JSON keys are present** | The UI only ever sees JSON (no discriminator field on the 7-member `CoordinatorResponse` union) — each of the 7 shapes has an unambiguous distinguishing key (`sentiment`, `rationale`, `differences`, `policy`, `question`, `message`, `error`); one shared function keeps every workflow rendering a given response type identically instead of 5 near-duplicate implementations | 2026-09-16 (implementation) |
| Phase 4a git tracking scope | Exclude `app/ui/`/`tests/ui/` like `app/agents/`/`app/api/`, or track it | **Track it** | Unlike `app/api/`, the UI has no import coupling to the untracked `app/agents/` internals — it only calls a documented HTTP API, so nothing breaks if it's public. Confirmed with the user before implementation | 2026-09-16 (implementation) |
| Phase 4b timeout mechanism | `ModelSettings(timeout=...)` per agent vs. an `asyncio.wait_for()` wrapper in `call_with_retry` | **`ModelSettings`** | Same mechanism `groundedness.py` already uses for `temperature=0` — one line per `build_*_agent()`, no change to the generic `call_with_retry` helper, and it's PydanticAI's own supported timeout surface rather than a hand-rolled wrapper around it | 2026-09-16 (implementation) |
| Phase 4b cost-logging hook point | Thread token/cost logging through each of the 6 call sites individually vs. one shared hook | **`call_with_retry` itself**, via an optional `label` param and `getattr(result, "usage", None)` | Every LLM call in the codebase already goes through this one function — reusing it gives Section 11's "Token cost per turn" real data for every sub-agent (plus the eval groundedness judge) for the cost of one parameter, without touching each dispatch function's own logic | 2026-09-16 (implementation) |
| Phase 4b caching placement and testability | Cache inside `handle_query()` vs. at the API route only; direct singleton vs. `Depends`-injected | **API route only, `Depends(get_query_cache)`** | Caching is a "serving repeated HTTP requests" concern — the CLI is a fresh process per call, so an in-memory cache there would never persist between invocations, and `handle_query()`'s signature stays untouched for every existing caller. `Depends`-injecting the cache (mirroring `get_app_state`) is what let contract tests use a fresh instance per test instead of leaking cached responses across unrelated tests sharing a query string — caught by a real test failure, not designed in upfront | 2026-09-16 (implementation) |
| Phase 4b rate-limiting approach | Hand-rolled fixed-window limiter vs. adding `slowapi` | **Hand-rolled** | The actual logic needed at this scale (single-process, in-memory, no numeric target in either spec) is small enough that a library wouldn't meaningfully reduce code; `slowapi`+Redis remains the documented fallback if a distributed deployment ever exists | 2026-09-16 (implementation) |
| Phase 4b circuit breaker | Build now (Phase 4 was the explicitly-named re-evaluation point) vs. defer again | **Defer again, explicitly re-evaluated, not silently skipped** | The original trigger condition ("single-process, no concurrent load") still holds — nothing about this project's deployment scale changed between Phase 1 and now | 2026-09-16 (implementation) |
| Phase 4b logging visibility | Assume `logger.info(...)` calls were already working (they'd existed since Phase 1) vs. verify | **Verify — and they weren't** | Real server log output during Phase 4b's own verification showed zero `llm_usage`/`routing_decision` lines despite the code being correct; root cause was a project-wide missing `logging.basicConfig` — Python's root logger defaults to `WARNING`. Fixed in both process entry points (`app/api/main.py`, `app/agents/cli.py`); this had silently affected every prior phase's "routing decisions are logged" claim, not just this one | 2026-09-16 (implementation) |
| Log persistence (post-Phase-4b follow-up) | Console-only (as Phase 4b left it) vs. also persist to a file | **Also persist — `RotatingFileHandler` per entry point via `app.agents.logging_setup.configure_logging()`** | Console-only logging is exactly the "looks done, isn't durable" gap Rule 9 exists for — lines vanish with the terminal's scrollback. Small rotation caps (5 MB × 3 backups) chosen over unbounded append or a full log-aggregation setup, proportionate to this capstone's single-process scale; codified as `AGENTS.md` Rule 17 so future entry points follow the same pattern automatically | 2026-09-16 (implementation) |
| Phase 4c catalog data path | Route "list all products" through the coordinator/LLM (as every other workflow does) vs. a plain direct data endpoint | **Direct — `GET /products`, no LLM call** | Browsing 2,000 real products is a data read, not a classification-and-generation task; routing it through `handle_query()` would spend real tokens/latency for nothing gained, and an LLM call couldn't even guarantee returning the true full list deterministically. Same class of decision as `/health` already staying outside the coordinator path. Verified for real: browsing/filtering against a live server produced zero new `llm_usage` log lines | 2026-09-17 (implementation) |
| Phase 4c home page | Catalog as an additional 6th page vs. replacing the chat assistant as the app's home page | **Replace — chat assistant relocates to `app/ui/pages/5_💬_Chat_Assistant.py`** | Settled directly with the user during planning (an explicit alternative was offered and not chosen); the catalog is the one page with no "already know what to ask" assumption, so it's the more natural first thing a new user sees. Chat's own logic (transcript, dispatch) is unchanged, only relocated | 2026-09-17 (implementation) |
| Phase 4c interactivity scope | Per-row "Review Summary"/"Add to Compare" actions with cross-page `session_state` prefill (`st.switch_page`) vs. a plain filterable table | **Plain table only — explicitly declined** | Proposed as concrete options during planning; the user explicitly ruled them out ("not on the catalog... user will copy item and check in chat window or move to a specific page"). Recorded here so a future revisit starts from "deliberately declined," not "never considered" | 2026-09-17 (implementation) |
| Phase 4a `streamlit run` sys.path gap (post-Phase-4a follow-up, user hit it directly) | Assume the documented `streamlit run app/ui/streamlit_app.py` command worked (Phase 4a claimed "real end-to-end verification") vs. verify the literal command itself | **Verify — and it didn't.** Fixed by inserting the project root onto `sys.path` at the top of `streamlit_app.py` and every `app/ui/pages/*.py` file | Confirmed via the installed `streamlit` package's own `web/bootstrap.py::_fix_sys_path` source: `streamlit run` puts only the target script's own directory on `sys.path`, never the project root. `AppTest` — the tool behind every "real end-to-end verification" claim in Phase 4a — does no `sys.path` manipulation of its own; it silently inherited the project root only because `pytest` is always invoked from there. The literal CLI command had never actually been exercised until the user ran it directly. Same class of finding as the Phase 4b logging-visibility gap above: a test harness's own blind spot had let something "verified" go unexercised in its real, documented form | 2026-09-16 (implementation) |

## Appendix B: Out-of-Scope / Non-Goals

- **Long-term customer memory / persisted profile** — no customer-identity or order-history system exists in this project.
- **Human-in-the-Loop escalation** — no human support queue exists to escalate to.
- **Vector semantic caching** — not triggered by any measured cost/latency problem yet.
- **Streaming responses (SSE/WebSocket)** — no UI consumes this agent yet (Phase 4).
- **Circuit breakers / production resiliency hardening** — not justified at Phase 1's single-process, no-concurrent-load scale.
- **PII redaction pipeline** — no customer-PII data source exists; the datasets are catalog/review/policy content.
- **Production secrets manager** — `.env`/environment variables are sufficient pre-deployment (Phase 4 revisits this).

---

**Version**: 1.0
**Last Updated**: 2026-09-17 (Phase 4c)
