# ShopEnsemble Data Pipeline Requirements

**Status:** Project-specific draft for review before implementation  
**Generated from:** the standard data-pipeline requirements spec template  
**Project:** ShopEnsemble  
**Python:** 3.12  
**Primary sources:** `data/products.csv`, `data/reviews.csv`, `data/store_policies.csv`

## Table of Contents

- [1. Purpose and Workflow](#1-purpose-and-workflow)
- [2. Current Repository Context](#2-current-repository-context)
- [3. Source Inventory and Observed Contracts](#3-source-inventory-and-observed-contracts)
- [4. Canonical Domain Records](#4-canonical-domain-records)
- [5. Path Resolution and File Safety](#5-path-resolution-and-file-safety)
- [6. Ingestion and Normalization](#6-ingestion-and-normalization)
- [7. Validation Error Strategy](#7-validation-error-strategy)
- [8. Batching and Resource Limits](#8-batching-and-resource-limits)
- [9. Persistence Requirements](#9-persistence-requirements)
- [10. Observability and Run Report](#10-observability-and-run-report)
- [11. Implementation Boundaries](#11-implementation-boundaries)
- [12. Required Test Suite](#12-required-test-suite)
- [13. Gherkin Acceptance Scenarios](#13-gherkin-acceptance-scenarios)
- [14. Open Decisions Requiring Approval](#14-open-decisions-requiring-approval)
- [15. Acceptance Checklist](#15-acceptance-checklist)

---

## 1. Purpose and Workflow

This document is the ShopEnsemble-specific requirements contract for file ingestion, validation, transformation, and persistence. It is the implementation input only after review and approval.

Required sequence:

```text
This approved requirements document
    -> ingestion implementation
    -> ETL/transformation implementation
    -> persistence implementation
    -> focused tests
    -> complete verification
```

The current task is specification only. Do not implement pipeline code until unresolved decisions in Section 14 are approved.

## 2. Current Repository Context

### Existing modules

- `app/models.py`: Pydantic v2 models for `Product`, `Review`, and `StorePolicy`.
- `app/pipeline/persistence.py`: planned persistence boundary; implementation is not started.
- `tests/test_models.py`: model validation tests.
- `requirements.txt`: includes FastAPI, Uvicorn, Pydantic, OpenAI, pandas, python-dotenv, SQLAlchemy, asyncpg, Streamlit, LangChain, and pytest.

### Reference documentation

- `Reference/Learning/Pydantic-Data-Modeling-Interview-Tutorial.md`: Pydantic v2, validation, serialization, FastAPI boundaries, and Gherkin/BDD guidance.
- `Reference/Learning/Python-uv-pip-Cheatsheet.md`: Python 3.12, virtual environment, `uv`, package, test, and lint commands.
- `Reference/Learning/ShopEnsemble-Database-Selection.md`: database-selection reasoning, PostgreSQL, SQLAlchemy, `asyncpg`, `JSONB`, and optional `pgvector`.
- `Reference/ShopEnsemble AI Problem Statement.docx`: intended product and assistant context; confirm extracted requirements before using them as a data contract.
- `Reference/ShopEnsemble Assistant _ 8 - Week Milestone.docx`: milestone context; confirm extracted requirements before treating them as pipeline behavior.
- `specs/1_data-pipeline/shopensemble-data-models.md`: current data-model contract; it requires reconciliation with the broader policy CSV values documented below.

The existing `memory-bank/projectDocs.md` contains StyleLens/DeepFashion material that is unrelated to this ShopEnsemble CSV pipeline. It must not be treated as authoritative ShopEnsemble pipeline requirements.

## 3. Source Inventory and Observed Contracts

| Source | Format | Encoding | Delimiter | Rows | Columns |
| :--- | :--- | :--- | :--- | ---: | :--- |
| `data/products.csv` | CSV | UTF-8 | `,` | 2,000 | `id,name,brand,category,price,description,stock,rating` |
| `data/reviews.csv` | CSV | UTF-8 | `,` | 4,000 | `product_id,rating,text,date` |
| `data/store_policies.csv` | CSV | UTF-8 | `,` | 22 | `policy_type,description,conditions,timeframe` |

### Products

- Categories observed: `laptop`, `smart_tv`, `smartphone`, `speaker`.
- Product ID prefixes observed: `LP`, `SP`, `SPK`, `TV`.
- Product IDs are unique: 2,000 unique IDs.
- Price range observed: `50.23` through `2998.95`.
- Stock range observed: `0` through `200`.
- Rating range observed: `0.0` through `5.0`.
- No blank values were observed during profiling.

### Reviews

- Rating range observed: `2.0` through `5.0`.
- Dates range from `2024-08-26` through `2025-02-22` in ISO format.
- No duplicate complete rows were observed.
- Every review `product_id` refers to an existing product ID; no orphan references were observed.
- No blank values were observed during profiling.

### Store policies

- Policy types observed: `exchanges`, `financing`, `preorder`, `price_matching`, `repairs`, `returns`, `shipping`, `warranty`.
- All 22 rows contain pipe-delimited conditions.
- Timeframe range is `0` through `730`.
- `timeframe=0` is used for policy types where a duration does not apply, including shipping, price matching, repairs, financing, and preorder entries.
- No blank values were observed during profiling.

## 4. Canonical Domain Records

### Product

| Field | Canonical type | Required | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | `str` | Yes | `^[A-Z]{2,3}[0-9]{4}$`; accepts `SP0001` and `SPK0441` |
| `name` | `str` | Yes | Strip whitespace; length 1-200 |
| `brand` | `str` | Yes | Strip whitespace; length 1-100 |
| `category` | `str` | Yes | One observed category or documented future extension; lowercase identifier format |
| `price` | `Decimal` | Yes | Greater than 0 |
| `description` | `str` | Yes | Strip whitespace; length 1-1000 |
| `stock` | `int` | Yes | Greater than or equal to 0 |
| `rating` | `float` | Yes | Inclusive range 0-5 |

### Review

| Field | Canonical type | Required | Constraints |
| :--- | :--- | :--- | :--- |
| `product_id` | `str` | Yes | Same product ID contract as `Product.id` |
| `rating` | `float` | Yes | Inclusive range 0-5 |
| `text` | `str` | Yes | Strip whitespace; length 1-2000 |
| `date` | `date` | Yes | Parse ISO `YYYY-MM-DD` |

### Store policy

| Field | Canonical type | Required | Constraints |
| :--- | :--- | :--- | :--- |
| `policy_type` | `str` or enum | Yes | One of the eight observed policy types |
| `description` | `str` | Yes | Strip whitespace; length 1-300 |
| `conditions` | `list[str]` | Yes | Split source value on `|`; each item must be non-empty after stripping |
| `timeframe` | `int` | Yes | Greater than or equal to 0; zero means not applicable |

### Existing model reconciliation requirement

The `app/models.py` `StorePolicy` model now accepts all eight observed policy types and `timeframe >= 0`, with regression tests for zero-duration policies.

## 5. Path Resolution and File Safety

- Resolve the repository root from configuration or a deterministic project-root discovery strategy.
- Use `pathlib.Path`, not string concatenation, for paths.
- Default source root is the project-relative `data/` directory; do not hardcode a developer-specific absolute path.
- Resolve paths before opening them and verify they remain inside the configured source root.
- Reject missing paths, directories supplied as files, symlink escapes, and path traversal.
- Configuration should support an environment override such as `SHOPENSEMBLE_DATA_ROOT` while retaining a clearly documented project-relative default.
- Tests must use temporary directories or project-relative fixtures, never a machine-specific absolute path.

## 6. Ingestion and Normalization

Use a streaming or chunked CSV reader. The implementation may use Python `csv.DictReader` or pandas chunking, but the selected approach must be documented and tested.

For every source:

1. Open as UTF-8 with newline handling appropriate for CSV.
2. Verify the exact expected header set before processing rows.
3. Preserve source row number and source filename in validation errors.
4. Strip string fields before validation.
5. Convert products `price` to `Decimal`, `stock` to `int`, and numeric ratings to `float`.
6. Convert review `date` from ISO text to `datetime.date`.
7. Split policy `conditions` on `|`, strip each item, and reject empty resulting conditions.
8. Validate normalized records with the Pydantic models.

### Missing, NaN, and infinity policy

- Empty strings and whitespace-only values in required fields: reject and quarantine the row.
- CSV null tokens such as `NA`, `N/A`, `NULL`, or `-`: no such tokens are currently observed; reject them in required fields unless a future spec revision explicitly permits them.
- NaN, positive infinity, and negative infinity: reject and quarantine for numeric fields.
- Do not serialize or persist NaN or infinity.
- Report counts by source, field, and error class.

## 7. Validation Error Strategy

Classify failures as follows:

| Error | Behavior |
| :--- | :--- |
| Missing or invalid configuration | Fail before reading files |
| Missing or extra CSV columns | Reject the entire source file |
| Malformed CSV row | Quarantine row with source and row number |
| Pydantic/domain validation error | Quarantine row and continue until threshold is exceeded |
| Orphan review product ID | Quarantine row; current source profile expects zero |
| Persistence connection failure | Retry bounded transient failures; fail run after exhaustion |
| Duplicate destination key | Upsert or fail according to the approved persistence design |
| Unexpected programming error | Fail loudly with run ID and traceback |

Initial policy recommendation:

- Maximum invalid rows: `0` for the current curated datasets.
- Maximum invalid ratio: `0%`.
- Any invalid row causes the run to fail after writing a quarantine report; do not silently produce a partial success.
- Quarantine records must include source file, row number, stable key where available, sanitized raw values, error type, error message, and run ID.

This threshold may be relaxed only through an explicit project-spec revision.

## 8. Batching and Resource Limits

- Process records incrementally; do not load unbounded source data into memory.
- Initial recommended batch size: 500 records, configurable through `SHOPENSEMBLE_BATCH_SIZE`.
- Validate a complete batch before persistence.
- Record accepted, rejected, and persisted counts per batch.
- Retry transient persistence failures with bounded exponential backoff.
- Use stable keys to make retries idempotent.
- Provide a dry-run mode that parses, validates, transforms, and reports without persistence.
- Add checkpoints only if the selected destination and pipeline volume require resumable runs; document the checkpoint key before implementation.

## 9. Persistence Requirements

The first persistence target is **PostgreSQL**. This is a project decision based on the data relationships and expected query patterns, not on the current dependency list.

### Why PostgreSQL

- Products and reviews have a clear relationship requiring referential integrity.
- Expected queries require filtering, sorting, joins, uniqueness, and aggregations.
- PostgreSQL provides transactions, constraints, indexes, and mature reporting/query support.
- Policy conditions are structured but can be stored as `JSONB` without making the entire system document-oriented.
- Optional semantic search can use `pgvector` beside structured records rather than introducing a separate vector database.

### Tradeoffs and boundary

- MongoDB may be useful later for flexible agent traces or conversation documents.
- PostgreSQL still requires explicit indexes, constraints, migrations, and reconciliation.
- The database choice must be revisited if the dominant workload changes or deployment constraints favor another system.

### Access and storage choices

- **Python access layer:** SQLAlchemy 2.x with the asynchronous `asyncpg` driver.
- **Policy conditions:** PostgreSQL `JSONB` array after splitting and validating the source pipe-delimited value.
- **Semantic search:** Optional `pgvector` extension for product, review, or policy embeddings after structured retrieval is working.

Before implementation, define:

- Target collections/tables/files for products, reviews, and policies.
- Primary and unique keys.
- Upsert versus append behavior.
- Decimal representation compatible with the selected destination.
- Transaction or batch atomicity behavior.
- Duplicate and retry behavior.
- Verification query or reconciliation step after writes.
- Migration and cleanup strategy.

Persistence MUST not claim success until the destination confirms the write. The pipeline must be rerunnable without creating duplicate products or reviews.

## 10. Observability and Run Report

Every run must generate a run ID and report:

- Start/end time and duration.
- Source files and resolved paths.
- Rows read, accepted, rejected, quarantined, and persisted.
- Batch count, retry count, and persistence latency.
- Missing, NaN, infinity, duplicate, orphan, and validation-error counts.
- Final status: `success`, `failed`, or `dry_run`.

Logs must not expose secrets or dump complete sensitive rows. Include source filename, row number, field, and stable key where safe.

## 11. Implementation Boundaries

Initial implementation should be separated into testable responsibilities:

- `app/pipeline/paths.py`: safe path resolution and allowed-root checks.
- `app/pipeline/ingestion.py`: file reading, header checks, and raw row iteration.
- `app/pipeline/etl.py`: normalization, Pydantic validation, transformations, error classification, and batch preparation.
- `app/pipeline/persistence.py`: SQLAlchemy async engine/session, PostgreSQL indexes, batch writes, retries, and persistence verification.
- `app/pipeline/orchestrator.py`: orchestration, dry-run mode, run reporting, and exit status.

Do not combine file reading, business transformation, and database writes in one function.

## 12. Required Test Suite

Use pytest and follow the existing `tests/test_models.py` convention. Add:

- `tests/pipeline/test_paths.py`
- `tests/pipeline/test_ingestion.py`
- `tests/pipeline/test_etl.py`
- `tests/pipeline/test_persistence.py`
- `tests/pipeline/test_orchestrator.py`

Use real small temporary CSV fixtures for parser and path behavior. Mock SQLAlchemy/PostgreSQL connections and other external persistence boundaries. Do not mock pure normalization, validation, or deterministic transformations.

Required coverage:

- Exact headers, UTF-8 parsing, malformed rows, empty files, missing files, and path traversal.
- All four product ID prefixes, including `SPK####`.
- Product/review numeric and date conversions.
- All eight policy types and `timeframe=0`.
- Pipe-delimited policy conditions.
- Empty values, null tokens, NaN, infinity, and invalid numeric/date values.
- Orphan review references and duplicate keys.
- Batch boundaries, dry-run behavior, retry behavior, and idempotent reruns.
- Persistence success, duplicate/upsert behavior, transient failures, permanent failures, and verification.
- Run metrics and sanitized quarantine output.

Before generating tests, apply the project's standard test-generation workflow, present the test plan for approval, run focused tests first, triage failures, and record the result in `.agents/memory-bank/testGenerationLog.md`.

## 13. Gherkin Acceptance Scenarios

### Scenario: Ingest all valid products

Given the UTF-8 `products.csv` file with the documented eight columns
When the pipeline reads and validates every row
Then all 2,000 product records are accepted
And product IDs are unique
And the `SP`, `LP`, `TV`, and `SPK` prefixes are accepted

### Scenario: Ingest speaker product IDs

Given a product row with ID `SPK0441`
When the row is normalized and validated
Then the product is accepted
And its name `ClearSound` is preserved after whitespace normalization

### Scenario: Reject invalid numeric values

Given a product row with NaN, infinity, a negative stock value, or a non-positive price
When the row is normalized and validated
Then the row is quarantined
And the run report identifies the field and error class

### Scenario: Ingest policy records with no duration

Given a shipping or price-matching policy with timeframe `0`
When the row is normalized and validated
Then the row is accepted
And timeframe zero is preserved as not applicable

### Scenario: Reject orphan reviews

Given a review whose `product_id` is absent from the product key set
When referential validation runs
Then the review is quarantined
And the current curated-data run fails because the invalid-row threshold is zero

## 14. Open Decisions Requiring Approval

1. Confirm PostgreSQL as the first persistence target, including connection configuration, tables, indexes, migrations, and deployment environment.
2. Confirm whether the existing `StorePolicy` model should be expanded to all eight observed policy types and `timeframe >= 0` before ingestion work.
3. Confirm whether a zero-invalid-row threshold is appropriate for production ingestion or only for the curated capstone datasets.
4. Confirm whether the DOCX reference documents should be converted to Markdown and treated as authoritative requirements after review.
5. Resolve the unrelated StyleLens content in `memory-bank/projectDocs.md`; it is not a ShopEnsemble pipeline source.
6. Define the run-report and quarantine storage location.
7. Define whether checkpoint/resume support is required for the initial 2,000/4,000/22-row datasets.

## 15. Acceptance Checklist

- [ ] Open decisions are resolved and this spec is approved.
- [ ] Existing Pydantic policy-model mismatch is reconciled.
- [ ] Paths are configuration-driven and traversal-safe.
- [ ] All source headers and observed patterns are tested.
- [ ] Missing, NaN, infinity, and sentinel policies are implemented.
- [ ] Invalid rows are classified, quarantined, counted, and surfaced.
- [ ] Batching and retry behavior are bounded and idempotent.
- [ ] Persistence target, keys, transactions, and verification are documented.
- [ ] Run reports do not expose secrets or sensitive raw records.
- [ ] Focused and complete test suites pass.
- [ ] A versioned implementation/test record is appended to the memory bank.
