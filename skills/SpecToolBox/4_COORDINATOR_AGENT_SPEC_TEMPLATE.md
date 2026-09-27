# Conversational Coordinator Agent Specification Template

## Overview
This template provides a reusable, full-maturity specification framework for a coordinator/orchestrator agent that routes conversational queries to specialized sub-agents. Use it for any project where a single entry-point agent must classify intent, dispatch to domain agents, and return a synthesized response.

**Write every section at full target maturity, even for an early-stage project.** Don't fork this into a per-phase or per-week file — fill in Section 14 (Roadmap) to say what's built now vs. later, and update the rest of the document *in place* as the project matures. A spec that accumulates `-v2`/`-phase2` copies is harder to trust than one authoritative document with an honest status column (this mirrors how `specs/1_data-pipeline/shopensemble-implementation-guide.md` was updated in place as its own phases shipped, rather than split into new files).

### Required workflow
1. Fill in every `{{PLACEHOLDER}}` and `[bracket]` field before treating this as approved.
2. Resolve every row in Appendix A (Decision Log) — a spec with open decisions isn't ready to build from.
3. Get sign-off against Section 15 (Acceptance Criteria) *before* implementation starts — this is the approval gate, distinct from Section 16's post-build verification checklist.
4. As work progresses, update Section 14's status column in place. Do not create a new file per phase/week.

### Adding a capability after the first spec exists (e.g. session memory, a new sub-agent family)
Fold any *analysis* ("which of these techniques apply to us") into the living spec in place — Decision Log rows, not a new file. Only when the analysis concludes that something concrete must be **built** does it get its own feature-named spec + a mirrored implementation plan (e.g. `specs/2_coordinator-agent/{{project}}-coordinator-agent-phase5-session-memory-spec.md` ↔ `plans/2_coordinator-agent/…-implementation-plan.md`), cross-linked from the living spec's header, Section 5/14 pointers, and Appendix A. Name the pair for the feature, not just the phase number. Before writing it, **reproduce the reported failure against the running system** and quote what actually happened — a spec drafted from a code read alone missed a second, independent gap (see Section 3's cardinality note).

### Naming example
Template → `specs/{{project}}-coordinator-agent-spec.md`

---

## Table of Contents
1. Meta and Scope
2. Architecture Pattern Selection
3. Sub-Agent Registry & Tool Contract
4. Routing & Intent Classification
5. State Management & Memory Hierarchy
6. Schema Typing & Validation
7. Dependency Injection & Resource Lifecycle
8. UI Design & Frontend Integration
9. Cognitive Features (Tier 2)
10. Resiliency & Graceful Degradation
11. Data Governance & Security
12. Telemetry, Tracing & Operational SLA
13. Required Test Suite & Evaluation
14. Roadmap / Phase Mapping
15. Acceptance Criteria (pre-build gate)
16. Production Verification Checklist (post-build gate)
17. Appendix A: Decision Log
18. Appendix B: Out-of-Scope / Non-Goals

---

## 1. Meta and Scope

| Field | Value |
| :--- | :--- |
| Document Version | `{{MAJOR.MINOR.PATCH}}` |
| System ID / Code Name | `{{e.g. ORCH-COORD-PROD}}` |
| Lead System Architect | `{{Name / Title}}` |
| Runtime Target | `{{e.g. Python 3.11+, PydanticAI}}` |
| Deployment Topology | `{{e.g. local dev, ECS Fargate, Cloud Run}}` |
| LLM Provider(s) + Model(s) | `{{e.g. OpenAI gpt-4o-mini, fallback: none yet}}` |

### Required discovery before implementation
- What domains/sub-agents exist at launch, and which are planned but not yet built?
- What is the expected query volume (QPS) and acceptable end-to-end latency?
- Does an evaluation dataset already exist, or does one need to be authored (see Section 13)?
- Is this agent reachable only in-process/CLI today, or does it sit behind an API (FastAPI, etc.)? If the API doesn't exist yet, say so explicitly rather than assuming it.
- Is every turn handled in isolation, or must a follow-up like *"review both of those"* / *"what about under $500?"* work? If multi-turn, Section 5 must be filled at full depth (identity, what is remembered, bounds, lifetime, isolation) and Sections 3, 4, 8, 11, 13 each carry a multi-turn item — do not leave "stateless" as an unexamined default.
- Is a UI in scope for the current roadmap milestone (Section 14)? If yes, read Section 8 **before** building any page — several real issues below were caught only after pages already existed and had to be patched, not designed in from the start.

---

## 2. Architecture Pattern Selection

Select and justify one operational pattern:

