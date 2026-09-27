# ShopEnsemble

An AI shopping assistant: a coordinator agent classifies a shopper's natural-language question and routes it to one of four specialist sub-agents — product recommendations, product comparison, review summarization, and store policy/FAQ — backed by a validated PostgreSQL product catalog. Built with [PydanticAI](https://ai.pydantic.dev/), FastAPI, and Streamlit.

## What's here

| Layer | Tech | What it does |
| :--- | :--- | :--- |
| Data pipeline | pandas, SQLAlchemy (async) + asyncpg | Validates `data/*.csv` (products, reviews, store policies) and loads them into PostgreSQL, idempotently |
| Coordinator agent | PydanticAI + OpenAI | Classifies intent, confidence-gates dispatch, routes to the right specialist agent |
| API | FastAPI | `GET /health`, `GET /products`, `POST /query` |
| UI | Streamlit | Browse Catalog (home page), Chat Assistant, Recommendations, Compare Products, Review Summaries, Policy/FAQ |

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
streamlit run app/ui/streamlit_app.py   # opens at http://localhost:8501
```

## Project structure

```
app/
├── main.py              # data pipeline CLI entry point
├── models.py             # Product/Review/StorePolicy — shared Pydantic models
├── pipeline/              # ETL, ingestion, persistence (PostgreSQL)
├── agents/                # coordinator + 4 sub-agents (PydanticAI)
├── api/                   # FastAPI layer — health, products, query
└── ui/                    # Streamlit — Browse Catalog + 5 other workflow pages

data/                      # source CSVs (products, reviews, store_policies)
tests/                     # mirrors app/ — pipeline, agents, api, ui
specs/                     # specifications only (BDD narrative + Gherkin)
plans/                     # implementation plans (one per spec, mirrored folder structure)
Reference/Learning/        # per-topic reference docs + sequence diagrams (local-only)
skills/SpecToolBox/        # reusable spec/plan templates this project's own specs were built from
```

## Testing

```bash
python -m pytest -q -m "not integration and not eval"   # fast suite, no network/DB/LLM calls
python -m pytest -m integration                          # needs: docker compose up -d postgres
python -m pytest -m eval                                 # needs: OPENAI_API_KEY, makes real billed calls
```

## Docs

- **Specs**: `specs/1_data-pipeline/`, `specs/2_coordinator-agent/` — what's built, requirements, decision logs.
- **Plans**: `plans/1_data-pipeline/`, `plans/2_coordinator-agent/` — the approved implementation plan behind each spec.
- **Reference**: `Reference/Learning/<topic>/` — command references, data models, sequence diagrams (gitignored, local-only).
- **Agent conventions**: [AGENTS.md](AGENTS.md) — rules this project's own coding agents follow (gitignored, local-only).

## Status

Data pipeline, coordinator agent (4 sub-agents), API layer (with rate limiting/caching/telemetry), and UI (6 pages, catalog browsing as the home page) are all implemented and verified end-to-end. Scatter-gather/composite multi-domain routing is the one capability not yet built — see `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` Section 13 for the full roadmap.
