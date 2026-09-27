# ShopEnsemble Full Data Pipeline Specification

**Status**: Phase 1 (Dry Run) Complete | Phase 2-5 (Full Run) - Development Plan  
**Version**: 1.0  
**Last Updated**: 2026-09-10  
**Author**: Development Team

---

## 1. Project Context

### 1.1 Project Name
**ShopEnsemble Data Pipeline**

### 1.2 Data Pipeline Purpose
The ShopEnsemble data pipeline ingests, validates, and persists e-commerce catalog data including:
- **Products**: Catalog items with pricing, stock, and ratings
- **Reviews**: Customer reviews linked to products with ratings and dates
- **Store Policies**: Return/shipping/warranty policies with conditions

### 1.3 Scope
- **Input**: 3 CSV files (products, reviews, store_policies)
- **Processing**: Type validation, business rule validation, referential integrity
- **Output**: PostgreSQL database tables with proper indexing and constraints
- **Schedule**: On-demand (one-time loads for development/testing, daily for production)
- **Capacity**: ~100K products, ~500K reviews, ~500 policies

### 1.4 Stakeholders
- **Data Owner**: Product & Operations team
- **Validator**: Data quality team
- **Consumer**: API backend, analytics team
- **DevOps**: Database infrastructure team

---

## 2. Data Sources

### 2.1 Input Files

| File Name | Format | Size | Frequency | Location |
|-----------|--------|------|-----------|----------|
| products.csv | CSV | ~1,000 rows | On-demand | `data/products.csv` |
| reviews.csv | CSV | ~5,000 rows | On-demand | `data/reviews.csv` |
| store_policies.csv | CSV | ~50 rows | On-demand | `data/store_policies.csv` |

### 2.2 File Headers & Validation

**products.csv**
```
Headers: id, name, brand, category, price, description, stock, rating
Expected: 8 columns, UTF-8 encoding
Example row: "SP0001","Widget Pro","TechBrand","electronics","19.99","Premium widget device",100,4.5
```

**reviews.csv**
```
Headers: product_id, rating, text, date
Expected: 4 columns, UTF-8 encoding
Example row: "SP0001",4.5,"Great product!","2026-09-10"
```

**store_policies.csv**
```
Headers: policy_type, description, conditions, timeframe
Expected: 4 columns, UTF-8 encoding
Conditions: Pipe-delimited list (e.g., "condition1 | condition2 | condition3")
Example row: "returns","30-day returns","No questions asked | Keep original packaging | Item in resale condition",30
```

### 2.3 Data Characteristics

| File | Row Count | Data Type | Key Field | Dependencies |
|------|-----------|-----------|-----------|--------------|
| products.csv | ~1,000 | Master | id (ProductId) | None |
| reviews.csv | ~5,000 | Transaction | product_id | products.csv (FK) |
| store_policies.csv | ~50 | Configuration | policy_type + description | None |

---

## 3. Data Model & Validation Rules

### 3.1 Entity Models

#### Product
```
Field         | Type      | Required | Constraints              | Example
──────────────┼───────────┼──────────┼──────────────────────────┼──────────────────
id            | String    | Yes      | Pattern: ^[A-Z]{2,3}[0-9]{4}$ | SP0001
name          | String    | Yes      | Length: 1-200            | Widget Pro
brand         | String    | Yes      | Length: 1-100            | TechBrand
category      | String    | Yes      | Pattern: ^[a-z][a-z0-9_]*$ | electronics
price         | Decimal   | Yes      | > 0, 2 decimals          | 19.99
description   | String    | Yes      | Length: 1-1000           | Premium widget device
stock         | Integer   | Yes      | >= 0                     | 100
rating        | Float     | Yes      | 0.0 - 5.0               | 4.5
```

#### Review
```
Field         | Type      | Required | Constraints              | Example
──────────────┼───────────┼──────────┼──────────────────────────┼──────────────────
id            | Integer   | Auto     | Primary Key              | 1
product_id    | String    | Yes      | FK → Product.id          | SP0001
rating        | Float     | Yes      | 0.0 - 5.0               | 4.5
text          | String    | Yes      | Length: 1-2000           | Great product!
date          | Date      | Yes      | ISO Format YYYY-MM-DD    | 2026-09-10
```