| Pattern | Characteristics | Best for |
| :--- | :--- | :--- |
| **A. Pure Semantic Router** | Single-turn intent classification, zero local computation, direct handoff to a leaf agent | High-throughput, stateless Q&A |
| **B. Supervisor / Orchestrator (Hierarchical)** | Dispatches to multiple worker agents, evaluates outputs, synthesizes final response | Composite requests spanning >1 domain |
| **C. ReAct / Dynamic Planner Loop** | Chain-of-thought + scratchpad to plan step-by-step tool use | Open-ended diagnostic/multi-step paths |

**Selected pattern**: `{{A / B / C}}`
**Justification**: `{{why this pattern fits the product requirement, not just architectural preference}}`

---

## 3. Sub-Agent Registry & Tool Contract

Every sub-agent the coordinator can dispatch to must be declared here **before** Section 4's routing logic can be implemented — this is what the coordinator classifies against.

| Sub-agent | Trigger intents / example queries | Input schema | Output schema | Data/tools it owns |
| :--- | :--- | :--- | :--- | :--- |
| `{{sub_agent_name}}` | `{{e.g. "summarize reviews for X"}}` | `{{PydanticModel}}` | `{{PydanticModel}}` | `{{e.g. reviews.csv}}` |

**Tool-calling convention**: `{{e.g. PydanticAI @agent.tool, function name = sub-agent name, docstring = routing description}}`

**Input cardinality — declare it per sub-agent (1 entity, or N up to a stated cap), and check it against the follow-ups Section 5 promises.** A sub-agent that takes exactly one entity cannot serve "summarize reviews of *both* of them"; the router then silently picks the *closest* tool that accepts a list (a comparison agent, say) and returns a confidently wrong answer. If N-entity requests are plausible, give the sub-agent an N-entity input with a hard cap (bounds cost per request), a separate response type with its own distinguishing key, a defined all-or-nothing rule for one bad entity, and request-order results.

---

## 4. Routing & Intent Classification

**Probabilistic/semantic routing only** — reject hardcoded string/keyword matching. Routing must use LLM function-calling, structured-output classification, or vector similarity against the Sub-Agent Registry (Section 3).

**Confidence source**: `{{how is C computed? e.g. a `confidence: float` field the coordinator's structured output is required to populate; or cosine similarity to an intent-bank embedding; or logprob of the selected tool call}}` — this must be answered concretely; "the LLM decides" is not an implementation.

| Confidence range (`C`) | Route action | Default threshold |
| :--- | :--- | :--- |
| `C ≥ τ_exec` | Direct sub-agent dispatch | `{{0.75}}` |
| `τ_clarify ≤ C < τ_exec` | Clarification / disambiguation turn | `{{0.50}}` – `{{0.75}}` |
| `C < τ_clarify` | Global fallback / human escalation | `< {{0.50}}` |

Log every routing decision (chosen sub-agent, `C`, and the action taken) — this is the input to Section 13's routing-accuracy evaluation.

### Chitchat/greetings and the wording of every "couldn't help" message

- **Detect pure chitchat deterministically, before classification — no LLM call for the one obviously correct reply.** A bare greeting ("hi", "hello", "how are you", "good morning") has exactly one sensible response; spending a classification call on it (and accepting whatever variance that call produces) buys nothing. Check it with a narrow, literal rule — e.g. every word in the message belongs to a small fixed greeting/pleasantry vocabulary, with at least one real greeting word present — so a message that also asks something real ("hi, do you have laptops under $500?") is never swallowed: any word outside that vocabulary means it is NOT pure chitchat and goes through classification normally. This is the same "deterministic first when one answer is provably correct" principle as Section 9's cost-optimization guidance, applied to UX rather than money.
- **Every "couldn't help" message should say what the system CAN do, not only that it can't.** A generic "I'm not sure how to help with that" reads as broken; a customer can't tell from it whether to rephrase, try a different topic, or give up. Give every such case — low confidence, a confident "none", and (if built) a chitchat reply — a consistent capability-describing line, built from ONE shared string so a future wording change is made once, not in N places. Render this class of response in a neutral/informational style, not a warning/error style, once it states a positive next step rather than only an apology — a visual "something went wrong" cue on a message that says "here's what I can help with" undersells it.
- **A real user-reported gap, not a hypothetical one**: found live in an otherwise-working coordinator (ShopEnsemble Phase 7) — "HI how are you you" and "tell me a joke" both hit the exact same terse fallback line a genuine failure would, with no way for the customer to tell the difference.

### Reference resolution (multi-turn systems only)

