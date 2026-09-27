# ShopEnsemble AI Project Requirements

**Status:** Project-specific requirements draft for review  
**Project:** ShopEnsemble AI  
**Python:** 3.12  
**Primary toolkit references:** `skills/SpecToolBox/Data_Model_Spec_Template.md`, `skills/SpecToolBox/DATA_PIPELINE_SPEC_TEMPLATE.md`

## Table of Contents

- [1. Product Vision](#1-product-vision)
- [2. Capstone Outcomes](#2-capstone-outcomes)
- [3. Current Repository Baseline](#3-current-repository-baseline)
- [4. Data Contracts](#4-data-contracts)
- [5. Architecture Requirements](#5-architecture-requirements)
- [6. AI Agent Requirements](#6-ai-agent-requirements)
- [7. API and UI Requirements](#7-api-and-ui-requirements)
- [8. Reliability and Security Requirements](#8-reliability-and-security-requirements)
- [9. Testing and Evaluation Requirements](#9-testing-and-evaluation-requirements)
- [10. Delivery Roadmap](#10-delivery-roadmap)
- [11. Open Decisions](#11-open-decisions)
- [12. Approval Gate](#12-approval-gate)

## 1. Product Vision

ShopEnsemble AI is a multi-agent e-commerce assistant that helps shoppers discover products, compare prices and features, understand reviews, and obtain grounded answers about store policies through conversational and modular UI experiences.

The system must prefer verified catalog, review, and policy data over invented facts. AI components provide interpretation and summarization; deterministic application services own retrieval, validation, filtering, comparison, and persistence.

## 2. Capstone Outcomes

- Typed data models and validated data ingestion.
- Reliable catalog, review, and policy persistence.
- Natural-language product discovery and recommendation.
- Product and price comparison.
- Review sentiment analysis and summarization.
- Policy and FAQ question answering grounded in store data.
- Coordinator and specialized AI agents with validated contracts.
- FastAPI API integration.
- Streamlit or Gradio UI integration.
- Evaluation dataset and measurable quality checks.
- Deployment-ready documentation and security controls.

## 3. Current Repository Baseline

- `app/models.py`: Pydantic v2 domain models for products, reviews, and policies.
- `app/pipeline/persistence.py`: planned PostgreSQL persistence boundary using SQLAlchemy 2.x and `asyncpg`; implementation is not started.
- `data/`: source CSV datasets.
- `tests/test_models.py`: model validation suite; existing model tests pass.
- `requirements.txt`: Python 3.12 note plus FastAPI, Uvicorn, Pydantic, OpenAI, pandas, python-dotenv, SQLAlchemy, asyncpg, Streamlit, LangChain, and pytest.
- Database direction: PostgreSQL with SQLAlchemy 2.x and `asyncpg`; policy conditions use `JSONB`; `pgvector` is optional for semantic search.
- `Reference/Learning/`: Pydantic/data-modeling and Python/uv/pip learning references.
- `specs/1_data-pipeline/data_pipeline_shopensemble_spec.md`: detailed ingestion, ETL, and persistence requirements.
- `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md`: detailed coordinator/sub-agent architecture, routing, and roadmap (Phases 1-4).
- `memory-bank/shopEnsembleProjectRequirements.md`: durable whole-project reference for future sessions.

## 4. Data Contracts

### Products

- Source: `data/products.csv`.
- 2,000 UTF-8 CSV rows.
- Columns: `id,name,brand,category,price,description,stock,rating`.
- Categories: `laptop`, `smart_tv`, `smartphone`, `speaker`.
- Valid ID prefixes: `LP`, `SP`, `SPK`, `TV` followed by four digits.
- Price range observed: `50.23` to `2998.95`.
- Stock range observed: `0` to `200`.
- Rating range observed: `0.0` to `5.0`.

### Reviews

- Source: `data/reviews.csv`.
- 4,000 UTF-8 CSV rows.
- Columns: `product_id,rating,text,date`.
- Product references currently resolve to catalog IDs.
- Dates are ISO dates from `2024-08-26` to `2025-02-22`.
- Ratings observed range from `2.0` to `5.0`.

### Policies

- Source: `data/store_policies.csv`.
- 22 UTF-8 CSV rows.
- Columns: `policy_type,description,conditions,timeframe`.
- Policy types: `exchanges`, `financing`, `preorder`, `price_matching`, `repairs`, `returns`, `shipping`, `warranty`.
- `conditions` is pipe-delimited and becomes `list[str]`.
- `timeframe=0` is valid when duration does not apply.

The existing `StorePolicy` implementation must be reconciled with these eight types and non-negative timeframe semantics before policy ingestion or policy-agent work.

## 5. Architecture Requirements

```text
Source data and external sources
    -> safe ingestion and normalization
    -> Pydantic domain models
    -> persistence and retrieval services
    -> deterministic domain tools
    -> specialized agents
    -> coordinator agent
    -> FastAPI API
    -> Streamlit/Gradio UI
```

Recommended boundaries:

- `app/models.py`: domain and agent contracts.
- `app/pipeline/paths.py`: file paths and allowed-root checks.
- `app/pipeline/ingestion.py`: parsing, headers, and source metadata.
- `app/pipeline/etl.py`: normalization, validation, transformation, batching, quarantine.
- `app/pipeline/persistence.py`: PostgreSQL/SQLAlchemy async client, indexes, writes, retries, verification.
- `app/pipeline/orchestrator.py`: orchestration, dry runs, reporting, exit status.
- `app/agents/`: coordinator and specialized agents/tools.
- `app/api/`: FastAPI application and routers.
- `app/ui/`: Streamlit or Gradio interface.
- `tests/`: unit, integration, contract, and evaluation tests.

No module should combine file parsing, persistence, business rules, and LLM orchestration without an explicit reason.

## 6. AI Agent Requirements

### Coordinator

- Receives all customer queries.
- Classifies intent and delegates to specialized tools or agents.
- Returns a Pydantic-validated response.
- Does not fabricate catalog, review, price, or policy facts.

### Specialized capabilities

- Product recommendation and search.
- Review analysis and summarization.
- Price and feature comparison.
- Store policy and FAQ handling.

Every agent and tool must define typed input/output models, explicit error behavior, grounding/source metadata where possible, and deterministic service dependencies outside the LLM layer.

## 7. API and UI Requirements

### API

- FastAPI health endpoint.
- Customer query endpoint routed to the coordinator agent.
- Separate request and response models where lifecycle or authorization differs.
- Clear validation errors without leaking internals.
- Contract tests before deployment.

### UI

Use modular navigation for:

- Product recommendations/search.
- Product comparison.
- Review summaries and sentiment insights.
- Policy/FAQ assistant.
- Conversational shopping assistant.

The UI should expose usable workflows rather than only a marketing or explanatory screen.

## 8. Reliability and Security Requirements

- Resolve paths with `pathlib.Path` and validate allowed roots.
- Treat missing values, empty strings, NaN, infinity, and sentinel tokens explicitly.
- Stream or chunk input; initial pipeline recommendation is 500 records per batch.
- Classify, quarantine, count, and report invalid records.
- Make retries bounded and writes idempotent.
- Do not claim persistence success until confirmed by the destination.
- Keep API, database, and OpenAI credentials in environment/secrets management.
- Never log secrets or full sensitive records.
- Bound LLM calls by timeout, retry, token, and cost policies.
- Treat retrieved external content as untrusted.
- Add rate limiting and abuse controls before public deployment.
- Review dataset licensing and privacy before external release.

## 9. Testing and Evaluation Requirements

Required test areas:

- `tests/test_models.py` for Pydantic contracts.
- `tests/pipeline/test_paths.py` and `tests/pipeline/test_ingestion.py` for paths, headers, parsing, and source errors.
- `tests/pipeline/test_etl.py` for normalization, validation, transformations, NaN/infinity, and quarantine.
- `tests/pipeline/test_persistence.py` for persistence behavior with mocked external clients.
- `tests/pipeline/test_orchestrator.py` for orchestration, dry runs, retries, and reports.
- API contract tests after routes exist.
- Agent/tool contract tests with deterministic fixtures.
- LLM evaluation dataset for policy/FAQ and at least one additional capability.

Use `test-suite-generator` before creating each suite. Present the plan first, triage failures, do not weaken assertions, and append results to `.agents/memory-bank/testGenerationLog.md`.

## 10. Delivery Roadmap

1. **Week 1:** Environment, repository, architecture, documentation, Python/uv, Pydantic, agents, FastAPI.
2. **Week 2:** Domain models, data contracts, sample database, ingestion specification.
3. **Week 3:** Coordinator and review analysis/summarization agent with first tool.
4. **Week 4:** Recommendation, comparison, and policy/FAQ agents.
5. **Week 5:** Evaluation dataset/script and prompt/system tuning.
6. **Week 6:** FastAPI query routing and deployment preparation.
7. **Week 7:** Streamlit or Gradio UI, scalability checks, API performance.
8. **Week 8:** Refinement, technical documentation, deployment checks, presentation.

## 11. Open Decisions

1. Confirm the selected PostgreSQL persistence target, schema, migrations, and deployment configuration.
2. Reconcile and update `StorePolicy` to match all source policy types.
3. Confirm invalid-row threshold for future non-curated data.
4. ~~Define agent framework and orchestration boundaries; use LangChain only where justified.~~ Resolved: **PydanticAI**, Supervisor/Orchestrator pattern. See `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` (Appendix A) for rationale.
5. Select first deployment target: Hugging Face, AWS, GCP, Azure, Netlify, or another approved target.
6. Decide whether DOCX references should be converted into version-controlled Markdown.
7. Define run-report and quarantine storage.
8. Decide whether checkpoint/resume is needed for current dataset sizes.

## 12. Approval Gate

Before production implementation begins:

- [ ] This project requirements document is reviewed and approved.
- [ ] The data-pipeline specification is reviewed and approved.
- [ ] The data-model specification is reconciled with all observed source records.
- [ ] Persistence target and schema are selected.
- [ ] Agent/API/UI scope for the next milestone is selected.
- [ ] Test plans are approved before new test files are generated.