#### StorePolicy
```
Field         | Type      | Required | Constraints              | Example
──────────────┼───────────┼──────────┼──────────────────────────┼──────────────────
id            | Integer   | Auto     | Primary Key              | 1
policy_type   | Enum      | Yes      | See allowed values       | returns
description   | String    | Yes      | Length: 1-300            | 30-day returns
conditions    | JSON List | Yes      | Non-empty strings        | ["No questions", "Keep packaging"]
timeframe_days| Integer   | Yes      | >= 0                     | 30
```

**StorePolicy.policy_type Enum Values:**
- exchanges
- financing
- preorder
- price_matching
- repairs
- returns
- shipping
- warranty

### 3.2 Validation Rules

#### Type Conversions
- **Decimal** (price): Use `Decimal` type, validate positive values
  - Example: "19.99" → Decimal('19.99')
  - Reject: "19.9", "19.999", "abc"

- **Integer** (stock, timeframe): Parse as `int`, reject negative or non-integer
  - Example: "100" → 100
  - Reject: "100.5", "abc", "-1"

- **Float** (rating): Parse as `float`, reject NaN/Infinity
  - Example: "4.5" → 4.5
  - Reject: "4.5.1", "inf", "nan", "abc"

- **Date** (review date): ISO format YYYY-MM-DD only
  - Example: "2026-09-10" → date(2026, 9, 10)
  - Reject: "09/10/2026", "2026-9-10", "invalid"

#### Business Rules

**Required Fields:**
- Must have non-empty value
- Reject: "", "NA", "N/A", "NULL", "-" (case-insensitive)

**ID Validation:**
- Product ID format: ^[A-Z]{2,3}[0-9]{4}$ (e.g., SP0001, SPK0441)
- Enforced at model level with Pydantic `Field(pattern=...)`

**Category Validation:**
- Must start with lowercase letter
- Can contain lowercase letters, digits, underscores
- Example valid: electronics, home_and_garden, sports_outdoors
- Example invalid: Electronics, Home-Garden, 123

**Rating Validation:**
- Must be 0.0 to 5.0 inclusive
- Enforced with `Field(ge=0, le=5)`

**Referential Integrity:**
- Review.product_id must exist in Product.id
- Checked during review normalization using product_ids set
- If not found, add to quarantine with error: "unknown product_id: [value]"

**Uniqueness:**
- Product.id: Must be unique (primary key)
- Review: Must be unique on (product_id, review_date, text)
- Policy: Must be unique on (policy_type, description, timeframe_days)

**Date Format:**
- Review dates must be ISO format YYYY-MM-DD
- Reject: "09/10/2026", "2026-9-10", "invalid"
- Error: "date must use ISO YYYY-MM-DD format"

**Conditions Parsing:**
- Pipe-delimited string split into list: "a | b | c" → ["a", "b", "c"]
- Each condition must be non-empty after stripping whitespace
- Error: "conditions must contain only non-empty values"

#### Error Handling
- **max_invalid_rows**: 0 (zero-tolerance for strict data quality)
- **Error collection**: Quarantine all invalid rows with full context
- **Failure mode**: Fail fast on first error
- **Quarantine fields**: source, row_number, record_key, error_type, message, raw_values

---

## 4. Pipeline Architecture

### 4.1 High-Level Flow

