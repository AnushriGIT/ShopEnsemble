"""Tests for ShopEnsemble streaming CSV ingestion."""

from pathlib import Path

import pytest

from app.pipeline.ingestion import (
    IngestionError,
    PRODUCT_HEADERS,
    iter_csv_rows,
)


def write_product_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_iter_csv_rows_preserves_source_and_row_metadata(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    write_product_csv(
        data_root / "products.csv",
        "id,name,brand,category,price,description,stock,rating\n"
        "SP0001,Phone,TechCo,smartphone,10.00,Good phone,3,4.0\n",
    )

    rows = list(iter_csv_rows("products.csv", PRODUCT_HEADERS, data_root))

    assert rows[0].row_number == 2
    assert rows[0].source_path == (data_root / "products.csv").resolve()
    assert rows[0].values["id"] == "SP0001"


def test_iter_csv_rows_rejects_unexpected_headers(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    write_product_csv(data_root / "products.csv", "id,name\nSP0001,Phone\n")

    with pytest.raises(IngestionError, match="Unexpected headers"):
        list(iter_csv_rows("products.csv", PRODUCT_HEADERS, data_root))


def test_iter_csv_rows_rejects_extra_values(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    write_product_csv(
        data_root / "products.csv",
        "id,name,brand,category,price,description,stock,rating\n"
        "SP0001,Phone,TechCo,smartphone,10.00,Good phone,3,4.0,extra\n",
    )

    with pytest.raises(IngestionError, match="Malformed row"):
        list(iter_csv_rows("products.csv", PRODUCT_HEADERS, data_root))
