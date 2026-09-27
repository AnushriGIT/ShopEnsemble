# Full Data Pipeline Specification Template

## Overview
This template provides a reusable specification framework for developing and running complete data pipelines with validation and database persistence. Use this template for any project requiring CSV ingestion, data transformation, and database storage.

---

## 1. Project Context

### 1.1 Project Name
**[Project Name]**

### 1.2 Data Pipeline Purpose
**[Describe the purpose of this data pipeline - what data is being loaded, validated, and stored?]**

### 1.3 Scope
- **Input**: [CSV files, APIs, databases, etc.]
- **Processing**: [Validation, transformation, enrichment]
- **Output**: [Database tables, reports, data warehouse]
- **Schedule**: [One-time load, daily, weekly, etc.]

### 1.4 Stakeholders
- **Data Owner**: [Name/Team]
- **Validator**: [Who approves the data?]
- **Consumer**: [Who uses the data?]

---

## 2. Data Sources

### 2.1 Input Files

| File Name | Format | Size | Frequency | Location |
|-----------|--------|------|-----------|----------|
| [File 1] | CSV | [~Rows] | [How often] | [Path] |
| [File 2] | CSV | [~Rows] | [How often] | [Path] |

### 2.2 File Headers & Validation

```
[File Name]: [Expected Headers]
Example: products.csv: id, name, brand, category, price, description, stock, rating
```

**Header Validation Rules:**
- Headers must match exactly (no case changes, additions, or removals)
- Row count must be predictable (alert if >N% deviation)
- Encoding must be UTF-8

### 2.3 Data Characteristics

| File | Row Count | Data Type | Key Field | Dependencies |
|------|-----------|-----------|-----------|--------------|
| [File 1] | [Estimated] | [Master/Transaction] | [Primary Key] | None / [Depends on File 2] |
| [File 2] | [Estimated] | [Transaction] | [Primary Key] | [File 1] via FK |

---

## 3. Data Model & Validation Rules

### 3.1 Entity Models

#### [Entity 1 Name]
```
Field Name      | Type      | Required | Constraints         | Example
────────────────┼───────────┼──────────┼─────────────────────┼──────────────
id              | String    | Yes      | Pattern: [REGEX]    | SP0001
name            | String    | Yes      | Length: [1-200]     | Widget Pro
price           | Decimal   | Yes      | > 0, 2 decimals    | 19.99
rating          | Float     | Yes      | Range: [0-5]        | 4.5
stock           | Integer   | Yes      | >= 0               | 100
```

#### [Entity 2 Name]
```
Field Name      | Type      | Required | Constraints         | Example
────────────────┼───────────┼──────────┼─────────────────────┼──────────────
id              | Integer   | Auto     | Primary Key         | 1
[fk_field]      | String    | Yes      | Foreign Key → [Entity 1] | SP0001
rating          | Float     | Yes      | Range: [0-5]        | 4.5
date            | Date      | Yes      | ISO Format YYYY-MM-DD | 2026-09-10
```

### 3.2 Validation Rules

#### Type Conversions
- **Decimal fields** (prices): Use `Decimal` type to avoid float rounding errors
- **Integers** (counts, stock): Parse as `int`, reject non-integer values
- **Floats** (ratings): Parse as `float`, reject NaN/Infinity
- **Dates**: ISO format YYYY-MM-DD only

#### Business Rules
- **Required fields**: Must have non-empty value (reject "", "NA", "N/A", "NULL", "-")
- **Referential integrity**: [Entity 2] must reference existing [Entity 1] keys
- **Uniqueness**: [Field names that must be unique]
- **Pattern matching**: [Any regex patterns to validate]

#### Error Handling
- **max_invalid_rows**: [0 for zero-tolerance, N for threshold]
- **Error collection**: Quarantine all invalid rows with full context
- **Failure mode**: [Fail fast vs. collect all errors]

---

## 4. Pipeline Architecture

### 4.1 High-Level Flow

```
START
  │
  ├─► PHASE 1: Load & Validate [Source 1]
  │     ├─ Read CSV → Validate headers
  │     ├─ Normalize types
  │     ├─ Validate with business rules
  │     └─ Batch rows (size: [N])
  │
  ├─► Extract reference keys for downstream validation
  │
  ├─► PHASE 2: Load & Validate [Source 2]
  │     ├─ Read CSV → Validate headers
  │     ├─ Normalize types
  │     ├─ Referential validation (check FK)
  │     └─ Batch rows (size: [N])
  │
  ├─► [More phases as needed]
  │
  ├─► Decision: Dry Run or Full Run?
  │     │
  │     ├─ DRY RUN: Return validation report (STOP)
  │     │
  │     └─ FULL RUN: Continue to persistence
  │           ├─ Create database schema
  │           ├─ Create session factory
  │           └─ For each batch: Upsert/Insert
  │
  └─► END: Return pipeline report
```

### 4.2 Component Breakdown

