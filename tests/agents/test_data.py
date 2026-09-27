"""Tests for the in-memory catalog/review/policy loader (Phases 1-2)."""

from decimal import Decimal
from pathlib import Path

from app.agents.data import (
    filter_products,
    load_catalog_data,
    policies_by_type,
    product_exists,
    products_by_ids,
    reviews_for_product,
)


def _write_catalog(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "products.csv").write_text(
        "id,name,brand,category,price,description,stock,rating\n"
        "SP0001,Widget Pro,TechCo,speaker,49.99,A fine speaker,10,4.5\n"
        "SP0002,Widget Lite,TechCo,speaker,29.99,A lighter speaker,5,4.0\n"
        "LP0003,Laptop Pro,TechCo,laptop,999.99,A fast laptop,3,4.8\n",
        encoding="utf-8",
    )
    (data_root / "reviews.csv").write_text(
        "product_id,rating,text,date\n"
        "SP0001,5.0,Loved it!,2025-01-01\n"
        "SP0001,4.0,Pretty good.,2025-01-02\n",
        encoding="utf-8",
    )
    (data_root / "store_policies.csv").write_text(
        "policy_type,description,conditions,timeframe\n"
        'returns,"Speaker Return Policy","No physical damage|Original packaging",15\n'
        'warranty,"Laptop Warranty","1 year manufacturer warranty",365\n',
        encoding="utf-8",
    )
    return data_root


def test_load_catalog_data_loads_products_reviews_and_policies(tmp_path: Path):
    data_root = _write_catalog(tmp_path)

    catalog = load_catalog_data(data_root=data_root)

    assert {product.id for product in catalog.products} == {"SP0001", "SP0002", "LP0003"}
    assert len(catalog.reviews) == 2
    assert {policy.policy_type for policy in catalog.policies} == {"returns", "warranty"}


def test_reviews_for_product_filters_by_product_id(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    assert len(reviews_for_product(catalog, "SP0001")) == 2
    assert reviews_for_product(catalog, "SP0002") == []


def test_product_exists_reflects_the_loaded_catalog(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    assert product_exists(catalog, "SP0001") is True
    assert product_exists(catalog, "SP9999") is False


def test_products_by_ids_returns_only_known_ids(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    found = products_by_ids(catalog, ["SP0001", "SP9999", "LP0003"])

    assert {product.id for product in found} == {"SP0001", "LP0003"}


def test_products_by_ids_preserves_request_order_and_dedupes(tmp_path: Path):
    # Phase 5 spec B5: results follow the order the IDs were requested in (not
    # catalog order), so the order shown on screen matches what "the first
    # one" later refers to. A repeated ID yields one product, not two.
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    found = products_by_ids(catalog, ["LP0003", "SP0001", "LP0003", "SP9999"])

    assert [product.id for product in found] == ["LP0003", "SP0001"]


def test_filter_products_by_max_price_and_category(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    by_price = filter_products(catalog, max_price=Decimal("50.00"))
    assert {product.id for product in by_price} == {"SP0001", "SP0002"}

    by_category = filter_products(catalog, category="laptop")
    assert {product.id for product in by_category} == {"LP0003"}

    by_both = filter_products(catalog, max_price=Decimal("50.00"), category="laptop")
    assert by_both == []


def test_filter_products_tolerates_a_plural_or_mixed_case_category(tmp_path: Path):
    # Defense-in-depth against an LLM-extracted near-miss like "Speakers"
    # instead of the catalog's exact "speaker" (observed via manual testing).
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    assert {p.id for p in filter_products(catalog, category="Speakers")} == {"SP0001", "SP0002"}
    assert {p.id for p in filter_products(catalog, category="speaker")} == {"SP0001", "SP0002"}


def test_filter_products_ranks_highest_rated_first(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    results = filter_products(catalog, category="speaker")

    assert [product.id for product in results] == ["SP0001", "SP0002"]  # 4.5 before 4.0


def test_policies_by_type_filters_and_falls_back_to_all(tmp_path: Path):
    data_root = _write_catalog(tmp_path)
    catalog = load_catalog_data(data_root=data_root)

    assert [policy.policy_type for policy in policies_by_type(catalog, "returns")] == ["returns"]
    assert len(policies_by_type(catalog, None)) == 2