```
START (run_dry_run or run_full_pipeline)
  │
  ├─► PATH RESOLUTION
  │    └─ Validate SHOPENSEMBLE_DATA_ROOT exists
  │       Default: [project_root]/data
  │
  ├─► PHASE 1: LOAD & VALIDATE PRODUCTS
  │    ├─ iter_csv_rows('products.csv')
  │    │  └─ Validate headers match exactly
  │    ├─ normalize_product_row() for each row
  │    │  ├─ _require_value(): Strip whitespace, reject nulls
  │    │  ├─ _parse_decimal(): Convert price
  │    │  ├─ _parse_int(): Convert stock
  │    │  └─ _parse_float(): Convert rating
  │    ├─ Pydantic model validation
  │    │  └─ Validate: id pattern, name length, category pattern, price > 0, rating 0-5
  │    ├─ iter_validated_batches(batch_size=500)
  │    │  └─ Group rows, collect errors in quarantine
  │    └─ Extract product_ids = {p.id for batch for p in batch}
  │       (Used for review referential validation)
  │
  ├─► PHASE 2: LOAD & VALIDATE REVIEWS
  │    ├─ iter_csv_rows('reviews.csv')
  │    ├─ normalize_review_row(row, product_ids) for each row
  │    │  ├─ _require_value(): product_id, text
  │    │  ├─ Check product_id in product_ids (referential)
  │    │  ├─ _parse_float(): rating
  │    │  └─ Parse date ISO format
  │    ├─ Pydantic model validation
  │    │  └─ Validate: product_id exists, rating 0-5, text length, date format
  │    └─ iter_validated_batches(batch_size=500)
  │       └─ Group rows, collect errors
  │
  ├─► PHASE 3: LOAD & VALIDATE POLICIES
  │    ├─ iter_csv_rows('store_policies.csv')
  │    ├─ normalize_policy_row() for each row
  │    │  ├─ _require_value(): policy_type, description, conditions, timeframe
  │    │  ├─ Parse pipe-delimited conditions
  │    │  │  └─ Split on "|", strip whitespace, reject empty strings
  │    │  └─ _parse_int(): timeframe_days
  │    ├─ Pydantic model validation
  │    │  └─ Validate: policy_type enum, description length, conditions non-empty, timeframe >= 0
  │    └─ iter_validated_batches(batch_size=500)
  │       └─ Group rows, collect errors
  │
  ├─► REPORT GENERATION
  │    ├─ Calculate metrics:
  │    │  ├─ rows_read: Raw rows from CSV
  │    │  ├─ rows_validated: Rows that passed validation
  │    │  ├─ rows_persisted: Rows written to DB (if full run)
  │    │  └─ quarantine: Invalid rows with error context
  │    └─ Set status: "dry_run" or "completed" or "failed"
  │
  ├─► DECISION: DRY RUN or FULL RUN?
  │    │
  │    ├─ DRY RUN MODE ✗ (STOP HERE)
  │    │    └─ Return PipelineRunReport
  │    │
  │    └─ FULL RUN MODE ✓ (Continue below)
  │         │
  │         ├─► CREATE DATABASE ENGINE
  │         │    └─ create_engine()
  │         │       Connects using SHOPENSEMBLE_DATABASE_URL env var
  │         │       Driver: postgresql+asyncpg
  │         │
  │         ├─► CREATE SCHEMA
  │         │    └─ await create_schema(engine)
  │         │       Creates tables:
  │         │       ├─ products (8 columns, indexes)
  │         │       ├─ reviews (5 columns, FK, unique constraint)
  │         │       └─ store_policies (4 columns, JSONB, unique constraint)
  │         │
  │         ├─► CREATE SESSION FACTORY
  │         │    └─ create_session_factory(engine)
  │         │       For transaction management
  │         │
  │         └─► PERSIST BATCHES
  │              For each product batch:
  │              │ await persist_batch(session, products=batch)
  │              │ Strategy: UPSERT on id (update if exists)
  │              │
  │              For each review batch:
  │              │ await persist_batch(session, reviews=batch)
  │              │ Strategy: INSERT-or-IGNORE (skip if duplicate)
  │              │
  │              For each policy batch:
  │              └─ await persist_batch(session, policies=batch)
  │                 Strategy: UPSERT on identity (update conditions)
  │
  ├─► CLEANUP
  │    └─ await engine.dispose()
  │
  └─► RETURN REPORT
       PipelineRunReport with final metrics
```

### 4.2 Component Breakdown