| Component | Purpose | Implementation |
|-----------|---------|-----------------|
| **Path Resolver** | Safe file path resolution | `resolve_source_path()` |
| **CSV Ingester** | Stream CSV rows | `iter_csv_rows()` |
| **Normalizer** | Type conversion | `normalize_*_row()` |
| **Validator** | Business rule validation | Pydantic models |
| **Batcher** | Group rows | `iter_validated_batches()` |
| **Quarantine** | Collect errors | `QuarantineRecord` |
| **Persister** | Upsert to DB | `persist_batch()` |

### 4.3 Processing Modes

#### Mode 1: Dry Run (Validation Only)
```
INPUT: CSV files
  ↓
PROCESS: Read → Normalize → Validate → Batch
  ↓
OUTPUT: PipelineRunReport
  ├─ rows_read
  ├─ rows_validated
  └─ quarantine (invalid rows)
```

#### Mode 2: Full Run (Validation + Persistence)
```
INPUT: CSV files
  ↓
PROCESS: (All of Dry Run, plus:)
  ├─ Create database engine
  ├─ Create schema
  └─ For each batch: Persist
  ↓
OUTPUT: PipelineRunReport
  ├─ rows_read
  ├─ rows_validated
  ├─ rows_persisted
  └─ quarantine (invalid rows)
```

---

## 5. Database Design

### 5.1 Schema

#### Table: [Entity 1]
```sql
CREATE TABLE [table_name] (
    id VARCHAR(7) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    field3 NUMERIC(12, 2) NOT NULL,
    INDEX idx_field2 (field2),
    INDEX idx_field3 (field3)
);
```

#### Table: [Entity 2]
```sql
CREATE TABLE [table_name] (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    [entity1_id] VARCHAR(7) NOT NULL,
    field2 FLOAT NOT NULL,
    date DATE NOT NULL,
    FOREIGN KEY fk_[entity1] ([entity1_id]) REFERENCES [entity1](id) ON DELETE CASCADE,
    UNIQUE CONSTRAINT uq_[entity2_identity] ([entity1_id], date, field3)
);
```

### 5.2 Upsert Strategies

| Table | Strategy | Key | Conflict Resolution |
|-------|----------|-----|-------------------|
| [Entity 1] | UPSERT | `id` | UPDATE all fields |
| [Entity 2] | INSERT-or-IGNORE | `(fk_id, date, ...)` | SKIP if exists |
| [Entity 3] | UPSERT | `(field1, field2)` | UPDATE specific columns |

**Rationale:**
- [Entity 1] is mutable (catalog updates)
- [Entity 2] is immutable (transaction logs)
- [Entity 3] allows condition updates

---

## 6. Implementation Checklist

### 6.1 Phase 1: Setup
- [ ] Define domain models (Pydantic)
- [ ] Create normalization functions
- [ ] Define validation rules
- [ ] Create ORM models
- [ ] Design database schema

### 6.2 Phase 2: Validation
- [ ] Implement CSV ingestion
- [ ] Implement type normalization
- [ ] Implement business validation
- [ ] Implement batching logic
- [ ] Implement quarantine collection
- [ ] Write unit tests for each component

### 6.3 Phase 3: Orchestration
- [ ] Implement dry-run orchestrator
- [ ] Track run metrics
- [ ] Generate reports
- [ ] Test with real data
- [ ] Validate error handling

### 6.4 Phase 4: Persistence
- [ ] Create database engine setup
- [ ] Implement schema creation
- [ ] Implement upsert logic
- [ ] Implement transaction handling
- [ ] Test persistence with real DB
- [ ] Test conflict resolution
- [ ] Test rollback on errors

### 6.5 Phase 5: Deployment
- [ ] Create full-run orchestrator
- [ ] Add environment configuration
- [ ] Add logging and monitoring
- [ ] Create CLI/API interface
- [ ] Test end-to-end pipeline
- [ ] Document operational procedures

---

## 7. Commands & Usage

### 7.1 Run Dry Run (Validation Only)

```bash
python -c "
from [module].orchestrator import run_dry_run

report = run_dry_run(
    data_root='[path_to_data]',  # Optional
    batch_size=500,               # Batch size
    max_invalid_rows=0            # Error threshold
)

print(f'Status: {report.status}')
print(f'Rows read: {report.rows_read}')
print(f'Rows validated: {report.rows_validated}')
print(f'Invalid: {len(report.quarantine)}')
"
```

### 7.2 Run Full Pipeline (Validation + Persistence)

```bash
# Set database connection
export [PROJECT]_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Run pipeline
python -c "
import asyncio
from [module].full_pipeline import run_full_pipeline

asyncio.run(run_full_pipeline(
    data_root='[path_to_data]',
    batch_size=500
))
"
```

### 7.3 Verify Data in Database

