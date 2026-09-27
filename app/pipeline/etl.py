"""Pure normalization, validation, quarantine, and batching for ShopEnsemble rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable, TypeVar

from pydantic import ValidationError

from app.models import Product, Review, StorePolicy
from app.pipeline.ingestion import SourceRow

ModelT = TypeVar("ModelT", Product, Review, StorePolicy)

NULL_TOKENS = frozenset({"", "NA", "N/A", "NULL", "-"})


@dataclass(frozen=True)
class QuarantineRecord:
    """Sanitized context for a row rejected during normalization or validation."""

    source: str
    row_number: int
    record_key: str | None
    error_type: str
    message: str
    raw_values: dict[str, str]


def _require_value(value: str, field_name: str) -> str:
    """Normalize one required string and reject known missing-value tokens."""

    normalized = value.strip()
    if normalized.upper() in NULL_TOKENS:
        raise ValueError(f"{field_name} is missing")
    return normalized


def _parse_decimal(value: str, field_name: str) -> Decimal:
    """Parse finite decimal data so monetary values avoid float rounding."""

    normalized = _require_value(value, field_name)
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(f"{field_name} is not a valid decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _parse_float(value: str, field_name: str) -> float:
    """Parse finite floating-point data for ratings and similar measures."""

    normalized = _require_value(value, field_name)
    try:
        parsed = float(normalized)
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid number") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _parse_int(value: str, field_name: str) -> int:
    """Parse an integer field while preserving a field-specific error message."""

    normalized = _require_value(value, field_name)
    try:
        return int(normalized)
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid integer") from error


def normalize_product_row(row: SourceRow) -> Product:
    """Convert and validate one raw product row."""

    # Convert raw CSV strings before Pydantic validation so domain models see
    # the same types that later persistence code will receive.
    values = row.values
    return Product.model_validate(
        {
            "id": _require_value(values["id"], "id"),
            "name": _require_value(values["name"], "name"),
            "brand": _require_value(values["brand"], "brand"),
            "category": _require_value(values["category"], "category"),
            "price": _parse_decimal(values["price"], "price"),
            "description": _require_value(values["description"], "description"),
            "stock": _parse_int(values["stock"], "stock"),
            "rating": _parse_float(values["rating"], "rating"),
        }
    )


def normalize_review_row(row: SourceRow, product_ids: set[str]) -> Review:
    """Convert and validate one review, including its product reference."""

    values = row.values
    product_id = _require_value(values["product_id"], "product_id")
    # Referential validation belongs here because the ETL layer knows the
    # catalog key set while the Pydantic model only knows field shape.
    if product_id not in product_ids:
        raise ValueError(f"unknown product_id: {product_id}")
    try:
        review_date = date.fromisoformat(_require_value(values["date"], "date"))
    except ValueError as error:
        raise ValueError("date must use ISO YYYY-MM-DD format") from error

    return Review.model_validate(
        {
            "product_id": product_id,
            "rating": _parse_float(values["rating"], "rating"),
            "text": _require_value(values["text"], "text"),
            "date": review_date,
        }
    )


def normalize_policy_row(row: SourceRow) -> StorePolicy:
    """Convert and validate one policy, including its pipe-delimited conditions."""

    values = row.values
    raw_conditions = _require_value(values["conditions"], "conditions")
    # The source stores a list in one pipe-delimited CSV cell; normalize it
    # once here so every downstream layer uses a structured list.
    conditions = [condition.strip() for condition in raw_conditions.split("|")]
    if any(not condition for condition in conditions):
        raise ValueError("conditions must contain only non-empty values")

    return StorePolicy.model_validate(
        {
            "policy_type": _require_value(values["policy_type"], "policy_type"),
            "description": _require_value(values["description"], "description"),
            "conditions": conditions,
            "timeframe": _parse_int(values["timeframe"], "timeframe"),
        }
    )


def _error_type(error: Exception) -> str:
    """Map validation failures and conversion failures to report categories."""

    if isinstance(error, ValidationError):
        return "validation"
    return "normalization"


def iter_validated_batches(
    rows: Iterable[SourceRow],
    normalizer: Callable[[SourceRow], ModelT],
    quarantine: list[QuarantineRecord],
    batch_size: int = 500,
    max_invalid_rows: int = 0,
) -> Iterable[list[ModelT]]:
    """Yield bounded valid batches and collect rejected rows for reporting."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if max_invalid_rows < 0:
        raise ValueError("max_invalid_rows cannot be negative")

    # Keep only one bounded batch in memory while quarantine retains the
    # diagnostic context required by the run report.
    batch: list[ModelT] = []
    for row in rows:
        try:
            record = normalizer(row)
        except (ValidationError, ValueError, KeyError) as error:
            # Invalid rows are recorded before the threshold decision so a
            # failed run still explains which source record caused the failure.
            quarantine.append(
                QuarantineRecord(
                    source=row.source_path.name,
                    row_number=row.row_number,
                    record_key=(row.values.get("id") or row.values.get("product_id")),
                    error_type=_error_type(error),
                    message=str(error),
                    raw_values=dict(row.values),
                )
            )
            # The curated ShopEnsemble datasets currently use a zero-invalid-row
            # policy; callers can deliberately provide a larger threshold.
            if len(quarantine) > max_invalid_rows:
                raise ValueError(
                    f"invalid row threshold exceeded: {len(quarantine)} > "
                    f"{max_invalid_rows}"
                ) from error
            continue

        batch.append(record)
        if len(batch) == batch_size:
            yield batch
            batch = []

    if batch:
        yield batch