| Component | Module | Key Functions | Purpose |
|-----------|--------|----------------|---------|
| **Paths** | `paths.py` | `resolve_data_root()`, `resolve_source_path()` | Safe file path resolution |
| **Ingestion** | `ingestion.py` | `iter_csv_rows()`, `SourceRow` | Stream CSV rows with metadata |
| **ETL** | `etl.py` | `normalize_*_row()`, `iter_validated_batches()` | Type conversion, validation, batching |
| **Orchestrator** | `orchestrator.py` | `run_dry_run()`, `PipelineRunReport` | Dry-run implementation |
| **Persistence** | `persistence.py` | `create_engine()`, `create_schema()`, `persist_batch()` | Database operations |
| **Main** | `main.py` | `run_full_pipeline()` | Full-run with persistence (TBD) |

### 4.3 Processing Modes

#### Mode 1: Dry Run (Currently Implemented) ✅

```
python -c "
from app.pipeline.orchestrator import run_dry_run

report = run_dry_run(
    data_root=None,        # Use default: [project]/data
    batch_size=500,        # Process 500 rows at a time
    max_invalid_rows=0     # Fail on first error
)

print(f'Status: {report.status}')
print(f'Duration: {report.duration_seconds}s')
print(f'Rows read: {report.rows_read}')
print(f'Rows validated: {report.rows_validated}')
print(f'Invalid: {len(report.quarantine)}')
"
```

**Output:**
```
Status: dry_run
Duration: 2.34s
Rows read: {'products': 1000, 'reviews': 5000, 'policies': 50}
Rows validated: {'products': 1000, 'reviews': 5000, 'policies': 50}
Invalid: 0
```

#### Mode 2: Full Run (Not Yet Implemented) ⚠️

```python
import asyncio
from app.main import run_full_pipeline

# Set environment first
export SHOPENSEMBLE_DATABASE_URL=postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble

asyncio.run(run_full_pipeline(
    data_root=None,    # Use default
    batch_size=500
))
```

**Output:**
```
✅ Persisted 2 product batches
✅ Persisted 10 review batches
✅ Persisted 1 policy batch
✅ All records inserted successfully!
```

---

## 5. Database Design

### 5.1 PostgreSQL Schema

#### Table: products

```sql
CREATE TABLE products (
    id VARCHAR(7) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    description TEXT NOT NULL,
    stock INTEGER NOT NULL,
    rating NUMERIC(3, 2) NOT NULL,
    
    -- Indexes for query performance
    CREATE INDEX idx_products_brand ON products(brand);
    CREATE INDEX idx_products_category ON products(category);
    CREATE INDEX idx_products_price ON products(price);
    CREATE INDEX idx_products_rating ON products(rating);
);
```

**Characteristics:**
- **Primary Key**: id (stable product identifier)
- **Indexes**: brand, category, price, rating (common filter columns)
- **Updates**: UPSERT strategy (update if id exists)

#### Table: reviews

```sql
CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id VARCHAR(7) NOT NULL,
    rating NUMERIC(3, 2) NOT NULL,
    text TEXT NOT NULL,
    review_date DATE NOT NULL,
    
    -- Foreign key to products
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    
    -- Prevent duplicate reviews
    UNIQUE CONSTRAINT uq_review_identity 
        ON (product_id, review_date, text),
    
    -- Indexes
    CREATE INDEX idx_reviews_product_id ON reviews(product_id);
    CREATE INDEX idx_reviews_rating ON reviews(rating);
);
```

**Characteristics:**
- **Primary Key**: id (auto-incremented)
- **Foreign Key**: product_id → products.id (CASCADE on delete)
- **Unique Constraint**: (product_id, review_date, text)
- **Persistence Strategy**: INSERT-or-IGNORE (skip duplicates)
- **Safe on Rerun**: Yes, duplicate rows are silently skipped

#### Table: store_policies

