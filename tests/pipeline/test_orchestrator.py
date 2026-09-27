"""Tests for ShopEnsemble pipeline orchestration and dry-run reporting."""

from pathlib import Path

import pytest

from app.pipeline.orchestrator import run_dry_run


def test_dry_run_validates_all_real_source_rows():
    report = run_dry_run()

    assert report.status == "dry_run"
    assert report.rows_read == {"products": 2000, "reviews": 4000, "policies": 22}
    assert report.rows_validated == report.rows_read
    assert report.quarantine == []
    assert report.duration_seconds is not None


def test_dry_run_fails_before_partial_success_when_invalid_rows_exceed_threshold(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "products.csv").write_text(
        "id,name,brand,category,price,description,stock,rating\n"
        "bad,Phone,TechCo,smartphone,10.00,Phone,1,4.0\n",
        encoding="utf-8",
    )
    (data_root / "reviews.csv").write_text(
        "product_id,rating,text,date\n",
        encoding="utf-8",
    )
    (data_root / "store_policies.csv").write_text(
        "policy_type,description,conditions,timeframe\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="threshold exceeded"):
        run_dry_run(data_root=data_root)
