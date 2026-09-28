# Phase 3b — FastAPI Layer Implementation Plan

**Status:** ✅ Implemented and verified (2026-09-16) — 5/5 contract tests passing, 116/116 in the full fast suite (zero regressions), plus a real end-to-end run (`uvicorn` + `curl`, real OpenAI API) covering health, a genuine coordinator round-trip, and both validation-error boundaries.
**Governing spec:** [shopensemble-coordinator-agent-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md) Section 13 (Phase 3 row), Section 1 (Deployment Topology), Section 7 (Dependency Injection & Resource Lifecycle); `specs/shopensemble-project-requirements.md` Section 7 (API and UI Requirements) — the actual requirement text (health endpoint, query endpoint, separate request/response models, clear validation errors, contract tests).
**Precedes:** Nothing further planned yet within Phase 3 — this was the last deferred piece (3a shipped the eval harness, 3a Part 2 shipped groundedness, this is 3b).
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (`v9` entry)

## Implementation Notes (added post-implementation)

- **Built exactly as designed** — no design changes were needed during implementation, unlike every prior phase. The one real surprise was environmental, not architectural (next point).
- **This project's pinned FastAPI/Starlette versions (`fastapi==0.141.1`, `starlette==1.6.0`) are much newer than commonly-assumed defaults, with a materially different internal routing representation** — `app.routes` no longer shows a flat list of registered paths after `include_router()` (an `_IncludedRouter` wrapper with an "effective candidates" routing architecture instead). Caught via `python -c "... app.routes ..."` introspection before writing any tests (Rule 9 — verify against reality); confirmed the routes still dispatch correctly via `TestClient` regardless, so no code change was needed, only that my mental model of what `app.routes` would print was wrong.
- **`TestClient.raise_server_exceptions` is constructor-only in this Starlette version** — setting it on an already-built client (`client.raise_server_exceptions = False`) silently has no effect. The one test that needs it (verifying the global exception handler doesn't leak a raw exception message) builds its own `TestClient(app, raise_server_exceptions=False)` instance rather than reusing the shared fixture's client. Caught by actually running the test and seeing the exception propagate into the test instead of returning a 500 — not assumed correct.
- **Real end-to-end verification** (`uvicorn app.api.main:app`, then `curl`): server started cleanly (lifespan built the catalog + all 5 agents without error); `GET /health` → `200 {"status":"ok"}`; `POST /query` with `"What do people say about SP0001?"` → a real coordinator → review-agent round trip through HTTP, correct `ReviewSummaryResponse` shape and real generated content; empty query → `422` with safe structured field-level detail; a 2001-character query → `422`, correctly rejected at the schema boundary. No attempt was made to force a real 500 from the live server (would require deliberately breaking something with no real additional coverage over the already-passing mocked exception-handler test).
- All of `app/api/`/`tests/api/` stayed local-only per the confirmed git scope — only `.gitignore`'s new exclusion lines and this file's status update are tracked.

## Context

The governing spec (`shopensemble-coordinator-agent-spec.md` Section 13) has carried "Phase 3b (FastAPI layer) still ⏳ Planned" since Phase 3a shipped — it's the one deliberately-deferred piece from every prior Phase 3 plan. `shopensemble-project-requirements.md` Section 7 states the actual requirement: a health endpoint, a customer-query endpoint routed to the coordinator, separate request/response models where lifecycle differs, clear validation errors without leaking internals, and contract tests before deployment. No endpoint paths, request/response shapes, or auth scheme are specified beyond that — this plan makes those concrete choices.

Verified via Explore agent (2026-09-16): `fastapi==0.141.1` and `uvicorn==0.52.4` are already in `requirements.txt` and installed — no new dependency needed. `httpx` (needed for `TestClient`) is already installed transitively. No `app/api/` directory or any FastAPI/uvicorn reference exists anywhere in `app/` yet — this is genuinely greenfield, no naming collision with `app/main.py` (the unrelated data-pipeline CLI entry point).

One real, spec-flagged risk this plan directly resolves: Appendix A already notes that `app/agents/cli.py::main()`'s pattern of printing a caught exception's raw message would be an information-disclosure risk "if reused verbatim by the Phase 3b FastAPI layer" — this plan's global exception handler is the fix, not a follow-up.

**Git scope (confirmed with the user):** `app/api/` and `tests/api/` get added to `.gitignore` alongside the existing `app/agents/`/`tests/agents/` exclusion — the API layer imports directly from `app.agents`, so tracking it while `app/agents/` stays untracked would push code with unresolvable imports.

---

## Design

### Module layout — `app/api/`, matching `shopensemble-project-requirements.md` Section 5's own recommended boundary

```
app/api/
├── __init__.py
├── main.py          # FastAPI() instance, lifespan (builds catalog/coordinator/sub_agents once), router include, global exception handler
├── dependencies.py  # AppState dataclass + get_app_state() Depends provider (overridable in tests)
├── schemas.py       # QueryRequest{query: str} — the one new API-boundary request model
└── routes.py        # APIRouter: GET /health, POST /query
```

### Singleton resources via FastAPI `lifespan` (spec Section 7's existing requirement, now given an actual mechanism)

Section 7 already mandates the catalog and agent clients be built once, not per-call — `app/agents/cli.py::_run()` does this per-CLI-invocation; the API layer needs the equivalent done once per **process**, not once per request. `main.py`'s `lifespan` context manager calls `load_catalog_data()`, `build_coordinator_agent()`, and builds `SubAgents(...)` exactly the way `cli.py` already does, storing the result as an `AppState` on `app.state`. `dependencies.py::get_app_state(request: Request) -> AppState` reads it back out — this indirection (rather than reading `request.app.state` directly in every route) is what makes contract tests possible: tests use `app.dependency_overrides[get_app_state] = ...` to swap in `TestModel`-built agents, the FastAPI-idiomatic equivalent of this project's existing `monkeypatch`/fake-agent convention (`tests/agents/test_coordinator.py::_fake_sub_agents`).

### Endpoints

- **`GET /health`** → `{"status": "ok"}`. Minimal per the spec's own minimal ask (no elaborate readiness/liveness split — matches this project's "no production SLA yet" scope discipline, Appendix B).
- **`POST /query`**, body `QueryRequest{query: str}` (new, `app/api/schemas.py` — `Field(min_length=1, max_length=MAX_QUERY_LENGTH)`, reusing `app.agents.sanitize.MAX_QUERY_LENGTH` for the same bound already enforced one layer down, defense-in-depth per the existing convention from the earlier code-review fix). Calls `handle_query(app_state.coordinator_agent, app_state.sub_agents, app_state.catalog, request.query)` and returns its result directly — `response_model=CoordinatorResponse`, the existing 7-member union, reused as-is; no new response schema needed.