```sql
CREATE TABLE store_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_type VARCHAR(32) NOT NULL,
    description VARCHAR(300) NOT NULL,
    conditions JSONB NOT NULL,           -- PostgreSQL JSON array
    timeframe_days INTEGER NOT NULL,
    
    -- Prevent duplicate policies
    UNIQUE CONSTRAINT uq_policy_identity 
        ON (policy_type, description, timeframe_days),
    
    -- Indexes
    CREATE INDEX idx_store_policies_type ON store_policies(policy_type);
);
```

**Characteristics:**
- **Primary Key**: id (auto-incremented)
- **Conditions**: PostgreSQL JSONB type (structured array)
- **Unique Constraint**: (policy_type, description, timeframe_days)
- **Persistence Strategy**: UPSERT on identity (update conditions)
- **Safe on Rerun**: Yes, conditions are updated, not duplicated

### 5.2 Upsert Strategies

| Table | Strategy | Conflict Key | Action | Rationale |
|-------|----------|--------------|--------|-----------|
| **products** | UPSERT | `id` | UPDATE all fields | Product catalog is mutable (prices, stock, rating change) |
| **reviews** | INSERT-or-IGNORE | `(product_id, review_date, text)` | SKIP if exists | Reviews are immutable; duplicates safe to skip |
| **store_policies** | UPSERT | `(policy_type, description, timeframe_days)` | UPDATE conditions | Policy conditions may change; identity remains |

**Examples:**

```sql
-- Product UPSERT (update existing)
INSERT INTO products (...) VALUES (...)
ON CONFLICT (id) DO UPDATE SET 
    name = EXCLUDED.name,
    price = EXCLUDED.price,
    stock = EXCLUDED.stock,
    rating = EXCLUDED.rating;

-- Review INSERT-or-IGNORE (skip duplicate)
INSERT INTO reviews (...) VALUES (...)
ON CONFLICT (product_id, review_date, text) DO NOTHING;

-- Policy UPSERT (update conditions)
INSERT INTO store_policies (...) VALUES (...)
ON CONFLICT (policy_type, description, timeframe_days) DO UPDATE SET
    conditions = EXCLUDED.conditions;
```

---

## 6. Implementation Roadmap

### Phase 1: Dry Run ✅ COMPLETE
- [x] Define domain models (Pydantic)
- [x] Create normalization functions
- [x] Define validation rules
- [x] Implement CSV ingestion
- [x] Implement type conversion
- [x] Implement batching logic
- [x] Implement quarantine collection
- [x] Implement dry-run orchestrator
- [x] Write unit tests

### Phase 2: Database Setup 🔄 IN PROGRESS
- [ ] Create ORM models (SQLAlchemy)
- [ ] Design database schema
- [ ] Implement schema creation
- [ ] Set up PostgreSQL locally for testing

### Phase 3: Persistence Implementation 📋 PLANNED
- [ ] Implement upsert logic for each entity
- [ ] Implement transaction handling
- [ ] Test with real data
- [ ] Test conflict resolution
- [ ] Test rollback on errors

### Phase 4: Orchestration ⏳ PLANNED
- [ ] Create full-run orchestrator
- [ ] Add error handling
- [ ] Add logging/monitoring
- [ ] Generate reports

### Phase 5: Deployment & Operations ⏳ PLANNED
- [ ] Create CLI/API interface
- [ ] Add environment configuration
- [ ] Test end-to-end pipeline
- [ ] Document operational procedures
- [ ] Set up monitoring/alerts

---

## 7. Commands & Usage

### 7.1 Prerequisites

```bash
# Python environment
python --version  # 3.10+
pip install -r requirements.txt

# PostgreSQL database (for full run)
brew install postgresql  # macOS
# or docker run -d -p 5432:5432 postgres:13
```

### 7.2 Environment Variables

```bash
# Data root (optional, default: [project]/data)
export SHOPENSEMBLE_DATA_ROOT=/path/to/data

# Database URL (required for full run, optional for dry run)
export SHOPENSEMBLE_DATABASE_URL=postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble

# Or use default (localhost, no password)
# postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble
```

### 7.3 Run Dry Run (Validation Only)

