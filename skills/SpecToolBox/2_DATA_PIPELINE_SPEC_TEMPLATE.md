# Toolkit Template: File Ingestion, ETL, and Data Persistence

## Template Purpose

This file is a reusable toolkit template. It is not the ShopEnsemble pipeline specification and it is not an implementation input by itself.

Use this template to create a project-specific requirements document at:

```text
specs/data_pipeline_{{PROJECT_NAME}}_spec.md
```

The generated project-specific document becomes the implementation contract only after it has been completed from repository evidence and explicitly reviewed or approved. It is designed to prevent fragile scripts by making data contracts, failure behavior, path handling, batching, validation, and observability explicit.

### Required workflow

1. **Toolkit phase:** Read this template from `skills/SpecToolBox/`. Do not implement production code from the template directly.
2. **Project-spec phase:** Inspect the project's source files, data folder, existing modules, tests, configuration, and persistence target. Replace every `{{PLACEHOLDER}}` with verified project-specific evidence and save the result under `specs/`.
3. **Review phase:** Present the completed project-specific requirements document for review. Resolve missing assumptions, contradictions, and open decisions before implementation.
4. **Implementation phase:** Implement ingestion, ETL, and persistence modules from the approved project-specific document, not from this generic template.
5. **Verification phase:** Generate the required tests from the approved project-specific document, run focused and complete validation, and record the result.

**Implementation rule:** Do not guess a schema, path, nullability rule, batch size, or error policy. If repository evidence is insufficient, record the open question in the generated project-specific document instead of silently choosing a value.

### Naming example for ShopEnsemble

For this repository, the intended artifacts are:

```text
Toolkit:  skills/SpecToolBox/DATA_PIPELINE_SPEC_TEMPLATE.md
Project spec: specs/1_data-pipeline/data_pipeline_shopensemble_spec.md
Implementation: app/pipeline/ingestion.py, app/pipeline/etl.py, app/pipeline/persistence.py
Tests: tests/pipeline/test_ingestion.py, tests/pipeline/test_etl.py, tests/pipeline/test_persistence.py
```

The `specs/1_data-pipeline/data_pipeline_shopensemble_spec.md` file is created from this toolkit after inspecting ShopEnsemble's `data/` files and persistence requirements. It is not an input to create this toolkit; it is the downstream project-specific requirements document produced by it.

## Table of Contents