### Error handling — the actual fix for the flagged info-disclosure risk

A global `@app.exception_handler(Exception)` in `main.py`: `logger.exception(...)`s the real error server-side, returns a generic `AgentErrorEnvelope(error=AgentError(code="internal_error", message="An unexpected error occurred.", sub_agent=None))` with HTTP 500 to the caller — no raw exception text ever reaches an external caller. FastAPI's own automatic 422 responses for `QueryRequest` validation failures (empty/over-length query) already return structured, safe field-level errors by default — no additional handling needed there, that satisfies "clear validation errors without leaking internals" as-is.

### Tests — `tests/api/`, same mocking policy as everywhere else (no real OpenAI calls, no new pytest marker)

```
tests/api/
├── conftest.py    # TestClient fixture; dependency_overrides[get_app_state] wired to TestModel-built agents + an in-memory CatalogData fixture
├── test_health.py # GET /health returns 200 + expected body
└── test_query.py  # valid dispatch (asserts the right CoordinatorResponse member comes back), empty-query 422, over-max-length-query 422, and an internal-error path (monkeypatch handle_query to raise) asserting the response is the generic envelope, never the raw exception text
```
Fits the existing default fast suite (`pytest -q -m "not integration and not eval"`) — `TestClient` + `TestModel` are fully synchronous/deterministic, no marker needed.

### Manual real end-to-end verification (Rule 9 — not a permanent automated suite)

Start the server for real (`uvicorn app.api.main:app --reload`) and `curl` both endpoints with a real query, confirming an actual coordinator round-trip works end-to-end through HTTP — the same "run it for real before declaring done" discipline every prior phase followed, not a permanent `eval`-marked HTTP suite (that would just duplicate `tests/agents/eval/` with an extra HTTP hop for no real additional coverage).

---

## Files

```
app/api/__init__.py
app/api/main.py
app/api/dependencies.py
app/api/schemas.py
app/api/routes.py
tests/api/conftest.py
tests/api/test_health.py
tests/api/test_query.py
.gitignore            # add app/api/ and tests/api/
```
No `requirements.txt`/`pyproject.toml` change — `fastapi`/`uvicorn`/`httpx` already present; no new pytest marker.

---

## Verification

```bash
# Fast suite includes the new contract tests, still no real API calls
.venv/bin/python -m pytest -q -m "not integration and not eval"

# Real manual smoke test
uvicorn app.api.main:app --reload &
curl -s localhost:8000/health
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' -d '{"query": "What do people say about SP0001?"}'
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' -d '{"query": ""}'   # expect 422, no internal leakage
```

---

## After implementation — update in place (established convention)

- `shopensemble-coordinator-agent-spec.md`: Section 13 Phase 3 row → fully ✅ (3a + 3b both shipped); Section 1's "Deployment Topology" note updated from "no FastAPI route until Phase 3" to reflect it now exists; Section 7 gains the lifespan/DI mechanism actually used; Appendix A gains rows for the module-layout, DI/testing-override, and error-handling decisions; the flagged Section 10 info-disclosure risk marked resolved.
- `.agents/memory-bank/testGenerationLog.md`: append a `v9` entry, same format as `v7`/`v8`.
- `Reference/Learning/coordinator-agent/`: add an "API Layer" section to the reference doc (endpoints, how to run, how DI/testing works) and extend the sequence-flow artifact with an HTTP → FastAPI → `handle_query` diagram, per `AGENTS.md` Rule 8.
- `git add`/commit/push only `.gitignore` (the new exclusion lines) — `app/api/`/`tests/api/` themselves stay local-only per the confirmed scope.

## Out of scope

Auth/API-key/CORS for the HTTP layer — the project-requirements spec states no auth requirement for this layer, and Appendix B's existing non-goals stance (no production secrets manager, no resiliency hardening) applies the same way here. Rate limiting/concurrency hardening — not justified at this scale (Appendix B). Host/port configuration via env vars — `uvicorn`'s own `--host`/`--port` flags are sufficient; no `SHOPENSEMBLE_API_*` vars needed given there's no deployment target yet. Streaming responses (SSE/WebSocket) — already an explicit Appendix B non-goal. Any change to `app/agents/cli.py` itself — it stays as the separate, already-fine-for-local-use manual entry point; only the *new* API layer gets the fixed error-handling pattern.