```bash
# Simple command
python -c "
from app.pipeline.orchestrator import run_dry_run
report = run_dry_run()
print(f'Status: {report.status}')
print(f'Products: {report.rows_validated.get(\"products\", 0)} validated')
print(f'Reviews: {report.rows_validated.get(\"reviews\", 0)} validated')
print(f'Policies: {report.rows_validated.get(\"policies\", 0)} validated')
"

# Or via Python script
python << 'EOF'
from app.pipeline.orchestrator import run_dry_run

report = run_dry_run(
    data_root=None,        # Default: [project]/data
    batch_size=500,        # Process 500 rows at a time
    max_invalid_rows=0     # Zero-tolerance for errors
)

print(f"Run ID: {report.run_id}")
print(f"Status: {report.status}")
print(f"Duration: {report.duration_seconds:.2f}s")
print()
print("Rows read:")
for source, count in report.rows_read.items():
    print(f"  {source}: {count}")
print()
print("Rows validated:")
for source, count in report.rows_validated.items():
    print(f"  {source}: {count}")

if report.quarantine:
    print()
    print(f"ERRORS FOUND: {len(report.quarantine)} invalid rows")
    for record in report.quarantine[:10]:  # Show first 10
        print(f"  {record.source}:{record.row_number} - {record.message}")
        if record.record_key:
            print(f"    Key: {record.record_key}")
else:
    print()
    print("✅ No validation errors!")
EOF
```

### 7.4 Run Full Pipeline (With Persistence)

```bash
# Set database connection first
export SHOPENSEMBLE_DATABASE_URL=postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble

# Run full pipeline (to be implemented)
python << 'EOF'
import asyncio
from app.main import run_full_pipeline

asyncio.run(run_full_pipeline(
    data_root=None,    # Default: [project]/data
    batch_size=500     # Process 500 rows at a time
))
EOF
```

### 7.5 Query Database

```bash
# Connect to database
psql $SHOPENSEMBLE_DATABASE_URL

# Count records
SELECT COUNT(*) as product_count FROM products;
SELECT COUNT(*) as review_count FROM reviews;
SELECT COUNT(*) as policy_count FROM store_policies;

# Check for duplicates
SELECT id, COUNT(*) FROM products GROUP BY id HAVING COUNT(*) > 1;
SELECT (product_id, review_date, text), COUNT(*) FROM reviews GROUP BY (product_id, review_date, text) HAVING COUNT(*) > 1;

# View some data
SELECT * FROM products LIMIT 5;
SELECT * FROM reviews WHERE product_id = 'SP0001' LIMIT 5;
SELECT * FROM store_policies LIMIT 5;
```

---

## 8. Error Handling & Recovery

### 8.1 Common Validation Errors

| Error Message | Cause | CSV Example | Solution |
|---------------|-------|-------------|----------|
| "id is missing" | ID is empty | `,name,brand,...` | Fill in product ID |
| "price is not a valid decimal" | Non-numeric price | `SP0001,Widget,Brand,cat,abc,...` | Use number format |
| "stock is not a valid integer" | Non-integer stock | `SP0001,Widget,Brand,cat,19.99,Desc,100.5` | Use integer |
| "rating must be finite" | Rating is NaN or Inf | `SP0001,Widget,Brand,cat,19.99,Desc,100,inf` | Use 0.0-5.0 |
| "unknown product_id: XXX" | Review refs non-existent product | Review for product "INVALID" | Load products first |
| "date must use ISO YYYY-MM-DD format" | Wrong date format | `2026/09/10` or `09-10-2026` | Use YYYY-MM-DD |
| "conditions must contain only non-empty values" | Pipe-delimited has empty | `returns\|Policy\|\|Another` | No empty conditions |
| "category pattern mismatch" | Category not lowercase | `Electronics` | Use lowercase |

### 8.2 Error Recovery Strategy

**Dry Run Error:**
1. Check quarantine records: `report.quarantine`
2. Review error message and CSV row number
3. Fix data in source CSV
4. Re-run dry-run to verify fix
5. Once successful, proceed to full run

