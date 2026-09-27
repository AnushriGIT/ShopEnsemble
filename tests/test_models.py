"""Contract tests for the ShopEnsemble Pydantic domain models."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Product, Review, StorePolicy


PRODUCT_PAYLOAD = {
    "id": "SP0001",
    "name": " Wireless Headphones ",
    "brand": "TechCo",
    "category": "audio_device",
    "price": "59.99",
    "description": "Wireless headphones with noise cancellation.",
    "stock": 43,
    "rating": 4.0,
}


REVIEW_PAYLOAD = {
    "product_id": "SP0001",
    "rating": 4.5,
    "text": " Battery lasts all day. ",
    "date": "2024-12-18",
}


POLICY_PAYLOAD = {
    "policy_type": "returns",
    "description": "Laptop Return Policy",
    "conditions": [
        " Laptop must be unopened ",
        "All original accessories must be included",
    ],
    "timeframe": 14,
}


@pytest.mark.parametrize(
    "policy_type",
    [
        "exchanges",
        "financing",
        "preorder",
        "price_matching",
        "repairs",
        "returns",
        "shipping",
        "warranty",
    ],
)
def test_store_policy_accepts_all_source_policy_types(policy_type):
    policy = StorePolicy.model_validate({**POLICY_PAYLOAD, "policy_type": policy_type})

    assert policy.policy_type == policy_type


def test_store_policy_accepts_zero_timeframe_for_non_duration_policy():
    # Regression test for data/store_policies.csv: shipping policies use timeframe 0.
    policy = StorePolicy.model_validate(
        {**POLICY_PAYLOAD, "policy_type": "shipping", "timeframe": 0}
    )

    assert policy.timeframe == 0


def test_product_validates_and_preserves_typed_price():
    product = Product.model_validate(PRODUCT_PAYLOAD)

    assert product.id == "SP0001"
    assert product.name == "Wireless Headphones"
    assert product.price == Decimal("59.99")
    assert product.stock == 43


def test_product_accepts_three_letter_speaker_identifier():
    # Regression test for data/products.csv: speaker records use the SPK#### prefix.
    product = Product.model_validate({**PRODUCT_PAYLOAD, "id": "SPK0441"})

    assert product.id == "SPK0441"


def test_review_validates_and_parses_iso_date():
    review = Review.model_validate(REVIEW_PAYLOAD)

    assert review.product_id == "SP0001"
    assert review.text == "Battery lasts all day."
    assert review.date == date(2024, 12, 18)


def test_store_policy_normalizes_condition_whitespace():
    policy = StorePolicy.model_validate(POLICY_PAYLOAD)

    assert policy.conditions == [
        "Laptop must be unopened",
        "All original accessories must be included",
    ]


@pytest.mark.parametrize("rating", [-0.1, 5.1])
def test_product_rejects_rating_outside_inclusive_five_point_scale(rating):
    # Boundary regression: catalog ratings must remain within the documented 0-5 range.
    payload = {**PRODUCT_PAYLOAD, "rating": rating}

    with pytest.raises(ValidationError, match="rating"):
        Product.model_validate(payload)


@pytest.mark.parametrize("field, value", [("price", 0), ("stock", -1)])
def test_product_rejects_invalid_numeric_boundaries(field, value):
    # Boundary regression: non-positive prices and negative stock are invalid inventory data.
    payload = {**PRODUCT_PAYLOAD, field: value}

    with pytest.raises(ValidationError, match=field):
        Product.model_validate(payload)


def test_product_rejects_invalid_identifier():
    # Identifier contract: source keys use two or three uppercase letters and four digits.
    payload = {**PRODUCT_PAYLOAD, "id": "product-1"}

    with pytest.raises(ValidationError, match="id"):
        Product.model_validate(payload)


def test_review_rejects_non_iso_date():
    # Date contract: CSV dates must be parsed as ISO calendar dates.
    payload = {**REVIEW_PAYLOAD, "date": "18-12-2024"}

    with pytest.raises(ValidationError, match="date"):
        Review.model_validate(payload)


def test_store_policy_rejects_unsupported_policy_type():
    payload = {**POLICY_PAYLOAD, "policy_type": "exchange"}

    with pytest.raises(ValidationError, match="policy_type"):
        StorePolicy.model_validate(payload)


def test_store_policy_rejects_blank_condition():
    # Input contract: splitting a pipe-delimited CSV value must not create blank rules.
    payload = {**POLICY_PAYLOAD, "conditions": ["valid condition", "   "]}

    with pytest.raises(ValidationError, match="conditions"):
        StorePolicy.model_validate(payload)


def test_models_reject_unknown_fields():
    # Strictness contract: undeclared client fields must not be silently accepted.
    payload = {**PRODUCT_PAYLOAD, "supplier_secret": "hidden"}

    with pytest.raises(ValidationError, match="supplier_secret"):
        Product.model_validate(payload)


def test_models_serialize_only_declared_fields():
    product = Product.model_validate(PRODUCT_PAYLOAD)

    assert set(product.model_dump()) == {
        "id",
        "name",
        "brand",
        "category",
        "price",
        "description",
        "stock",
        "rating",
    }
    assert '"id":"SP0001"' in product.model_dump_json()