- **The coordinator resolves references; sub-agents stay stateless.** Pronouns/ordinals/attributes ("both", "them", "the first one", "the cheaper one", "it") are turned into explicit identifiers *before* dispatch, from a rendered context block plus the current message. No sub-agent contract changes, and existing sub-agent tests stay valid.
- **The current message wins** over context on any conflict or topic change; context only fills gaps. Refinements ("what about under $500?") inherit earlier stated constraints.
- **Unresolvable → ask, don't guess**: return low confidence + a clarification question so it flows through the existing confidence gate above — no new response type.
- **Deterministic guard — don't trust the model with identifiers**: for every *conversational* request, the model must have extracted enough identifiers for the chosen tool, and each must appear in the sanitized current message or in the known context; otherwise downgrade to a clarification (not an error). Scope it to requests that carry a session — **including a session's first turn, when the context is still empty** — so requests with no session stay byte-for-byte unchanged. A guard scoped to "non-empty context" leaves a hole exactly where it matters: with nothing to resolve a reference against, the model invents identifiers (it copies the examples in your own prompt, at high confidence), and editing the examples doesn't stop it — only the deterministic check does. Test this with the real model, not just fakes.
- **Ordering contract**: results must be returned (and remembered) in the order the user requested/saw them, or "the first one" silently means a different item than the screen shows.

---

## 5. State Management & Memory Hierarchy

- **Session identity**: `{{how is a session keyed? e.g. session_id per conversation, tied to a customer_id if authenticated}}`
- **Context decoupling**: short-term session state (ephemeral tool scratchpads) must stay isolated from long-term memory (customer profile, order history).
- **Token sliding window**: `{{FIFO eviction / summarization buffer — specify the strategy and the trigger (e.g. token count > N)}}`

If the system is multi-turn (Section 1), answer **all** of the following — each maps to a decision that is expensive to retrofit:

- **Where memory lives and who issues the ID**: `{{server-side per-session store vs. client resends the transcript vs. external DB/Redis}}`. Prefer server-side keyed by a **client-generated, optional** `session_id` (128-bit random) when the process is single-instance: a client-supplied transcript lets the client forge what "the assistant said" and grows every request, and an *optional* ID keeps stateless callers (CLI, form pages, existing tests) byte-for-byte unchanged. State the accepted limit (in-process memory ⇒ single worker) and the upgrade path.
- **What is remembered — structured facts, not a transcript**: entity identifiers with their display fields, stated filters/constraints, and the last N sanitized user messages. **Do not persist model-written prose** (summaries, rationales, answers): it is the highest-risk content for carrying an injection across turns, it bloats every later prompt, and the facts a follow-up needs are re-derivable from source data. Name the one exception you allow (e.g. a pending clarification question, so the user's answer to it is understood).
- **Bounds, all numeric**: turns kept, entities in focus, characters per stored message, max sessions, idle TTL (sliding), max entities per request. `{{N / N / N / N / N / N}}` — unbounded memory is a DoS surface.
- **Lifetime**: `{{ephemeral, in-process, never persisted; lost on restart}}` — say so, and add a "restart forgets everything" scenario so it is a stated behavior, not a surprise. Provide an explicit clear ("New chat" + idempotent `DELETE` that returns the same status whether or not the session existed).
- **Interaction with any response cache (Section 8/12)**: a cache keyed by query text is only valid for answers that depend on the text alone. Once answers depend on context, a context-resolved answer cached under bare text is served to an unrelated session (wrong answer *and* a cross-session leak). Rule: **read and write the cache only for requests with no session or no prior turns**; still record a cache-hit turn into memory (carry the turn's "facts" in the cached value so filters aren't lost).
- **Mechanism for what gets remembered**: the typed response alone often can't say which filters the user stated (only the routing decision knows). Return a `(response, facts)` result from a new entry point and keep the existing one as a thin wrapper, rather than changing an established return type that every test depends on.
- **Isolation and disclosure**: no read endpoint, context never included in any response, full session ID never logged (log an 8-char prefix), invalid ID → validation error.
- **Never put the session ID in a URL** (path or query string). URLs are written to the server's access log, reverse-proxy logs and the HTTP client's own log, so a bearer ID in a path (`DELETE /sessions/{id}`) is logged in full even when your application code is careful. Send it in the request body (`POST`) or a header (`X-Session-ID`) — found only by running the real server and reading its console, not by unit tests.
- **Partition any response cache by guarded vs. unguarded path**: if session requests get a deterministic guard (Section 4) that stateless requests don't, the two must not share cache entries — a stateless answer cached under the bare text would be served to a session's first turn and bypass the guard.
- **Scope of memory**: name which pages/entry points use it and which deliberately don't (forms with explicit inputs should not gain hidden memory).

---

## 6. Schema Typing & Validation

- Incoming requests and outgoing responses (including every sub-agent's I/O from Section 3) must validate against strict schemas (Pydantic v2 or equivalent).
- On a schema/contract violation, return an explicit JSON error envelope — never an unhandled 500/stack trace.

**Error envelope shape**: `{{e.g. {"error": {"code": str, "message": str, "sub_agent": str | None}}}}`

---

## 7. Dependency Injection & Resource Lifecycle

Long-lived resources — DB pools, HTTP clients, LLM client instances — must be instantiated once at startup and injected into route/agent calls, never re-instantiated per request.

**Singleton resources for this project**: `{{list them, e.g. asyncpg pool, OpenAI client}}`

---

## 8. UI Design & Frontend Integration

**When this section applies**: only once a UI is in scope for the current roadmap milestone (Section 14) — mark it "not yet in scope" rather than filling it with placeholders if no UI exists yet, same convention Section 12 uses for its cost-optimization analysis. Once it *is* in scope, every subsection below must be answered before the first page is built — every item here maps to a real issue that otherwise gets discovered mid-build and patched afterward instead of designed in from the start.

### Required discovery before implementation

- **Framework and consumption boundary**: `{{e.g. Streamlit, calling the API layer (Section 1) over real HTTP}}`. State explicitly whether the UI is a separate process/deployment from the agent backend, and justify it — importing agent/backend code in-process instead of calling the API boundary duplicates whatever singleton-resource/validation logic Section 7 exists to centralize, and defeats the reason that layer was built.
- **Cold-start discoverability**: what can a user with *zero* prior context about this system's data actually do on the very first screen? If every planned workflow assumes the user already knows something specific (a record ID, a category, an account number), name the one view that doesn't — a way to browse/discover before asking anything. A real project this template was validated against shipped 5 workflows that all assumed prior knowledge, then had to add a 6th "browse" view as a follow-up request once a real user hit the gap — decide this up front instead.
- **Home page / entry point**: which view loads first, and is that still the right choice once the discoverability view above exists? Decide explicitly rather than defaulting to whichever workflow was built first — changing the entry point later means relocating real, working code (session state, routing, framework-specific setup) between files, not just a config change.
- **Framework's actual import/execution mechanics — verify against the installed package, don't assume**: many UI frameworks run your code through a launcher that manipulates `sys.path`/the working directory differently than a normal `python -m` invocation, and differently again from how your own test harness runs the same file. Check the installed framework's actual source for how it resolves imports (e.g. Streamlit's `web/bootstrap.py::_fix_sys_path` adds only the target script's own directory to `sys.path`, never the project root — a real bug hit in production use of this template, invisible to a headless test runner that inherits the current process's already-correct `sys.path` instead of replicating the framework's real launch mechanics). Verify the literal documented run command actually works end-to-end, not just that the test suite passes.

### Data-browsing views — a checklist per view, not just once per project

For every view that lists/browses a collection of records (not a single-record lookup):

- **Filter/sort scope, decided up front, not negotiated in rounds**: which fields are filterable, and by what widget shape (single-select, multi-select, numeric range, text search)? Naming these late means shipping a "just enough to feel done" first pass and re-litigating the rest as follow-up requests one at a time.
- **Volume and rendering strategy**: how many records, realistically? A flat table with the framework's own built-in virtualization scales very differently than a per-record loop of interactive widgets (a button/checkbox per row) — the latter needs pagination or a hard result cap before it's even buildable at scale. Decide which shape up front; it changes the widget choice itself, not just a later config tweak.
- **Cross-view interactivity, explicitly in or out**: does selecting something in this view need to carry into another view (a deep link, a pre-filled form, a "cart"/multi-select-then-act pattern)? If yes, name the state-carrying mechanism up front (session state, URL query params, a shared backend resource). If no, say so explicitly in Appendix B rather than leaving it to be inferred — so a later request to add it reads as new scope, not a missed requirement.
- **Numeric filter bounds — real data or a fixed guess?**: range filters (price, date, score) should derive their min/max from the actual dataset, not a hardcoded constant. If they do, say so here and carry the implication into Section 13's mocking policy: any test fixture using smaller/different sample data will have correspondingly different real bounds, and a filter test's chosen values must respect the *fixture's* range, not the production range — a common, easy-to-hit test-authoring trap otherwise.

### Caching strategy

- **What's cached, where, at what scope**: per-process (shared across every concurrent user — e.g. a loaded reference dataset) vs. per-session (one user's own view/data) vs. per-request (nothing cached). Framework-level caching decorators are typically **process-wide by default**, not per-session and not per-test-run. If the test suite exercises the same cached function with different fixture data across multiple tests, the cache must be explicitly cleared between them — otherwise a later test silently observes an earlier test's cached result instead of its own, and fails (or worse, passes) for the wrong reason. Name this explicitly alongside Section 13's mocking policy, not as a separately-discovered surprise mid-implementation.

### Response rendering

- **One shared renderer per response-shape family, not one per view**: if multiple views/pages can receive the same set of possible response shapes (e.g. every sub-agent's typed output, Section 3), write one dispatcher function keyed on a distinguishing field and reuse it everywhere that shape can appear — not a near-duplicate implementation per page. Adding a response shape means checking its distinguishing key overlaps no existing one.
- **Lookup-key visibility**: if any flow (a follow-up question, a form, a sub-agent input) is keyed on an identifier (a product/order/account ID), **every place the UI shows an entity must show that identifier**, or the user cannot reuse what they were just shown. Guarantee it **deterministically in the renderer** (cards are built from source records, not model output) and add a prompt rule for model-written text ("write 'Name (ID)'") that is **verified by an eval assertion, not trusted**. Do not "fix" it by regex-replacing names with IDs in generated text — names repeat and appear as substrings, so it can corrupt sentences.
- **Session identity in the UI**: generate the session ID once per UI session, send it only from views that use memory, provide a "new conversation" control, and document that a browser refresh/new tab is a new conversation.

---

## 9. Cognitive Features (Tier 2 — build when the product requirement justifies it, not by default)

| Feature | What it does | Trigger to build it |
| :--- | :--- | :--- |
| Scatter-Gather / Fan-Out | Decompose a multi-intent query, dispatch to N sub-agents via `asyncio.gather`, synthesize one response | A real query in the eval set (Section 13) needs >1 sub-agent to answer |
| Vector Semantic Cache | Skip LLM generation for near-duplicate queries via embedding-distance cache | Measured LLM cost/latency becomes a problem |
| Human-in-the-Loop (HITL) Intercept | Escalate to a human queue on low confidence or negative sentiment | Product requires a human fallback path |
| Streaming (SSE/WebSocket) | Progressive token streaming with status markers | A UI consumes this agent directly (needs an API layer first — see Section 1, and Section 8 for the UI's own design) |

---

## 10. Resiliency & Graceful Degradation

```
Coordinator Request ──► [Circuit Breaker: CLOSED] ──► Sub-Agent Execution
                              │
                              ├─► (Failures > {{N}} in {{window}})
                              ▼
                      [Circuit Breaker: OPEN]
                              │
                              └──► Graceful Fallback (cached/static content)
```

| Control | Default | Notes |
| :--- | :--- | :--- |
| Sub-agent timeout | `{{4.0s}}` | Terminate unresponsive calls, trigger the fallback path |
| Retry backoff | Exponential + jitter | Only for retriable errors (e.g. `429`) — never for data/validation errors |
| Circuit breaker trip | `{{>15% failure rate}}` over `{{1 min}}` | Routes to a static fallback without exhausting backend threads |

---

## 11. Data Governance & Security

- **Input sanitization**: strip/neutralize prompt-injection delimiter attacks before queries reach the coordinator prompt.
- **PII redaction**: scrub credit-card numbers, emails, phone numbers before routing to sub-agents (or before logging).
- **Credential handling**: secrets come from `{{env vars for local dev / a secrets manager for prod}}` — never hardcoded, never logged.
- **Conversation memory (if Section 5 applies)** — walk STRIDE explicitly: *Spoofing* (a session ID is a bearer secret when no auth exists → 128-bit random, never logged in full/returned), *Tampering* (memory is server-side and built only from typed responses; stored user text sanitized and injected inside a delimited "reference data, never instructions" block), *Repudiation* (log an ID prefix), *Information disclosure* (no read path; per-session isolation tested), *DoS* (every bound in Section 5, plus a per-request entity cap), *Elevation* (memory adds no tools; the Section 4 identifier guard rejects IDs nobody mentioned).

---

## 12. Telemetry, Tracing & Operational SLA

| Metric | Collection mechanism | Target SLA |
| :--- | :--- | :--- |
| Time to First Token (TTFT) | `{{tracing tool}}` | `{{< 800ms}}` |
| Total turn duration (p95) | `{{APM tool}}` | `{{< 2.5s}}` |
| Routing accuracy | Offline eval set (Section 13) | `{{> 96%}}` |
| Token cost per turn | `{{billing metric source}}` | Tracked per session |

A trace ID must link every hop across coordinator → sub-agent calls.

### Log persistence — decide this alongside the metric mechanism above, not as a later patch

Console-only logging looks complete during development (the lines are visible while you watch) but isn't durable — they vanish with the terminal's scrollback the moment the process is backgrounded or the window closes. Specify **where logs actually land**: `{{e.g. a rotating file handler per process entry point, alongside the console handler}}`. If multiple independent process entry points exist (a CLI, an API server, a worker), each needs this configured — don't assume one entry point's logging setup covers another.

### Cost optimization strategy — decide applicability before building anything

Same discipline as Section 13's evaluation strategy: walk this before implementing any cost-optimization technique, and only build what the analysis actually calls for. This section records the **requirement to eventually do this analysis** even on a project where cost hardening isn't in scope yet — per Section 14's Roadmap, this typically lands alongside the rest of Section 12 in a later hardening phase, not at initial build time; leaving this section blank (rather than filled with "N/A") would silently drop the requirement instead of deferring it.

**Cost categories** (source: standard GenAI cost breakdown): **Prompt cost** (scales with query frequency/complexity), **Generation cost** (scales with output length/complexity), **Fixed cost** (infrastructure/storage, constant regardless of usage).

**General guidelines**, apply selectively per the applicability questions below, not all by default:
1. Focus on token usage — prompt and response length are the biggest cost drivers.
2. Strategic model selection — don't default to the largest/most expensive model per component; pick the smallest one that meets the quality bar.
3. Implement caching for frequently repeated prompts/responses where applicable.
4. Continuous monitoring — track real token usage and cost, not estimates.
5. Iterate — cost optimization is ongoing, not a one-time pass.

**Methodology**: (1) identify which components in *this* architecture actually incur token cost (list them, same granularity as Section 3's sub-agent registry — a component with no LLM/embedding call in it has no token cost to optimize); (2) for each, check whether a cheaper model still meets the quality bar; (3) measure real usage across a representative query set (not a single test call) and set any token/length caps from that observed data, not a guess.

**Applicability questions** — answer these before assuming a technique applies:
- Does this system embed and retrieve by semantic/vector search at all? If there's no embedding/vector-store component, embedding-cost optimization (model choice, persisting a vector index instead of re-embedding, multi-tenancy) doesn't apply — don't build it for a component that doesn't exist.
- Does this system carry multi-turn conversational memory that grows across a session? If every query is handled statelessly (no chat history passed between turns), memory-summarization optimization has nothing to act on. If it *does*, the bounded structured context in Section 5 is itself the cost control — measure the per-turn token delta from the existing usage log rather than estimating, and remember it also removes the response cache's benefit for context-bearing turns.
- Is a cost-appropriate model already the default per component (check Section 3's registry), or is a larger/pricier model being used where a cheaper one would meet the bar?
- Is there an existing monitoring/billing metric source, or does one need to be stood up before "track real usage" is even possible?

Record the outcome — including techniques marked not applicable — as Decision Log rows in Appendix A, same convention as Section 13.

---

## 13. Required Test Suite & Evaluation

### Evaluation strategy — decide applicability before building anything

Every RAG/agentic system can in principle be scored on 4 standard LLM-as-judge metrics. Before writing a single evaluator, walk this table and mark each metric applicable / not applicable / already covered *for this project's actual architecture* — do not build all 4 by default just because the table lists 4.

| Metric | Compares | Needs ground truth? |
| :--- | :--- | :--- |
| Correctness | response vs. reference answer | yes |
| Relevance | response vs. input question | no |
| Groundedness | response vs. retrieved/source docs | no |
| Retrieval relevance | retrieved docs vs. input question | no |

Questions to answer for each row, filled in below (not here):
- **Retrieval relevance** only means something if retrieval is *semantic* (embeddings/vector search, ranked results). If this system selects records by exact lookup or structured filtering instead, there's no ranked-retrieval step to score — the real question ("did we select the right records?") is better answered by a **deterministic** assertion against known ground truth than by an LLM judge.
- **Correctness** needs a reference answer — if the exact correct value for a case is knowable in advance from the source data itself (an ID, a price, a policy field), prefer a deterministic field assertion over an LLM judge: it's cheaper, faster, and isn't itself a fallible model call.
- **Groundedness** earns its keep specifically where a response contains **free text synthesized from source records** the model was shown (a summary, a rationale, an explanation) — deterministic checks can't catch prose that quietly drifts from the facts it was supposed to reflect. If no sub-agent returns synthesized prose (every field is a structural reference Python resolves), this metric may not apply either.
- **Relevance** (does the response address the question) is often already implied by stricter checks already in place (correct tool routed to, correct response shape) — don't add a redundant LLM-judge pass on top of those without a concrete reason.

Record the outcome of this analysis as Decision Log rows in Appendix A — one row per metric, **including the ones marked not applicable** (the record of what was considered and rejected is the point, same as any other Decision Log entry). Only the metrics the analysis actually calls for get built below.

### Test suite

- **Routing-accuracy eval set**: a fixed list of `(query, expected_sub_agent)` pairs, run offline against the live classifier — this is what Section 12's "Routing accuracy" SLA measures against.
- **Golden Q&A regression set**: known-good `(query, expected_response_shape)` pairs per sub-agent, to catch prompt/model-swap regressions.
- **Mocking policy**: `{{how are LLM calls mocked in unit tests? e.g. a fixed-response fake model for schema/routing tests, real-model calls only in the eval set}}` — if a UI is in scope (Section 8), extend this to name the UI's own mocking approach (e.g. a fake API-client stand-in driven through the framework's own headless test tool) and whether it exercises the framework's real launch mechanics or only the current process's already-correct import state (see Section 8's import-mechanics note — a UI test suite that never actually invokes the documented run command can pass while that command still fails for a real user).
- **Contract tests**: every sub-agent's declared input/output schema (Section 3) is exercised with at least one valid and one invalid payload.
- **Multi-turn cases (if Section 5 applies)**: add them to the *same* routing/golden sets, not a separate one — reference by position/attribute/"both", refinement inheriting a constraint, topic change ignoring stale context, unresolvable reference on empty context (→ clarify), the model extracting an ID nobody mentioned (→ guard), isolation between two sessions, cache non-poisoning, bounds/TTL/eviction, "model-written text is not remembered". Use a prompt-capturing fake model (e.g. PydanticAI `FunctionModel`) to assert the rendered context *actually reached* the model — a fixed-output fake can't show that — and assert stateless prompts are byte-identical to before.
- **Measure prompt-rule changes with repeated runs, one hypothesis at a time**: a one-sentence prompt rule (e.g. "write 'Name (ID)'") shifted an LLM-judged eval from 10/10 to ~5/6 by changing *what the model talks about*, and a first "obvious" fix was refuted by a 15-run measurement and reverted. Run each candidate 10–15 times against a control (a throwaway pytest plugin can toggle a prompt constant with no file edits), read the *failing* text rather than theorizing, and keep the check that asserts the rule (an eval), never trust it. Also expect test-authoring bugs (e.g. reused product names) to surface here before assuming the model is wrong.
- **Async eval harness pitfall**: if the real-API eval fixtures build agents at session scope (one shared HTTP client/connection pool), the async tests must share a session-scoped event loop. With function-scoped loops, a pooled keep-alive connection from an earlier test's closed loop is reused and later tests fail with `RuntimeError: Event loop is closed` — while passing when run alone, which makes it look like flaky LLM behavior. Scope the loop fix to the eval directory, prove it with a full single-process run, and skip-guard real-API tests on the API key with the documented way to load it.
- **Applicable metric evaluators** (per the analysis above — e.g. a groundedness judge if this project's sub-agents return synthesized prose): `{{list only what the analysis above concluded is applicable}}`
- Durable test-generation log: append results to `{{path, e.g. .agents/memory-bank/testGenerationLog.md}}`, following this project's existing convention.

---

## 14. Roadmap / Phase Mapping

Map this document's sections to when each is actually being built — update the **Status** column in place as work progresses. This is the mechanism for tracking "what's real today," not a separate per-phase spec file.

Use sequential phase numbers (`Phase 1`, `Phase 2`, ...) rather than calendar time (sprints/weeks/dates) — a phase name should describe a capability milestone that holds up regardless of how the project's schedule shifts.

| Section(s) | Capability | Target phase | Status |
| :--- | :--- | :--- | :--- |
| Section 3, Section 4, Section 6 | Coordinator routes to 1 sub-agent, strict schemas | `{{e.g. Phase 1}}` | ⏳ Planned |
| Section 3 (additional rows) | More sub-agents registered | `{{e.g. Phase 2}}` | ⏳ Planned |
| Section 13 | Evaluation harness | `{{e.g. Phase 3}}` | ⏳ Planned |
| Section 1 (API layer), Section 9 (streaming) | FastAPI integration | `{{e.g. Phase 3}}` | ⏳ Planned |
| Section 8 | UI, including the cold-start discoverability view | `{{e.g. Phase 4}}` | ⏳ Planned |
| Section 10, Section 11, Section 12 | Resiliency, security, telemetry | `{{e.g. Phase 4 / post-launch}}` | ⏳ Planned |

---

## 15. Acceptance Criteria (pre-build gate)

- [ ] Section 1 discovery questions answered (domains, QPS/latency target, eval dataset status, API-layer status, whether a UI is in scope this milestone).
- [ ] Section 2 pattern selected with a justification tied to the actual product requirement.
- [ ] Section 3 registry lists every sub-agent in scope for the *current* roadmap milestone (Section 14), each with input/output schemas.
- [ ] Section 4 confidence source is concretely specified, not left as "the LLM decides."
- [ ] Section 5 session-identity contract is defined.
- [ ] Section 8's discovery questions are answered once a UI is part of the current roadmap milestone (Section 14) — not required before then, but not skipped once it is the milestone in scope. In particular: the cold-start discoverability view is named, the home page is decided, and the framework's real import/execution mechanics have been checked against its actual installed source, not assumed.
- [ ] Section 13 mocking policy and at least a draft eval set exist before agent code is written.
- [ ] Section 13's evaluation-strategy applicability analysis is filled in for all 4 metrics (not skipped) — including a Decision Log row for each metric marked not applicable.
- [ ] Section 12's cost-optimization applicability analysis is filled in once cost hardening is part of the current roadmap milestone (Section 14) — not required before then (see Section 14's typical later-phase placement), but not skipped once it is the milestone in scope.
- [ ] If multi-turn: every Section 5 item is answered with numbers (bounds, TTL), the cache interaction rule is stated, and the reported failing conversation was **reproduced against the running system** and quoted in the spec.
- [ ] Every sub-agent's input cardinality (Section 3) is declared and checked against the follow-ups the spec promises (e.g. "both").
- [ ] If any flow is keyed on an identifier: the lookup-key visibility rule (Section 8) is specified for every view that shows the entity.
- [ ] Appendix A (Decision Log) has no open rows.
- [ ] Appendix B (Out-of-Scope) is filled in — not left empty.

---

## 16. Production Verification Checklist (post-build gate)

- [ ] Substring/keyword matching eliminated in favor of semantic intent classification.
- [ ] Strict schemas enforced on every cross-agent boundary (Section 6).
- [ ] Long-lived resources injected as singletons, not re-instantiated per call (Section 7).
- [ ] Context-window eviction/sliding buffer configured (Section 5).
- [ ] If a UI is in scope (Section 8): the literal documented run command was actually executed and verified, not just the test suite — including a check of what the real framework does to `sys.path`/imports, since a test harness can silently exercise different mechanics than the real launch path.
- [ ] Circuit breaker and timeout policies defined for each downstream dependency (Section 10).
- [ ] PII redaction and prompt-injection filters active (Section 11).
- [ ] Distributed tracing (trace ID) linked across all agent hops (Section 12); logs confirmed to actually persist somewhere durable (not console-only) for every process entry point.
- [ ] Routing-accuracy eval set passes at the Section 12 target (Section 13).
- [ ] If multi-turn: the real end-to-end conversation from the spec was run against the live app (and "new conversation" then re-run to confirm it forgets); logs show context-turn counts and an ID *prefix* and `grep` finds no full session ID; the eval suite passes in a **single combined process**, not just test-by-test.
- [ ] If any flow is keyed on an identifier: the identifier is visible on every rendered entity, and the ID-citing eval assertion passes.

---

## Appendix A: Decision Log

| Decision | Options considered | Selected option | Reason | Date |
| :--- | :--- | :--- | :--- | :--- |
| `{{DECISION}}` | `{{OPTIONS}}` | `{{SELECTED}}` | `{{RATIONALE}}` | `{{DATE}}` |

*Decisions worth a row when Section 5 applies*: where memory lives; who issues the session ID; what is (and is not) remembered; who resolves references; identifier guard; cache policy with memory; numeric bounds; which pages get memory; how memory is cleared; N-entity input cardinality per sub-agent; how identifier visibility is guaranteed.

## Appendix B: Out-of-Scope / Non-Goals

List what this coordinator agent explicitly does **not** do at the current roadmap milestone (Section 14), so scope creep has an obvious reference point.

- `{{e.g. "Multi-language support — deferred, no requirement yet"}}`

---

**Version**: 2.3 (added: deterministic chitchat/greeting detection and consistent, capability-describing "couldn't help" wording; v2.2 added session ID never in a URL, cache partitioning, guard scope for empty first turn, measuring prompt changes; v2.1 added multi-turn memory, reference resolution, input cardinality, lookup-key visibility and async-eval-harness guidance; v2.0 added Section 8: UI Design & Frontend Integration)
**Last Updated**: `{{Date}}`
**Template Author**: `{{Name}}`