**Full Run Error:**
1. Fix data in source CSV (same as dry run)
2. Note: UPSERT will handle duplicates safely on rerun
   - Products: Updated (old values replaced)
   - Reviews: Skipped (unique constraint prevents duplicates)
   - Policies: Updated (conditions updated)
3. Re-run full pipeline

### 8.3 Quarantine Record Analysis

```python
from app.pipeline.orchestrator import run_dry_run

report = run_dry_run()

# Group errors by type
from collections import defaultdict
errors_by_type = defaultdict(list)
for record in report.quarantine:
    errors_by_type[record.error_type].append(record)

print(f"Normalization errors: {len(errors_by_type['normalization'])}")
print(f"Validation errors: {len(errors_by_type['validation'])}")

# Show unique error messages
unique_messages = set()
for record in report.quarantine:
    unique_messages.add(record.message)

print("\nUnique errors:")
for msg in sorted(unique_messages):
    count = sum(1 for r in report.quarantine if r.message == msg)
    print(f"  [{count}] {msg}")
```

---

## 9. Performance Considerations

### 9.1 Current Constraints

- **Products**: ~1,000 rows
- **Reviews**: ~5,000 rows (cached product IDs in memory)
- **Policies**: ~50 rows
- **Batch Size**: 500 (default)
- **Memory Usage**: <500MB (small datasets)

### 9.2 Optimization Parameters

| Parameter | Current | Min | Max | Impact |
|-----------|---------|-----|-----|--------|
| batch_size | 500 | 1 | 5000 | Memory, throughput |
| max_invalid_rows | 0 | 0 | unlimited | Fail-fast vs. collect-all |

### 9.3 Performance Profile

**Dry Run (validation only):**
```
~2-5 seconds for full dataset
- CSV reading: ~0.5s
- Normalization: ~1s
- Validation: ~1s
- Batching: ~0.5s
```

**Full Run (validation + persistence):**
```
~5-10 seconds (estimate)
- All of dry run: ~5s
- Schema creation: <1s
- Batch persistence: ~2-4s
- Commit/cleanup: <1s
```

**Scaling Consideration:**
- Product ID set: 1,000 products = negligible memory
- At 1M products: ~100MB memory (product ID lookup set)
- Batch processing: Constant memory (one batch at a time)

---

## 10. Monitoring & Metrics

### 10.1 Pipeline Report

```python
report = run_dry_run()

print(f"Run ID: {report.run_id}")  # shopensemble-20260910T143022Z
print(f"Status: {report.status}")  # dry_run, completed, or failed
print(f"Started: {report.started_at}")
print(f"Ended: {report.ended_at}")
print(f"Duration: {report.duration_seconds}s")
print()
print("Input:")
print(f"  Products: {report.rows_read.get('products', 0)}")
print(f"  Reviews: {report.rows_read.get('reviews', 0)}")
print(f"  Policies: {report.rows_read.get('policies', 0)}")
print()
print("Validated:")
print(f"  Products: {report.rows_validated.get('products', 0)}")
print(f"  Reviews: {report.rows_validated.get('reviews', 0)}")
print(f"  Policies: {report.rows_validated.get('policies', 0)}")
print()
print("Persisted (full run only):")
print(f"  Products: {report.rows_persisted.get('products', 0)}")
print(f"  Reviews: {report.rows_persisted.get('reviews', 0)}")
print(f"  Policies: {report.rows_persisted.get('policies', 0)}")
print()
print(f"Retries: {report.retries}")
print(f"Invalid rows: {len(report.quarantine)}")
```

### 10.2 Success Criteria

- [ ] All source rows successfully read
- [ ] Validation pass rate = 100%
- [ ] Processing time < 10 seconds
- [ ] No quarantine records
- [ ] All batches persisted successfully (full run)
- [ ] Row counts match between validation and persistence
- [ ] Database queries return expected counts

---

## 11. References

### 11.1 File Structure

