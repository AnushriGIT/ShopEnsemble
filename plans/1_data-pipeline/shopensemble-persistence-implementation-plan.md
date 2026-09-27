# ShopEnsemble Pipeline: Phase 4 (Persistence Integration) + Phase 5 (Full-Run Orchestration)

**Status:** ✅ Implemented and verified (2026-09-13) — 56/56 tests passing, real end-to-end run against PostgreSQL confirmed idempotent via both pytest and direct CLI invocation
**Generated from:** `skills/SpecToolBox/3_FULL_DATA_PIPELINE_SPEC_TEMPLATE.md` (generic sections 4.3 Mode 2, 6.4 Phase 4, 6.5 Phase 5, 7.2)
**Governing spec:** [specs/1_data-pipeline/data_pipeline_shopensemble_spec.md](../../specs/1_data-pipeline/data_pipeline_shopensemble_spec.md)
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (v3 entry)

## Implementation Notes (added post-implementation)

- Two gaps were discovered only once real DB connections were attempted (not predictable from static analysis alone): `greenlet` was missing from `requirements.txt` (required by SQLAlchemy's async engine), and this machine's local Homebrew `postgresql@16` service was already bound to `127.0.0.1:5432`, intercepting connections meant for the `docker-compose.yml` container. Worked around with a local `docker-compose.override.yml` remapping the container to host port 5433, rather than touching the system-wide Homebrew service. See `memory-bank/shopEnsembleDataPipeline.md` → "Local Environment Notes".
- One test-ordering bug was found and fixed during verification: `test_create_schema_declares_exactly_the_three_domain_tables` initially depended only on `db_engine` (not `clean_schema`), so it silently relied on another test having already created the schema. Fixed by depending on `clean_schema` explicitly. Full suite re-run twice after the fix to rule out order-flakiness.
- All "Decisions confirmed with user" below were implemented as agreed: `tenacity` for retry, JSON report/quarantine files on disk.

## Context

The ShopEnsemble pipeline currently only validates data (`run_dry_run()` in `app/pipeline/orchestrator.py`) — it reads all 3 CSVs (2,000 products / 4,000 reviews / 22 policies), normalizes, validates, batches, and reports, but **never writes to PostgreSQL**. This is Phase 1-3 of `skills/SpecToolBox/3_FULL_DATA_PIPELINE_SPEC_TEMPLATE.md` and it's complete and tested (42 passing tests).

The persistence layer (`app/pipeline/persistence.py`) already has working schema definitions and upsert logic (`create_engine`, `create_schema`, `persist_batch`) — but it has **zero tests against a real database**, no retry logic (only a placeholder `retries: int = 0` field), and nothing calls it end-to-end. There is no `run_full_pipeline()` anywhere, despite being referenced throughout `specs/1_data-pipeline/shopensemble-implementation-guide.md` and `.env.example` (`SHOPENSEMBLE_BATCH_SIZE`, `SHOPENSEMBLE_MAX_INVALID_ROWS`, `SHOPENSEMBLE_REPORT_ROOT`, `SHOPENSEMBLE_QUARANTINE_ROOT` are all declared but read by no code).

This plan closes that gap: picking up exactly where the project's own `Reference/Learning/PipelineImplementSteps.md` §16 "Remaining Work" and `memory-bank/shopEnsembleDataPipeline.md`'s open decisions left off — implement Phase 4 (Persistence Integration, template §6.4) and Phase 5 (Full-Run Orchestration, template §6.5/§7.2), using the already-running local Postgres (`docker-compose.yml`, `postgres:16-alpine`).

**Decisions confirmed with user:**
- Resolve spec Open Decision #6 (run-report/quarantine storage location) now: write one JSON report + one JSON quarantine file per run to `reports/`/`quarantine/` (already `.gitignore`d, matches `.env.example`'s `SHOPENSEMBLE_REPORT_ROOT`/`SHOPENSEMBLE_QUARANTINE_ROOT`).
- Retry/backoff uses the **`tenacity`** library (not hand-rolled), added to `requirements.txt`.
- Open Decision #7 (checkpoint/resume) stays explicitly **not implemented** — documented rationale in code: at 6,022 total rows, `persist_batch`'s upsert/on-conflict-do-nothing already makes reruns idempotent and cheap.

Do not modify `persistence.py`'s existing schema/upsert SQL, `etl.py`, `ingestion.py`, `paths.py`, or `app/models.py` — all already correct and tested. This is additive work on top of working code.

---

## Design

### Status vocabulary
`PipelineRunReport.status` currently becomes `"dry_run"` or `"failed"`. The new full-run path uses `"success"` or `"failed"` — together these are exactly the 3 values the spec (`1_data-pipeline/data_pipeline_shopensemble_spec.md` §10) requires (`success`, `failed`, `dry_run`). No renaming of the existing dry-run values (keeps `tests/pipeline/test_orchestrator.py` passing unchanged).

### Shared validation phase (avoid duplicating ~90 lines)
Extract the existing body of `run_dry_run()` (load/validate products → extract product IDs → load/validate reviews with referential check → load/validate policies) into a private helper `_run_validation_phase(data_root, batch_size, max_invalid_rows, report) -> _ValidatedBatches`. `run_dry_run()` becomes a thin wrapper calling this helper then `report.finish("dry_run")`. `run_full_pipeline()` calls the same helper, then persists. **Do this refactor first and re-run `test_orchestrator.py` unchanged as a checkpoint** before adding anything new.

### Failure → report handoff
Today a failed `run_dry_run()` re-raises `ValueError` and the caller loses the quarantine detail. Attach the report to the exception before re-raising (both functions): `error.pipeline_report = report`. This lets `app/main.py` write the quarantine dump even on failure, without changing the exception type (existing `pytest.raises(ValueError, match="threshold exceeded")` test still passes).

### Retry mechanism — `tenacity`
Add `tenacity` to `requirements.txt`. In `persistence.py`, wrap only the transient-failure case: retry on `sqlalchemy.exc.OperationalError` (connection refused, pool timeout, disconnects — matches spec §7's error table), never on `IntegrityError`/`ProgrammingError`/other exceptions (those are data or programming errors, re-raise immediately). Use `tenacity.AsyncRetrying` with `stop_after_attempt(max_retries + 1)`, `wait_exponential_jitter(initial=backoff_base_seconds, max=backoff_max_seconds)`, `retry_if_exception_type(OperationalError)`, `reraise=True`. A fresh session/transaction is opened per attempt (a session that failed mid-flush shouldn't be reused).

### `run_full_pipeline()` engine lifecycle
Accepts an optional `engine: AsyncEngine | None` parameter. When omitted, creates its own engine from `database_url` (or `SHOPENSEMBLE_DATABASE_URL`/default) and disposes it before returning. When the caller passes one in (tests), the caller owns disposal. Keeps `orchestrator.py` a pure composition layer per spec §11 ("do not combine file reading, business transformation, and database writes in one function") — it only calls `persistence.py` functions, never touches SQLAlchemy sessions directly.

---

## Files to change

### 1. `requirements.txt`
Add two lines: `pytest-asyncio`, `tenacity`.

### 2. `pyproject.toml` (new file)
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires a live PostgreSQL instance (docker compose up -d postgres)",
]
```
First config file in the project — chosen over `pytest.ini`/`setup.cfg` since it's the natural single consolidation point for future config (ruff, packaging).

### 3. `app/pipeline/persistence.py` (additive only — do not touch existing `Base`/`ProductRecord`/`ReviewRecord`/`StorePolicyRecord`/`create_engine`/`create_session_factory`/`create_schema`/`persist_batch`)
Add:
- `RetryStats` dataclass: `retries: int`, `latency_seconds: float`.
- `async def persist_batch_with_retry(session_factory, products=(), reviews=(), policies=(), *, max_retries=3, backoff_base_seconds=0.5, backoff_max_seconds=8.0) -> RetryStats` — wraps `persist_batch` with `tenacity.AsyncRetrying` as described above, opening one session+transaction per attempt, tracking attempt count and elapsed time.

### 4. `app/pipeline/orchestrator.py`
- Add `_ValidatedBatches` dataclass (`products`, `reviews`, `policies`, each `list[list[...]]` of validated Pydantic models) and extract `_run_validation_phase(...)` from `run_dry_run`'s current body (pure refactor, verify `test_orchestrator.py` still passes unchanged before proceeding).
- Add fields to `PipelineRunReport`: `batch_count: int = 0`, `persistence_latency_seconds: float = 0.0` (spec §10 requires reporting these); `retries` field already exists, now actually populated.
- Attach `error.pipeline_report = report` in both functions' except blocks before re-raising.
- Add `async def run_full_pipeline(data_root=None, database_url=None, batch_size=500, max_invalid_rows=0, max_retries=3, backoff_base_seconds=0.5, backoff_max_seconds=8.0, engine=None) -> PipelineRunReport`: runs `_run_validation_phase`, then for products/reviews/policies in order, creates schema once, persists each batch via `persist_batch_with_retry`, accumulates `rows_persisted`, `batch_count`, `retries`, `persistence_latency_seconds`, finishes with `"success"`/`"failed"`. Import `create_engine`, `create_schema`, `create_session_factory`, `persist_batch_with_retry` from `app.pipeline.persistence`.

### 5. `app/main.py` (new file)
CLI entry point. Reads the 4 currently-unused env vars (`SHOPENSEMBLE_BATCH_SIZE`, `SHOPENSEMBLE_MAX_INVALID_ROWS`, `SHOPENSEMBLE_REPORT_ROOT` default `reports`, `SHOPENSEMBLE_QUARANTINE_ROOT` default `quarantine`) — does **not** re-read `SHOPENSEMBLE_DATA_ROOT`/`SHOPENSEMBLE_DATABASE_URL` since `paths.py`/`persistence.py` already read those internally. Calls `load_dotenv()` (package already in `requirements.txt`, just unused today) so local `.env` values apply. Calls `run_full_pipeline()`, writes `reports/<run_id>.json` (report minus the verbose `quarantine` list) and `quarantine/<run_id>.json` (the quarantine records) via `dataclasses.asdict` + `json.dumps` — writes these even on failure using `error.pipeline_report`. `main()` prints a one-line summary and returns exit code 0/1. `if __name__ == "__main__": raise SystemExit(main())`.

### 6. `tests/conftest.py` (new file)
Shared fixtures: `database_url` (session-scoped, reads `SHOPENSEMBLE_DATABASE_URL`/default), `postgres_available` (cheap TCP probe against the configured host:port so DB tests skip cleanly instead of hanging when Postgres isn't running), `db_engine` (async, skips via `pytest.skip(...)` if unavailable), `clean_schema` (drop-all + create-all before each test, drop-all after), `db_session_factory`. No new CSV-fixture abstraction — keep using inline `tmp_path` like the existing tests.

### 7. `tests/pipeline/test_persistence.py` (existing file — add tests, don't touch existing 4)
Add mocked (no live DB) tests for `persist_batch_with_retry`: recovers after N transient `OperationalError`s then succeeds; fails after exhausting `max_retries`; does *not* retry on non-`OperationalError` exceptions (assert zero sleep calls).

### 8. `tests/pipeline/test_persistence_integration.py` (new file, `@pytest.mark.integration`, uses conftest fixtures)
Schema creates exactly 3 tables; product upsert overwrites in place; review FK violation raises and rolls back to 0 rows; duplicate review is a no-op; policy JSONB upsert replaces `conditions`; mid-batch failure rolls back the whole transaction; identical batch persisted twice stays at the same row count (idempotent rerun — direct test of spec §9's "rerunnable without creating duplicates").

### 9. `tests/pipeline/test_full_pipeline.py` (new file, `@pytest.mark.integration`)
End-to-end against real `data/` CSVs: `run_full_pipeline()` returns `status="success"`, `rows_persisted == {"products": 2000, "reviews": 4000, "policies": 22}`, `batch_count > 0`; rerun is idempotent (same counts, no errors); a validation failure (reused threshold-exceeded tmp-CSV pattern from `test_orchestrator.py`) raises `ValueError` with `error.pipeline_report.status == "failed"` and leaves the DB untouched; passing an explicit `engine=` leaves it undisposed after the call.

### 10. `.agents/memory-bank/testGenerationLog.md`
Append a `v3` entry per the existing convention (Target source, Generated tests, Discovery, Coverage rationale, Mocks, execution results, Triage, Committed) covering the new persistence/full-pipeline tests, following the `test-suite-generator` skill workflow before generating them.

---

## Order of implementation

1. `requirements.txt` + `pyproject.toml`.
2. `persistence.py`: `RetryStats` + `persist_batch_with_retry` (additive).
3. `test_persistence.py`: mocked retry tests — run these first, no DB needed.
4. `tests/conftest.py`: DB fixtures.
5. `docker compose up -d postgres`, wait healthy; `test_persistence_integration.py`.
6. `orchestrator.py`: extract `_run_validation_phase`; re-run existing `test_orchestrator.py` to confirm zero behavior drift.
7. `orchestrator.py`: add report fields, exception attribute, `run_full_pipeline`.
8. `test_full_pipeline.py`.
9. `app/main.py`; manually run the full runbook once against real Postgres.
10. Append `testGenerationLog.md` v3 entry.

## Verification

```bash
# Fast subset, no DB required
.venv/bin/python -m pytest -q -m "not integration"

