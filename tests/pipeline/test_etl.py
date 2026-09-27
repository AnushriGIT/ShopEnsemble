"""Tests for ShopEnsemble normalization and validation behavior."""

from pathlib import Path

import pytest

from app.pipeline.etl import (
    QuarantineRecord,
    iter_validated_batches,
    normalize_policy_row,
    normalize_product_row,
    normalize_review_row,
)
from app.pipeline.ingestion import SourceRow


def source_row(values: dict[str, str], row_number: int = 2) -> SourceRow:
    return SourceRow(Path("fixture.csv"), row_number, values)


def product_values() -> dict[str, str]:
    return {
        "id": "SPK0441",
        "name": " ClearSound ",
        "brand": "AudioMax",
        "category": "speaker",
        "price": "62.43",
        "description": "Speaker delivering wireless connectivity.",
        "stock": "197",
        "rating": "4.0",
    }


def test_normalize_product_converts_numeric_fields():
    product = normalize_product_row(source_row(product_values()))

    assert product.id == "SPK0441"
    assert str(product.price) == "62.43"
    assert product.stock == 197


def test_normalize_review_checks_product_reference_and_date():
    review = normalize_review_row(
        source_row(
            {
                "product_id": "SPK0441",
                "rating": "4.0",
                "text": "Great sound.",
                "date": "2024-12-18",
            }
        ),
        {"SPK0441"},
    )

    assert review.product_id == "SPK0441"
    assert review.date.isoformat() == "2024-12-18"


def test_normalize_policy_splits_pipe_delimited_conditions_and_zero_timeframe():
    policy = normalize_policy_row(
        source_row(
            {
                "policy_type": "shipping",
                "description": "Free shipping",
                "conditions": "Minimum order|Contiguous address",
                "timeframe": "0",
            }
        )
    )

    assert policy.conditions == ["Minimum order", "Contiguous address"]
    assert policy.timeframe == 0


@pytest.mark.parametrize("field, value", [("price", "nan"), ("rating", "inf")])
def test_normalizers_reject_non_finite_numbers(field, value):
    # NaN/infinity must not bypass domain bounds or reach persistence.
    values = {**product_values(), field: value}

    with pytest.raises(ValueError, match="finite"):
        normalize_product_row(source_row(values))


def test_iter_validated_batches_quarantines_and_reports_invalid_rows():
    quarantine: list[QuarantineRecord] = []
    rows = [
        source_row(product_values(), row_number=2),
        source_row({**product_values(), "id": "bad"}, row_number=3),
    ]

    batches = list(
        iter_validated_batches(
            rows,
            normalize_product_row,
            quarantine,
            batch_size=1,
            max_invalid_rows=1,
        )
    )

    assert len(batches) == 1
    assert batches[0][0].id == "SPK0441"
    assert quarantine[0].row_number == 3
    assert quarantine[0].record_key == "bad"
    assert quarantine[0].error_type == "validation"


def test_iter_validated_batches_fails_when_invalid_threshold_is_exceeded():
    quarantine: list[QuarantineRecord] = []
    rows = [source_row({**product_values(), "id": "bad"})]

    with pytest.raises(ValueError, match="threshold exceeded"):
        list(
            iter_validated_batches(
                rows,
                normalize_product_row,
                quarantine,
                max_invalid_rows=0,
            )
        )