- [1. Meta and Scope](#1-meta-and-scope)
- [2. Pipeline Overview](#2-pipeline-overview)
- [3. Source File Contract](#3-source-file-contract)
- [4. Path Resolution and File Safety](#4-path-resolution-and-file-safety)
- [5. Schema, Types, and Missing-Value Policy](#5-schema-types-and-missing-value-policy)
- [6. Transformation and ETL Rules](#6-transformation-and-etl-rules)
- [7. Validation Error Strategy](#7-validation-error-strategy)
- [8. Batching, Memory, and Backpressure](#8-batching-memory-and-backpressure)
- [9. Persistence Contract](#9-persistence-contract)
- [10. Configuration and Secrets](#10-configuration-and-secrets)
- [11. Observability and Auditability](#11-observability-and-auditability)
- [12. Required Test Suite](#12-required-test-suite)
- [13. Operational Runbook](#13-operational-runbook)
- [14. Acceptance Criteria](#14-acceptance-criteria)
- [Appendix A: Raw Source Contracts](#appendix-a-raw-source-contracts)
- [Appendix B: Destination Contract](#appendix-b-destination-contract)
- [Appendix C: Decision Log](#appendix-c-decision-log)

When creating a project-specific document, keep this table immediately below the document metadata and update it whenever headings change.

---

## 1. Meta and Scope

- **Project:** `{{PROJECT_NAME}}`
- **Specification file:** `specs/data_pipeline_{{PROJECT_NAME}}_spec.md`
- **Target source module(s):** `{{SOURCE_MODULE_PATHS}}`
- **Target test module(s):** `{{TEST_MODULE_PATHS}}`
- **Python version:** `{{PYTHON_VERSION}}`
- **Primary libraries:** `{{LIBRARIES_AND_VERSIONS}}`
- **Pipeline owner:** `{{OWNER_OR_TEAM}}`
- **Change type:** [New pipeline | Existing pipeline modification | Backfill | Migration]
- **In scope:** `{{IN_SCOPE_BEHAVIOR}}`
- **Out of scope:** `{{OUT_OF_SCOPE_BEHAVIOR}}`

### Required discovery before implementation

Before writing production code, inspect and record:

- Every input file, header, delimiter, encoding, and representative row.
- Existing ingestion, transformation, persistence, and configuration modules.
- Existing tests, fixtures, test commands, review logs, and known failures.
- The selected Python environment and installed library versions.
- Target storage constraints, indexes, uniqueness rules, and transaction support.
- Expected data volume, row count, record size, and acceptable runtime.

Do not implement until the source contract and destination contract are documented below.

---

## 2. Pipeline Overview

Describe the pipeline as a deterministic sequence:

```text
Source discovery
    -> File opening and decoding
    -> Parsing
    -> Structural validation
    -> Type normalization
    -> Missing-value and NaN handling
    -> Business validation
    -> Transformation / enrichment
    -> Batching
    -> Persistence
    -> Verification and reporting
```

### Pipeline stages

| Stage | Input | Output | Invariants | Failure action |
| :--- | :--- | :--- | :--- | :--- |
| Discovery | `{{INPUT_PATH_CONFIG}}` | Resolved input paths | Paths are validated and within allowed roots | Fail before processing |
| Parse | Raw file bytes | Parsed rows | Encoding and delimiter are known | Record file error and stop |
| Structural validation | Parsed rows | Schema-shaped rows | Required columns exist; no duplicate headers | Reject file |
| Normalization | Raw values | Typed values | Null, NaN, whitespace, dates, and numeric formats are explicit | Quarantine row or fail batch |
| Business validation | Typed records | Valid domain records | Domain constraints hold | Quarantine row or fail batch per policy |
| Transform | Valid domain records | Destination records | Transformation is deterministic and documented | Fail affected row/batch |
| Persist | Destination records | Stored records | Writes are idempotent or duplicate behavior is explicit | Retry, rollback, or quarantine |
| Verify | Stored records and metrics | Run report | Counts and checksums reconcile | Mark run failed |

### Processing mode

- **Mode:** [Full load | Incremental load | Upsert | Append-only | CDC]
- **Ordering requirement:** `{{ORDERING_REQUIREMENT}}`
- **Idempotency key:** `{{IDEMPOTENCY_KEY}}`
- **Replay behavior:** `{{REPLAY_BEHAVIOR}}`
- **Dry-run behavior:** `{{DRY_RUN_BEHAVIOR}}`

---

## 3. Source File Contract

### Source inventory

| Source | Format | Encoding | Delimiter | Header | Expected columns | Volume |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `{{SOURCE_FILE_1}}` | `{{CSV_JSON_PARQUET}}` | `{{UTF8}}` | `{{COMMA}}` | [Yes | No] | `{{COLUMNS}}` | `{{ROWS_OR_SIZE}}` |

### Source rules

- **Allowed file extensions:** `{{EXTENSIONS}}`
- **Expected encoding:** `{{ENCODING}}`
- **Delimiter and quoting:** `{{DELIMITER_AND_QUOTING}}`
- **Header behavior:** `{{HEADER_BEHAVIOR}}`
- **Column order:** [Significant | Not significant]
- **Duplicate column names:** [Reject | Rename by explicit mapping]
- **Extra columns:** [Reject | Ignore with warning | Map explicitly]
- **Missing columns:** [Always reject | Allow documented optional columns]
- **Empty file behavior:** [No-op success | Failed run | Empty result]
- **Malformed row behavior:** `{{MALFORMED_ROW_POLICY}}`

### Source profiling evidence

Record observed values before writing constraints:

- **Distinct categorical values:** `{{OBSERVED_CATEGORIES}}`
- **Identifier prefixes and patterns:** `{{OBSERVED_ID_PATTERNS}}`
- **Numeric ranges:** `{{OBSERVED_NUMERIC_RANGES}}`
- **Date formats and ranges:** `{{OBSERVED_DATE_FORMATS}}`
- **Maximum string lengths:** `{{OBSERVED_STRING_LENGTHS}}`
- **Known duplicate keys:** `{{KNOWN_DUPLICATES}}`

Constraints MUST accept every valid observed source record. Add regression tests for every non-obvious valid pattern.

---

## 4. Path Resolution and File Safety

All paths MUST be resolved from configuration or a project-root discovery mechanism. Do not hardcode machine-specific absolute paths in production code.

### Path contract

- **Project root resolution:** `{{PROJECT_ROOT_STRATEGY}}`
- **Input root:** `{{INPUT_ROOT_CONFIG_KEY}}`
- **Output root:** `{{OUTPUT_ROOT_CONFIG_KEY}}`
- **Archive/quarantine root:** `{{ARCHIVE_ROOT_CONFIG_KEY}}`
- **Configuration source:** [Environment variables | Settings module | CLI arguments | Configuration file]
- **Path library:** `pathlib.Path`
- **Allowed roots:** `{{ALLOWED_ROOTS}}`
- **Symlink policy:** [Reject | Resolve and verify | Allow]
- **Traversal policy:** Reject paths that escape the configured root after resolution.

### Required path behavior

- Resolve paths with `Path.resolve()` before opening files.
- Validate that resolved inputs are regular files when a file is expected.
- Validate that resolved outputs remain inside the configured output root.
- Create output directories explicitly with `mkdir(parents=True, exist_ok=True)` where allowed.
- Never silently fall back to the current working directory.
- Never use a path assembled from untrusted input without validating its resolved location.
- Include resolved paths in run metadata, but do not log secrets embedded in paths.

### Path acceptance criteria

- A valid configured input path is opened successfully.
- A missing input file produces a clear error naming the configuration key and resolved path.
- A path outside the allowed root is rejected before reading or writing.
- A directory supplied where a file is required is rejected.
- Tests do not depend on a developer-specific absolute path.

---

## 5. Schema, Types, and Missing-Value Policy

### Canonical record schema

| Field | Source type | Canonical type | Required | Null allowed | Default | Constraints |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `{{FIELD_NAME}}` | `{{RAW_TYPE}}` | `{{CANONICAL_TYPE}}` | [Yes | No] | [Yes | No] | `{{CONSTRAINTS}}` |

### Missing values

Define behavior for every representation found in the source:

- Empty string: `{{EMPTY_STRING_POLICY}}`
- Whitespace-only string: `{{WHITESPACE_POLICY}}`
- `null` / `None`: `{{NULL_POLICY}}`
- CSV tokens such as `NA`, `N/A`, `NULL`, or `-`: `{{SENTINEL_POLICY}}`
- Missing column: `{{MISSING_COLUMN_POLICY}}`
- Missing required field: `{{REQUIRED_FIELD_POLICY}}`

Never silently convert a missing required value into a business value such as `0`, `False`, or an empty string unless the domain contract explicitly says to do so.

### NaN and infinity policy

NaN handling MUST be explicit for every numeric column.

- **NaN source representations:** `{{NAN_REPRESENTATIONS}}`
- **Positive infinity policy:** [Reject | Convert to null | Quarantine]
- **Negative infinity policy:** [Reject | Convert to null | Quarantine]
- **NaN policy per field:** `{{NAN_POLICY_BY_FIELD}}`
- **Allowed nullable numeric fields:** `{{NULLABLE_NUMERIC_FIELDS}}`
- **Serialization policy:** [Never serialize NaN | Convert to null | Explicitly supported format]

Required guardrails:

- Do not compare with `value == float("nan")`; use a reliable missing-value check appropriate to the data library.
- Do not allow NaN to bypass numeric bounds or uniqueness checks.
- Do not write NaN to a destination that cannot represent it safely.
- Test NaN, positive infinity, negative infinity, empty values, and numeric strings where relevant.
- Report how many values were rejected, converted, or quarantined because of missingness.

---

## 6. Transformation and ETL Rules

### Transformation catalog

Document each transformation as an input/output contract:

| Rule ID | Input | Transformation | Output | Idempotent | Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TR-001` | `{{INPUT_FIELD}}` | `{{NORMALIZATION_RULE}}` | `{{OUTPUT_FIELD}}` | [Yes | No] | `{{TEST_NAME}}` |

### Transformation guardrails

- Transformations MUST be deterministic for the same input and configuration.
- Preserve source values when normalization is lossy; record the transformation if auditability matters.
- Do not mix validation, persistence, and unrelated business side effects in one transformation function.
- Make timezone behavior explicit for timestamps.
- Make rounding mode and decimal precision explicit for money.
- Make unit conversion explicit, including source and destination units.
- Do not use implicit positional column access when named columns are available.
- Preserve stable identifiers through every stage.
- Ensure transformations are safe to rerun.

### Data quality invariants

- **Row count reconciliation:** `{{ROW_COUNT_RULE}}`
- **Key uniqueness:** `{{KEY_UNIQUENESS_RULE}}`
- **Referential integrity:** `{{REFERENCE_RULE}}`
- **Allowed categories/enums:** `{{ENUM_RULE}}`
- **Range checks:** `{{RANGE_RULE}}`
- **Duplicate handling:** `{{DUPLICATE_RULE}}`
- **Ordering checks:** `{{ORDERING_RULE}}`

---

## 7. Validation Error Strategy

Validation errors MUST be classified and handled deliberately. Do not catch `Exception` and continue without reporting the failed record.

### Error classes

| Error class | Example | Action | Retryable | Report |
| :--- | :--- | :--- | :--- | :--- |
| Configuration | Missing environment variable | Fail before processing | No | Configuration error |
| File access | Permission denied | Fail run | Maybe | Source error |
| Structural | Missing required column | Reject file | No | Schema error |
| Record validation | Invalid rating or date | Quarantine/reject row per policy | No | Row error |
| Referential | Unknown product ID | Quarantine/reject row per policy | No | Relationship error |
| Transient persistence | Connection timeout | Retry with bounded backoff | Yes | Persistence warning/error |
| Permanent persistence | Constraint violation | Roll back/quarantine | No | Persistence error |
| Unexpected | Programming defect | Fail loudly with traceback and run ID | No | Internal error |

### Row-level error policy

- **Maximum tolerated invalid rows:** `{{MAX_INVALID_ROWS}}`
- **Maximum tolerated invalid ratio:** `{{MAX_INVALID_RATIO}}`
- **Behavior when threshold is exceeded:** [Fail run | Roll back batch | Stop file]
- **Quarantine destination:** `{{QUARANTINE_TARGET}}`
- **Quarantine payload:** Include source identifier, row number, sanitized raw values, error class, error message, and run ID.
- **Sensitive data policy:** `{{REDACTION_POLICY}}`

A pipeline MUST NOT report success if invalid records were discarded without counts, reasons, and a documented policy allowing that behavior.

### Error reporting contract

Every run report MUST include:

- Run ID and start/end timestamps.
- Source file and resolved path.
- Total rows read.
- Rows parsed, accepted, rejected, quarantined, and persisted.
- Error counts grouped by class and field.
- Retry counts and final persistence status.
- Configuration version or commit identifier where available.

---

## 8. Batching, Memory, and Backpressure

The implementation MUST avoid loading unbounded input into memory.

- **Batch size:** `{{BATCH_SIZE}}` records or `{{BATCH_BYTES}}` bytes.
- **Maximum in-memory records:** `{{MAX_IN_MEMORY_RECORDS}}`
- **Streaming reader:** `{{READER_OR_CHUNK_API}}`
- **Persistence batch API:** `{{PERSISTENCE_BATCH_API}}`
- **Concurrency:** `{{CONCURRENCY_MODEL}}`
- **Backpressure behavior:** `{{BACKPRESSURE_BEHAVIOR}}`
- **Per-batch transaction behavior:** [Atomic | Partial success with row results | No transaction]
- **Flush behavior:** `{{FLUSH_AND_CHECKPOINT_RULE}}`

### Batch guardrails

- Process records incrementally when input can exceed memory limits.
- Do not create a list of the entire dataset merely to batch it later.
- Make batch size configurable and bounded.
- Commit only after the batch passes validation, unless partial writes are explicitly required.
- Record per-batch counts and the last successful checkpoint.
- Retry only transient failures, with a bounded retry count and backoff.
- Ensure retrying a batch does not duplicate records; use idempotency keys or atomic upsert semantics.
- Stop or pause when the destination applies backpressure instead of creating an unbounded queue.

### Performance acceptance criteria

- Peak memory remains below `{{MEMORY_LIMIT}}` for `{{DATASET_SIZE}}` input.
- A failed batch can be identified and replayed without reprocessing unrelated data.
- The pipeline can resume from `{{CHECKPOINT_STRATEGY}}`.

---

## 9. Persistence Contract

### Database Selection Decision

Select the persistence technology from verified project evidence, not from the current dependency list or a familiar default. The project-specific specification MUST document:

- Data shape: relational, document, key-value, graph, time-series, or mixed.
- Relationships and integrity requirements: foreign keys, ownership, uniqueness, and transactions.
- Expected query patterns: filters, joins, aggregations, full-text search, key lookups, and similarity search.
- Read/write workload, consistency, latency, scale, and deployment constraints.
- Schema evolution and migration requirements.
- Operational constraints, team familiarity, hosting, cost, and existing dependencies as secondary evidence only.
- At least one rejected alternative and the concrete reason it was rejected.

Do not choose a database solely because its client library appears in `requirements.txt`. A dependency records an available option; it does not prove architectural fit.

For semi-structured fields, document whether they should use a JSON/JSONB column, a normalized related table, or a document store, and explain the choice from expected queries and update patterns. For semantic search, document whether an existing relational database with a vector extension is sufficient before introducing a separate vector database.

### Destination

- **Target system:** `{{DATABASE_OR_STORAGE}}`
- **Target collection/table/path:** `{{TARGET_NAME}}`
- **Write operation:** [Insert | Upsert | Replace | Merge | Append]
- **Primary key:** `{{PRIMARY_KEY}}`
- **Unique indexes/constraints:** `{{UNIQUE_CONSTRAINTS}}`
- **Foreign keys/references:** `{{REFERENTIAL_CONSTRAINTS}}`
- **Schema migration strategy:** `{{MIGRATION_STRATEGY}}`
- **Retention policy:** `{{RETENTION_POLICY}}`

### Atomicity and idempotency

- **Transaction boundary:** `{{TRANSACTION_BOUNDARY}}`
- **Idempotency mechanism:** `{{IDEMPOTENCY_MECHANISM}}`
- **Duplicate write behavior:** `{{DUPLICATE_WRITE_BEHAVIOR}}`
- **Partial failure behavior:** `{{PARTIAL_FAILURE_BEHAVIOR}}`
- **Rollback behavior:** `{{ROLLBACK_BEHAVIOR}}`
- **Recovery/replay procedure:** `{{RECOVERY_PROCEDURE}}`

Persistence code MUST not claim success until the destination confirms the write. If a destination is eventually consistent, specify when verification is considered complete.

### Serialization rules

- Decimal/money representation: `{{DECIMAL_REPRESENTATION}}`
- Date/time representation and timezone: `{{DATETIME_REPRESENTATION}}`
- Null representation: `{{NULL_REPRESENTATION}}`
- NaN representation: `{{PERSISTED_NAN_POLICY}}`
- Unicode and encoding: `{{UNICODE_POLICY}}`

---

## 10. Configuration and Secrets

- Configuration MUST come from `{{CONFIGURATION_SOURCE}}`, not hardcoded constants for environment-specific values.
- Required settings: `{{REQUIRED_SETTINGS}}`
- Optional settings and defaults: `{{OPTIONAL_SETTINGS}}`
- Secret settings: `{{SECRET_NAMES}}`
- Secret logging policy: Never log secret values, tokens, passwords, or full connection strings.
- Configuration validation timing: Fail before opening source files or connecting to the destination.
- Environment-specific behavior: `{{ENVIRONMENT_BEHAVIOR}}`

---

## 11. Observability and Auditability

### Metrics

Record at minimum:

- Rows read, accepted, rejected, quarantined, and persisted.
- Batch count, batch duration, retry count, and checkpoint position.
- Missing, NaN, infinity, duplicate, and referential-integrity counts.
- Destination write latency and failure counts.
- Total duration and throughput.

### Logs

Each log event should include:

- `run_id`
- `stage`
- `source`
- `batch_id` when applicable
- `record_key` when safe to log
- `error_class` for failures
- `message` without secrets or unnecessary sensitive data

Use structured logs where possible. Avoid logging entire raw rows when they may contain personal or confidential information.

### Audit record

- **Run record location:** `{{RUN_RECORD_LOCATION}}`
- **Retention:** `{{RUN_RECORD_RETENTION}}`
- **Replay metadata:** `{{REPLAY_METADATA}}`
- **Data lineage:** `{{LINEAGE_REQUIREMENTS}}`

---

## 12. Required Test Suite

Use the repository's existing test conventions. If none exist, use pytest and create:

```text
tests/test_{{PIPELINE_MODULE_NAME}}.py
```

Before writing tests, use the `test-suite-generator` workflow to discover existing tests, configuration, known-bug history, public functions, and external dependencies.

### Test-plan approval checkpoint

Before generating test code, present and obtain approval for a test plan covering:

- Valid source parsing and canonical output.
- Missing columns, extra columns, malformed rows, empty files, and encoding errors.
- NaN, infinity, empty strings, null tokens, and numeric/date coercion.
- Every transformation rule and boundary condition.
- Invalid records, error classification, thresholds, and quarantine behavior.
- Path traversal, missing paths, directory/file mismatches, and project-root resolution.
- Batch boundaries, memory-safe iteration, retries, checkpoints, and backpressure.
- Idempotent reruns, duplicate keys, partial failures, rollback, and persistence confirmation.
- Run metrics and sanitized error reporting.
- Regression tests for every relevant known bug.

Do not generate tests until the plan is explicitly approved.

### Mocking policy

Mock external systems and nondeterministic dependencies:

- Database and document-store clients.
- Network APIs.
- Clock/time sources when time affects behavior.
- Filesystem boundaries when tests do not need real files.
- Cloud storage clients and message queues.

Use temporary directories and small real fixtures for parser and path tests where that gives stronger coverage. Do not mock pure transformations or validation logic.

### Test execution and triage

- Run the focused test module first, then the complete project suite.
- Investigate every failure before changing code.
- Distinguish test-authoring mistakes from production defects.
- Allow at most three bounded test/triage passes.
- Never weaken an assertion or silently discard a failing case.
- Run syntax checks, lint, and type checks when available.

### Required durable test log

Append a versioned entry to `.agents/memory-bank/testGenerationLog.md` or the repository's established equivalent containing:

- Target modules and test files.
- Discovery findings and coverage rationale.
- Fixtures and mocks used.
- Failure triage and genuine defects found.
- Final test result and known gaps.
- Whether changes were committed.

### Test acceptance criteria

The pipeline implementation is incomplete until the test suite passes, or every remaining failure is explicitly documented as a production defect or environment blocker.

---

## 13. Operational Runbook

### Normal run

```bash
{{NORMAL_RUN_COMMAND}}
```

### Dry run

```bash
{{DRY_RUN_COMMAND}}
```

### Resume from checkpoint

```bash
{{RESUME_COMMAND}}
```

### Replay quarantined records

```bash
{{REPLAY_COMMAND}}
```

### Verify destination

```bash
{{VERIFICATION_COMMAND}}
```

### Stop conditions

The pipeline MUST stop when:

- Required configuration is missing or invalid.
- The source structure does not match the documented contract.
- Invalid-row thresholds are exceeded.
- A non-retryable persistence error occurs.
- Idempotency cannot be guaranteed for a retry.
- Data reconciliation fails.

---

## 14. Acceptance Criteria

- [ ] All source files, paths, columns, types, and observed patterns are documented.
- [ ] Project-root and allowed-root path resolution is explicit and tested.
- [ ] Empty values, nulls, NaN, infinity, and sentinel tokens have field-level policies.
- [ ] Transformations are deterministic, idempotent, and individually testable.
- [ ] Batch size, memory limits, retries, backpressure, and checkpoints are specified.
- [ ] Validation errors are classified, counted, reported, and handled according to policy.
- [ ] Quarantined records preserve enough sanitized context for replay and diagnosis.
- [ ] Persistence keys, indexes, transactions, duplicate behavior, and rollback are specified.
- [ ] Metrics and structured logs include a run ID and do not expose secrets.
- [ ] Test-plan approval was obtained before test generation.
- [ ] Focused and complete test suites pass.
- [ ] Durable test-generation and implementation records are updated.

---

## Appendix A: Raw Source Contracts

Paste representative raw inputs here. Include at least:

- One valid record per distinct source pattern.
- One record containing each supported missing-value representation.
- One malformed or invalid record for every documented error class.

```text
{{RAW_SOURCE_SAMPLES}}
```

## Appendix B: Destination Contract

```text
{{DESTINATION_SCHEMA_OR_EXAMPLES}}
```

## Appendix C: Decision Log

| Decision | Options considered | Selected option | Reason | Date |
| :--- | :--- | :--- | :--- | :--- |
| `{{DECISION}}` | `{{OPTIONS}}` | `{{SELECTED}}` | `{{RATIONALE}}` | `{{DATE}}` |