```bash
# Connect to database
psql [PROJECT]_DATABASE_URL

# Query results
SELECT COUNT(*) as product_count FROM [table_1];
SELECT COUNT(*) as transaction_count FROM [table_2];
SELECT COUNT(*) as error_count FROM [quarantine_table];

# Check for duplicates
SELECT [key_field], COUNT(*) 
FROM [table_name] 
GROUP BY [key_field] 
HAVING COUNT(*) > 1;
```

---

## 8. Error Handling & Recovery

### 8.1 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| **Header Mismatch** | CSV headers don't match expected | Verify source file format |
| **Type Conversion** | Invalid data type (e.g., "abc" as int) | Check data quality |
| **Referential Integrity** | FK references non-existent key | Ensure [Entity 1] loaded first |
| **Unique Constraint** | Duplicate key on rerun | This is expected; use UPSERT |
| **Connection Error** | Database not running | Start PostgreSQL/database |

### 8.2 Error Recovery

**Strategy 1: Fail Fast (max_invalid_rows=0)**
- Stop on first error
- Useful for strict data quality requirements
- Good for initial validation

**Strategy 2: Collect Errors (max_invalid_rows=N)**
- Allow N errors before failing
- Collect all quarantine records
- Good for production with alert thresholds

**Strategy 3: Rerun on Failure**
- Fix issues in source data
- Rerun pipeline
- UPSERT will handle duplicates safely

---

## 9. Monitoring & Reporting

### 9.1 Pipeline Report

```python
report = run_dry_run()

print(f"Run ID: {report.run_id}")
print(f"Status: {report.status}")
print(f"Duration: {report.duration_seconds}s")
print(f"Rows read: {report.rows_read}")
print(f"Rows validated: {report.rows_validated}")
print(f"Rows persisted: {report.rows_persisted}")
print(f"Quarantine: {len(report.quarantine)}")
```

### 9.2 Quarantine Records

```python
for record in report.quarantine:
    print(f"{record.source}:{record.row_number}")
    print(f"  Key: {record.record_key}")
    print(f"  Type: {record.error_type}")
    print(f"  Message: {record.message}")
    print(f"  Values: {record.raw_values}")
```

### 9.3 Success Metrics

- [ ] All source rows successfully read
- [ ] Validation pass rate > [%]
- [ ] Processing time < [seconds]
- [ ] No data quality alerts
- [ ] All batches persisted successfully
- [ ] Referential integrity verified

---

## 10. Performance Tuning

### 10.1 Optimization Parameters

| Parameter | Default | Range | Impact |
|-----------|---------|-------|--------|
| batch_size | 500 | 1-10000 | Memory usage, throughput |
| pool_size | 5 | 1-100 | Database connection pool |
| max_overflow | 10 | 0-50 | Extra temporary connections |

### 10.2 Tuning Guide

**For large datasets (>1M rows):**
```python
run_full_pipeline(
    batch_size=1000,      # Larger batches
    pool_size=20,         # More connections
    max_overflow=10
)
```

**For small datasets (<10K rows):**
```python
run_full_pipeline(
    batch_size=100,       # Smaller batches
    pool_size=5           # Fewer connections
)
```

**For memory-constrained environments:**
```python
run_full_pipeline(
    batch_size=50,        # Very small batches
    pool_size=2           # Minimal connections
)
```

---

## 11. References & Dependencies

### 11.1 Technology Stack

- **Language**: Python 3.10+
- **Async**: asyncio
- **ORM**: SQLAlchemy 2.0
- **Validation**: Pydantic 2.0
- **Database**: PostgreSQL 13+
- **CSV**: csv module (stdlib)

### 11.2 Key Files

```
[project]/
├─ app/
│  ├─ models.py          # Domain models (Pydantic)
│  ├─ pipeline/
│  │  ├─ persistence.py  # DB engine, schema, upserts
│  │  ├─ orchestrator.py # Dry-run implementation
│  │  ├─ ingestion.py    # CSV reading
│  │  ├─ etl.py          # Normalization & validation
│  │  └─ paths.py        # Path resolution
│  └─ main.py            # Full run implementation
└─ tests/
   └─ pipeline/          # Unit tests
```

### 11.3 Environment Variables

```bash
# Database connection
export [PROJECT]_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname

# Data directory
export [PROJECT]_DATA_ROOT=/path/to/data

# Logging
export LOG_LEVEL=INFO
```

---

## 12. Appendix: Quick Start

### 12.1 Minimal Example

```python
import asyncio
from app.pipeline.orchestrator import run_dry_run

# Test validation
report = run_dry_run()
print(f"Validated {report.rows_validated} rows")

# If successful, proceed to full run
if report.status == "dry_run" and not report.quarantine:
    from app.main import run_full_pipeline
    asyncio.run(run_full_pipeline())
```

### 12.2 Docker Setup

```dockerfile
FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

ENV [PROJECT]_DATABASE_URL=postgresql+asyncpg://...
CMD ["python", "app/main.py"]
```

---

**Version**: 1.0  
**Last Updated**: [Date]  
**Template Author**: [Name]
