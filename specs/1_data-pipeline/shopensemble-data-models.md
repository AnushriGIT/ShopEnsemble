# Specification: ShopEnsemble Domain Data Models

## Table of Contents

- [1. Narrative](#1-narrative)
- [2. Environment and Library](#2-environment-and-library)
- [3. Entity Catalog and Relationships](#3-entity-catalog-and-relationships)
- [4. Concrete Entity Specifications](#4-concrete-entity-specifications)
- [5. Shared Validation Rules](#5-shared-validation-rules)
- [6. Serialization Expectations](#6-serialization-expectations)
- [7. Downstream Integration Contract](#7-downstream-integration-contract)
- [8. Acceptance Criteria in Gherkin](#8-acceptance-criteria-in-gherkin)
- [9. Implementation Scope](#9-implementation-scope)
- [10. Required Validation Test Suite](#10-required-validation-test-suite)
- [11. Test-Plan Approval Checkpoint](#11-test-plan-approval-checkpoint)
- [12. Verification Plan](#12-verification-plan)

## 1. Narrative

Implement strict Pydantic v2 models in `app/models.py` for the three datasets under `data/`:

- `Product` represents a catalog item from `data/products.csv`.
- `Review` represents a customer review linked to a product from `data/reviews.csv`.
- `StorePolicy` represents a store policy from `data/store_policies.csv`.

The models are application-domain models. CSV ingestion must normalize CSV text values into typed Python values before validation. Validation failures must be raised as Pydantic `ValidationError` instances and must not be silently corrected.

## 2. Environment and Library

- **Target file:** `app/models.py`
- **Validation library:** Pydantic v2
- **Python version:** 3.12
- **Syntax:** `Type | None` and built-in generic types such as `list[str]`
- **Global model configuration:** `ConfigDict(extra="forbid", str_strip_whitespace=True)`
- **Required documentation:** Module docstring, model docstrings, and concise comments for non-obvious CSV/domain decisions

## 3. Entity Catalog and Relationships

| Entity | Primary/business key | Relationships | Source |
| :--- | :--- | :--- | :--- |
| `Product` | `id` | One product has many reviews and may match many policies by category | `data/products.csv` |
| `Review` | No standalone id; composite identity is `(product_id, date, text)` | Belongs to one product by `product_id` | `data/reviews.csv` |
| `StorePolicy` | No standalone id; policy identity is `(policy_type, description, timeframe)` | Applies to a product category inferred from policy description | `data/store_policies.csv` |

## 4. Concrete Entity Specifications

### 4.1 `Product`

**Purpose:** Validated catalog data used for product search, display, inventory, and recommendation workflows.

| Field | Type | Requirement and constraints |
| :--- | :--- | :--- |
| `id` | `str` | Required; pattern `^[A-Z]{2,3}[0-9]{4}$` to match identifiers such as `SP0001`, `LP0002`, `TV0003`, and `SPK0441` |
| `name` | `str` | Required; stripped; length 1-200 |
| `brand` | `str` | Required; stripped; length 1-100 |
| `category` | `str` | Required; stripped; pattern `^[a-z][a-z0-9_]*$` |
| `price` | `Decimal` | Required; greater than 0; CSV decimal text must be converted before validation |
| `description` | `str` | Required; stripped; length 1-1000 |
| `stock` | `int` | Required; greater than or equal to 0 |
| `rating` | `float` | Required; inclusive range 0 through 5 |

### 4.2 `Review`

**Purpose:** Validated product feedback for ratings, search context, and product quality analysis.

| Field | Type | Requirement and constraints |
| :--- | :--- | :--- |
| `product_id` | `str` | Required; pattern `^[A-Z]{2,3}[0-9]{4}$`; references `Product.id` |
| `rating` | `float` | Required; inclusive range 0 through 5 |
| `text` | `str` | Required; stripped; length 1-2000 |
| `date` | `date` | Required; ISO date from CSV values such as `2024-12-18` |

### 4.3 `StorePolicy`

**Purpose:** Validated store policy information for returns and warranties.

| Field | Type | Requirement and constraints |
| :--- | :--- | :--- |
| `policy_type` | `Literal["exchanges", "financing", "preorder", "price_matching", "repairs", "returns", "shipping", "warranty"]` | Required; all eight values observed in the source data |
| `description` | `str` | Required; stripped; length 1-300 |
| `conditions` | `list[str]` | Required; each condition is a stripped non-empty string; source CSV uses `|` as the delimiter and ingestion must split it |
| `timeframe` | `int` | Required; greater than or equal to 0 days; zero means the policy has no duration |

## 5. Shared Validation Rules

- All models reject unknown fields with `extra="forbid"`.
- All string fields strip surrounding whitespace.
- Identifiers are required and use the shared product-ID pattern.
- Identifier constraints are derived from all observed source prefixes, including two-letter prefixes (`SP`, `LP`, `TV`) and the three-letter speaker prefix (`SPK`); they must not be inferred from a single sample row.
- Ratings are bounded inclusively between 0 and 5.
- Numeric fields use explicit `Field` constraints.
- `Product.price` uses `Decimal` to avoid binary floating-point representation for money.
- `StorePolicy.conditions` is normalized from the raw pipe-delimited CSV value into `list[str]` before model validation.
- No field is nullable because the inspected CSV contracts provide a populated value for every field.

## 6. Serialization Expectations

- `model_dump()` returns a Python dictionary for internal processing.
- `model_dump_json()` returns JSON for API or wire transmission.
- Serialization must preserve the typed values and must not expose undeclared fields.

## 7. Downstream Integration Contract

- **CSV ingestion:** `csv.DictReader` reads raw rows; an adapter converts decimal, integer, date, and pipe-delimited values before calling `model_validate`.
- **FastAPI:** `Product`, `Review`, and `StorePolicy` may be used as request/response schemas. Invalid request data should surface as FastAPI validation errors.
- **PostgreSQL/SQLAlchemy:** persistence code is responsible for mapping `Decimal` to PostgreSQL `NUMERIC`, policy condition lists to `JSONB`, and model IDs to explicit primary/foreign keys; the Pydantic models do not perform database writes.
- **Error handling:** callers should catch `ValidationError` at ingestion/API boundaries, log the row or request context, and reject the invalid record. No invalid record should be silently dropped.

## 8. Acceptance Criteria in Gherkin

### Scenario: Validate a product row

Given a normalized product payload with id `SP0001`, a positive price, stock `43`, and rating `4.0`
When the payload is validated as a `Product`
Then validation succeeds
And the price is represented as a `Decimal`
And `model_dump()` contains exactly the declared product fields

### Scenario: Reject an invalid product rating

Given a product payload with rating `5.1`
When the payload is validated as a `Product`
Then Pydantic raises `ValidationError`
And the error identifies the `rating` field

### Scenario: Reject unknown product fields

Given a valid product payload with an undeclared field named `supplier_secret`
When the payload is validated as a `Product`
Then Pydantic raises `ValidationError`

### Scenario: Validate a review linked to a product

Given a review payload with product id `TV0575`, rating `4.0`, non-empty text, and date `2024-11-18`
When the payload is validated as a `Review`
Then validation succeeds
And the date is represented as a Python `date`

### Scenario: Reject an invalid review date

Given a review payload with date `18-11-2024`
When the payload is validated as a `Review`
Then Pydantic raises `ValidationError`

### Scenario: Normalize store policy conditions

Given a store policy CSV value with conditions separated by `|`
When the ingestion adapter converts and validates the payload as a `StorePolicy`
Then `conditions` is a list of non-empty strings
And `timeframe` is represented as a positive integer

### Scenario: Reject unsupported policy types

Given a store policy payload with policy type `exchange`
When the payload is validated as a `StorePolicy`
Then Pydantic raises `ValidationError`

### Scenario: Preserve serialization contracts

Given a valid `Product`, `Review`, or `StorePolicy` instance
When `model_dump()` and `model_dump_json()` are called
Then both operations succeed
And only declared model fields are serialized

## 9. Implementation Scope

Implement only the models and their reusable validation constants/helpers in `app/models.py`. Do not implement CSV loading, database persistence, FastAPI routes, or unrelated refactors in this change.

## 10. Required Validation Test Suite

Create `tests/test_models.py` using pytest. The repository has no existing test directory, test configuration, fixtures, or model tests, so follow the project's standard test-generation convention.

The suite MUST cover:

- Valid construction of `Product`, `Review`, and `StorePolicy`.
- Product ID, category, string-length, price, stock, and rating boundaries.
- Review ID, rating, text, and ISO date validation.
- Store policy type, condition list, and positive timeframe validation.
- Unknown fields rejected by `extra="forbid"`.
- Whitespace stripping on string fields.
- Decimal price and Python date parsing.
- `model_dump()` and `model_dump_json()` serialization.
- Invalid inputs raising `pydantic.ValidationError` with the relevant field location.

No mocks are required because the target models are deterministic and have no network, database, filesystem, or time-dependent behavior. CSV loading and persistence are explicitly out of scope.

Each non-obvious boundary or negative test should include a brief comment explaining the contract it protects. Do not weaken tests or modify production code solely to make a test pass; report genuine model defects separately.

## 11. Test-Plan Approval Checkpoint

Before generating `tests/test_models.py`, present the test plan for approval. Do not write the test file until approval is explicit.

## 12. Verification Plan

After implementation:

1. Run Python syntax validation for `app/models.py`.
2. Run the generated suite with `python -m pytest`.
3. Investigate failures using the standard failure-triage workflow, with a maximum of three passes.
4. Run focused Pydantic construction checks for valid and invalid payloads.
5. Run project diagnostics/tests if available.
6. Append a versioned test-generation record to `.agents/memory-bank/testGenerationLog.md` or the repository's established equivalent.
