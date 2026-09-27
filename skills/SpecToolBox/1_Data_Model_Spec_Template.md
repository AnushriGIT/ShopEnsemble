# Specification: Domain Data Models & Schema Validation

## Template to generate project specific /specs/data_model_#ProjectName_spec.md file 
"""
Look at the @Data_Model_Spec_Template.md and ShopEnsemble/Data folder, replace 3 and 4 with concrete models for this project then implement the **code directly into `app/models.py`."* This guarantees consistent, production-grade models with strict types, constraints, and validation across any system you build.
"""

## Table of Contents

- [1. Meta & Environment](#1-meta--environment)
- [2. Global Validation & Quality Guardrails](#2-global-validation--quality-guardrails)
- [3. Entity Catalog & Relationship Matrix](#3-entity-catalog--relationship-matrix)
- [4. Entity Specifications](#4-entity-specifications)
- [5. Downstream Integration Contract](#5-downstream-integration-contract)
- [6. Required Data-Validation Test Suite](#6-required-data-validation-test-suite)
- [Appendix: Upstream Raw Data Contracts](#appendix-upstream-raw-data-contracts)

When generating a project-specific data-model specification, keep this table immediately below the metadata and update it whenever headings change.

## 1. Meta & Environment
- **Target File:** `{{TARGET_FILE_PATH}}` (e.g., `app/models.py`, `src/domain/schemas.py`)
- **Engine / Library:** {{VALIDATION_LIBRARY}} (e.g., `Pydantic v2`, `dataclasses`, `msgspec`)
- **Python Version:** 3.10+
- **Syntax Standards:**
  - Modern union syntax (`Type | None` instead of `Optional[Type]`)
  - Standard collections (`list[Type]`, `dict[str, Any]` instead of typing module equivalents)

---

## 2. Global Validation & Quality Guardrails
- **Strictness:** Apply `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)` to reject unmapped fields and sanitize strings.
- **Nullability Policy:** Never make an attribute optional (`| None = None`) unless explicitly verified as nullable in upstream storage or generated post-ingestion. Identifiers and business keys are strictly required.
- **Constraint Enforcement:** Every numeric, date, and bound string field must carry boundaries via `Field(...)` (e.g., `ge`, `le`, `min_length`, `pattern`).
- **Source-Pattern Verification:** Before defining regex, length, enum, or range constraints, inspect all relevant source rows and enumerate observed values/prefixes. Constraints MUST accept every valid observed record and reject only values outside the documented source contract. Add a regression test for each non-obvious valid pattern found.
- **Immutability:** Set `frozen=True` on value objects, search query payloads, and state snapshots where mutation is prohibited.

---

## 3. Entity Catalog & Relationship Matrix

| Entity Name | Primary Key | Key Relationships | Downstream Target |
| :--- | :--- | :--- | :--- |
| `{{EntityA}}` | `id` | 1-to-Many with `{{EntityB}}` | Vector Store / SQL / Cache |
| `{{EntityB}}` | `id` | Belongs to `{{EntityA}}` | NoSQL / Document Store |

---

## 4. Entity Specifications

<!-- Repeat this block for each entity in your project -->
### 4.{{N}} `{{EntityName}}`
- **Purpose:** Brief 1-line description of what this model represents in the business domain.
- **Attributes:**
  - `{{field_name}}`: `{{type}}` — [Required | Optional with default]. Constraints: `{{e.g., ge=0, min_length=1}}`. Description.
  - `{{foreign_key_id}}`: `{{type}}` — Required reference to `{{ReferencedEntity.id}}`.
  - `{{metadata_or_tags}}`: `list[str]` — Default factory `list`.
- **Custom Validators (if any):**
  - `@field_validator('{{field_name}}')`: Rule description (e.g., ensure end_date >= start_date).
- **Serialization Expectations:**
  - Method: `model_dump()` for Python dictionaries, `model_dump_json()` for wire transmission.

---

## 5. Downstream Integration Contract
- **Persistence Target:** How these models will be read/written (e.g., ORM, raw SQL, Redis, Chroma/Pinecone).
- **Error Handling:** Specify how validation failures (`ValidationError`) should bubble up (e.g., mapped to an HTTP 422 error or logged to a dead-letter queue).

---

## 6. Required Data-Validation Test Suite

Every generated data-model specification MUST define a focused pytest suite for the target models.

### Test discovery requirements

Before writing tests, use the `test-suite-generator` workflow to discover:

- Existing test directories, configuration, naming, fixtures, and assertion conventions.
- Review logs, changelogs, or known-bug history that should become regression tests.
- The public model surface, validators, serialization methods, and external integrations.
- Dependencies requiring mocks. Do not mock pure Pydantic validation; mock only network, database, filesystem, or other non-deterministic integrations.

If no test convention exists, use `tests/test_models.py` with pytest.

### Test-plan checkpoint

Before generating test code, present a test plan for human approval. The plan MUST cover:

- Valid construction for every generated model.
- Required fields, type parsing, boundaries, and invalid inputs.
- Custom field and model validators.
- Unknown-field behavior defined by `extra="forbid"`.
- Nested models and cross-entity relationships where applicable.
- `model_dump()` and `model_dump_json()` serialization contracts.
- One regression test for each relevant known bug found during discovery.
- The mocking strategy and any unresolved assumptions.

Do not generate or modify tests until the plan is approved.

### Test-generation and execution requirements

- Generate one focused test module per source module unless repository conventions require otherwise.
- Every non-obvious edge-case or regression test MUST include a brief comment explaining why it exists.
- Run the project test command after generation and investigate every failure before changing code.
- Allow at most three test/triage passes.
- Never weaken a test or modify production code solely to make a failing test pass. Surface genuine production defects separately.
- Run syntax, lint, and focused model checks when available.

### Required tracking record

Append a versioned entry to `.agents/memory-bank/testGenerationLog.md` (or the repository's established test-generation log) recording:

- Target source and test files.
- Discovery findings and test coverage rationale.
- Mocks used and why.
- Failures, triage results, and genuine defects found.
- Final test result and whether tests were committed.

### Test acceptance criteria

The data-model work is incomplete until the generated suite passes, or any remaining failure is explicitly reported as a production defect or documented environment blocker.

## Appendix: Upstream Raw Data Contracts
<!-- Paste raw input sample payloads below so the AI or developer has zero ambiguity -->
```json
// Paste 1-2 actual raw JSON objects, CSV row headers, or DB DDL here