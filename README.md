# ShopEnsemble

An AI shopping assistant for a product catalog. A **coordinator agent** classifies a shopper's natural-language question and routes it to one of five specialist sub-agents — recommendations, comparison, review summaries, store policy/FAQ, and judging products already shown in the conversation — backed by a validated PostgreSQL product catalog and a Streamlit chat UI with real, bounded session memory.

Built with [PydanticAI](https://ai.pydantic.dev/) (OpenAI `gpt-4o-mini`), FastAPI, and Streamlit.

## Highlights

- **Confidence-gated routing, not free-form tool-calling.** The coordinator's own structured output carries a self-reported confidence score; low confidence asks a clarifying question or declines instead of guessing, and every routing decision is logged.
- **Session memory with a deterministic safety net.** A chat conversation resolves "compare SP0001 with LP0002" → "review summary of both" correctly, but the coordinator never trusts the model with a product ID it didn't actually see — a code-level guard checks every extracted ID against the conversation before any sub-agent runs.
- **Deterministic where there's one right answer.** "Which one is the cheapest?" is computed in code from the catalog, not asked of the LLM — free, instant, and never wrong. The LLM is reserved for genuinely subjective judgments.
- **A real evaluation harness, not spot-checks.** A 42-case routing-accuracy suite and a golden-conversation suite run against the live OpenAI API; the current measured routing accuracy is **100% (42/42)**, iterated up from an initial 93.1% baseline.
- **Spec-driven, test-first development.** Every feature has a written spec (narrative + Gherkin scenarios + a decision log) and an implementation plan under `specs/`/`plans/`, built test-first with a fast, DB-free unit suite plus separate integration and real-API eval suites.
- **A generalized process, not one-off code.** `skills/SpecToolBox/` holds the reusable spec templates this project's own specs were built from, refined with lessons (session-ID handling, cache partitioning, deterministic guards) fed back in as the project grew.

## Architecture

```
Shopper
  │  natural-language question
  ▼
Streamlit UI  ──HTTP──►  FastAPI (app/api/)  ──►  Coordinator (app/agents/coordinator.py)
 (app/ui/)                 rate limiting,             classifies intent + confidence,
                            response caching,          resolves session-memory references,
                            session store               dispatches to one sub-agent:
                                                           ├─ review_summary_agent
                                                           ├─ recommendation_agent
                                                           ├─ comparison_agent
                                                           ├─ policy_faq_agent
                                                           └─ evaluate_products_agent
                                                                    │
                                                                    ▼
                                                         In-memory catalog (app/agents/data.py)
                                                                    ▲
                                                                    │  idempotent load
                                                    Data pipeline (app/pipeline/) ──► PostgreSQL
                                                                    ▲
                                                              data/*.csv (products, reviews, policies)
```

## What's here

| Layer | Tech | What it does |
| :--- | :--- | :--- |
| Data pipeline | pandas, SQLAlchemy (async) + asyncpg | Validates `data/*.csv` (products, reviews, store policies) and loads them into PostgreSQL, idempotently |
| Coordinator + 5 sub-agents | PydanticAI + OpenAI | Classifies intent, confidence-gates dispatch, resolves session-memory references, routes to the right specialist |
| API | FastAPI | `GET /health`, `GET /products`, `POST /query` (optional `session_id` for chat memory), `DELETE /session` (ID in the `X-Session-ID` header, never a URL) |
| UI | Streamlit | Browse Catalog (home page), Chat Assistant (session memory + "New chat"), Recommendations, Compare Products, Review Summaries, Policy/FAQ |

## Quick start

### 1. Environment

```bash
uv venv --python 3.12 .venv        # or: python3.12 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt # or: python -m pip install -r requirements.txt
cp .env.example .env               # then fill in OPENAI_API_KEY
```

### 2. Database (for the data pipeline)

```bash
docker compose up -d postgres
```

> If port 5432 is already taken locally (e.g. a Homebrew Postgres service), see `docker-compose.override.yml` and point `SHOPENSEMBLE_DATABASE_URL` at the remapped port instead.

### 3. Load the catalog

```bash
# Dry run first — validates data/*.csv without writing to the database
python -c "
from app.pipeline.orchestrator import run_dry_run
report = run_dry_run()
print(report)
"

# Full load
python -m app.main
```

### 4. Run the agent — pick one

```bash
# CLI, one query per invocation
python -m app.agents.cli "What do people say about SP0001?"

# API + UI (2 processes)
uvicorn app.api.main:app --reload
streamlit run app/ui/ShopEnsemble_App.py   # opens at http://localhost:8501
```

### Chat memory

The Chat Assistant remembers what you already said *within one conversation*, so you can follow up with "review both of those," "the cheaper one," or "what about under $500?" without retyping product IDs. Every product card shows its Product ID (e.g. `SP0001`) so you can reuse it. Memory is held in the API process's RAM only: it expires after 30 minutes idle (`SHOPENSEMBLE_SESSION_TTL_SECONDS`), is lost when the API restarts, and is cleared by **New chat**. Only the Chat page uses it; the other pages stay stateless. It is per-process, so run the API as a single worker (`uvicorn` without `--workers N`).

## Project structure

```
app/
├── main.py              # data pipeline CLI entry point
├── models.py            # Product/Review/StorePolicy — shared Pydantic models
├── pipeline/             # ETL, ingestion, persistence (PostgreSQL)
├── agents/               # coordinator + 5 sub-agents (PydanticAI), conversation memory
├── api/                  # FastAPI layer — health, products, query, sessions (chat memory)
└── ui/                   # Streamlit — Browse Catalog + 5 other workflow pages

data/                      # source CSVs (products, reviews, store_policies)
tests/                     # mirrors app/ — pipeline, agents, api, ui
specs/                      # specifications: narrative + Gherkin scenarios + decision logs
plans/                      # implementation plans, one per spec, mirrored folder structure
skills/SpecToolBox/         # reusable spec/plan templates this project's own specs were built from
```

## Testing

```bash
python -m pytest -q -m "not integration and not eval"   # fast suite, no network/DB/LLM calls (273 tests)
python -m pytest -m integration                          # needs: docker compose up -d postgres (11 tests)
python -m pytest -m eval                                 # needs: OPENAI_API_KEY, makes real billed calls (14 tests)
```

Mocking policy: `pydantic_ai.models.test.TestModel`/`FunctionModel` stand in for the LLM everywhere except `tests/agents/eval/`, the one directory that intentionally calls the real OpenAI API. `tests/agents/eval/routing_cases.py` is the routing-accuracy set (single-turn and multi-turn cases in one aggregate gate); `tests/agents/eval/test_golden_qa.py` is the golden-conversation set, including the exact end-to-end conversations this project's own session-memory and focus-scoped-follow-up features were built to fix.

## Docs

- **Specs**: `specs/1_data-pipeline/`, `specs/2_coordinator-agent/` — what's built, requirements, decision logs, one living document per domain, updated in place as the project grew (Phases 1–7).
- **Plans**: `plans/1_data-pipeline/`, `plans/2_coordinator-agent/` — the approved implementation plan behind each spec, including post-implementation notes on what was found and fixed along the way.
- **SpecToolBox**: `skills/SpecToolBox/` — the reusable templates behind every spec here, generalized as the project's own specs surfaced real lessons (session-ID handling, cache partitioning, deterministic reference resolution, chitchat detection).

## Status

Data pipeline, coordinator agent (5 sub-agents), API layer (rate limiting, caching, session memory, telemetry), and UI (6 pages, catalog browsing as the home page) are all implemented and verified end-to-end against the real OpenAI API. Measured routing accuracy: **100% (42/42)**. Scatter-gather/composite multi-domain routing (a single query spanning more than one sub-agent) is the one capability not yet built — see `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` Section 13 for the full roadmap.