# Start Postgres, run full suite including integration tests
docker compose up -d postgres
until [ "$(docker compose ps postgres --format '{{.Health}}')" = "healthy" ]; do sleep 1; done
.venv/bin/python -m pytest -q

# Run the full pipeline end-to-end via the new CLI entry point
.venv/bin/python -m app.main
# Expect: "Run shopensemble-... finished with status=success" and rows_persisted counts

# Verify in Postgres directly
docker compose exec postgres psql -U shopensemble -d shopensemble -c "SELECT COUNT(*) FROM products;"
docker compose exec postgres psql -U shopensemble -d shopensemble -c "SELECT COUNT(*) FROM reviews;"
docker compose exec postgres psql -U shopensemble -d shopensemble -c "SELECT COUNT(*) FROM store_policies;"
# Expect: 2000, 4000, 22

# Inspect the written report/quarantine JSON
cat reports/<run_id>.json
cat quarantine/<run_id>.json   # should be an empty array

# Rerun to confirm idempotency (no duplicate rows, no errors)
.venv/bin/python -m app.main

docker compose down -v
```

## Out of scope (unchanged from earlier discussion)
Alembic migrations, pgvector, FastAPI routes, UI work — all explicitly deferred per `Reference/Learning/PipelineImplementSteps.md` §16. The `.env` OpenAI key is a pre-existing, unrelated concern, not addressed here.