```
shopensemble/
├─ app/
│  ├─ __init__.py
│  ├─ models.py                   # Domain models
│  │  ├─ Product
│  │  ├─ Review
│  │  └─ StorePolicy
│  └─ pipeline/
│     ├─ __init__.py
│     ├─ persistence.py           # DB operations (phase 3-5)
│     │  ├─ create_engine()
│     │  ├─ create_schema()
│     │  ├─ create_session_factory()
│     │  ├─ persist_batch()
│     │  └─ ORM models
│     ├─ orchestrator.py          # Dry-run (phase 1-2) ✅
│     │  └─ run_dry_run()
│     ├─ ingestion.py             # CSV reading
│     │  └─ iter_csv_rows()
│     ├─ etl.py                   # Validation
│     │  ├─ normalize_product_row()
│     │  ├─ normalize_review_row()
│     │  ├─ normalize_policy_row()
│     │  └─ iter_validated_batches()
│     └─ paths.py                 # Path resolution
│        └─ resolve_source_path()
├─ main.py                        # Full-run orchestrator (TBD)
├─ data/
│  ├─ products.csv
│  ├─ reviews.csv
│  └─ store_policies.csv
├─ tests/
│  ├─ pipeline/
│  │  ├─ test_orchestrator.py    # Dry-run tests
│  │  ├─ test_ingestion.py
│  │  ├─ test_etl.py
│  │  ├─ test_persistence.py     # DB schema tests
│  │  └─ test_paths.py
│  └─ conftest.py
└─ requirements.txt
```

### 11.2 Technology Stack

- **Language**: Python 3.10+
- **Async**: asyncio
- **ORM**: SQLAlchemy 2.0
- **Validation**: Pydantic 2.0
- **Database**: PostgreSQL 13+
- **CSV**: csv module (stdlib)
- **Testing**: pytest

### 11.3 Environment Variables

```bash
# Data directory (optional)
SHOPENSEMBLE_DATA_ROOT=/Users/anushrin/Documents/AG/ShopEnsemble/data

# Database connection (required for full run)
SHOPENSEMBLE_DATABASE_URL=postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble

# Logging (optional)
LOG_LEVEL=INFO
```

### 11.4 Learning Resources

- **Sequence Flow Diagram**: `/Reference/Learning/datapipeline/pipeline-sequence-flow.html`
- **Command & API Reference**: `/Reference/Learning/datapipeline/pipeline-reference.md`
- **Template**: `/skills/SpecToolBox/FULL_DATA_PIPELINE_SPEC_TEMPLATE.md`

---

## 12. Development Phases Summary

| Phase | Status | Deliverable | Timeline |
|-------|--------|-------------|----------|
| Phase 1: Dry Run | ✅ COMPLETE | `run_dry_run()` function | ✓ Complete |
| Phase 2: Database Setup | 🔄 IN PROGRESS | PostgreSQL schema | This week |
| Phase 3: Persistence | 📋 PLANNED | `persist_batch()` implementation | Next week |
| Phase 4: Orchestration | ⏳ PLANNED | `run_full_pipeline()` function | Following week |
| Phase 5: Deployment | ⏳ PLANNED | CLI/monitoring | Final week |

---

## Appendix A: Quick Start Commands

```bash
# 1. Setup environment
cd /Users/anushrin/Documents/AG/ShopEnsemble
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run dry-run validation
python -c "
from app.pipeline.orchestrator import run_dry_run
report = run_dry_run()
print(f'Status: {report.status}')
print(f'Validated: {report.rows_validated}')
"

# 3. Setup database (when full run is ready)
export SHOPENSEMBLE_DATABASE_URL=postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble
psql $SHOPENSEMBLE_DATABASE_URL < setup.sql

# 4. Run full pipeline (when full run is ready)
python app/main.py
```

---

**Document History**
- **v1.0** (2026-09-10): Initial specification
  - Phase 1 (Dry Run) complete
  - Phases 2-5 planned
  - Generic template created for SpecToolBox

**Next Review**: After Phase 2 completion
