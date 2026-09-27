"""Integration tests for the ShopEnsemble persistence boundary against a live
PostgreSQL instance (started via `docker compose up -d postgres`).

These tests exercise `create_schema`/`persist_batch` for real: schema
creation, upsert behavior, foreign-key/unique-constraint enforcement,
transaction atomicity, and idempotent reruns. Unlike `test_persistence.py`
(sync contract tests, always run), everything here is marked `integration`
and is skipped automatically when PostgreSQL isn't reachable (see
`tests/conftest.py`).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Product, Review, StorePolicy
from app.pipeline.persistence import (
    ProductRecord,
    ReviewRecord,
    StorePolicyRecord,
    persist_batch,
)

pytestmark = pytest.mark.integration


def _product(**overrides) -> Product:
    values = {
        "id": "SP0001",
        "name": "Widget Pro",
        "brand": "TechBrand",
        "category": "electronics",
        "price": Decimal("19.99"),
        "description": "Premium widget device",
        "stock": 100,
        "rating": 4.5,
    }
    values.update(overrides)
    return Product.model_validate(values)


def _review(**overrides) -> Review:
    values = {
        "product_id": "SP0001",
        "rating": 4.5,
        "text": "Great product!",
        "date": date(2026, 9, 10),
    }
    values.update(overrides)
    return Review.model_validate(values)


def _policy(**overrides) -> StorePolicy:
    values = {
        "policy_type": "returns",
        "description": "30-day returns",
        "conditions": ["Keep original packaging", "Item in resale condition"],
        "timeframe": 30,
    }
    values.update(overrides)
    return StorePolicy.model_validate(values)


async def test_create_schema_declares_exactly_the_three_domain_tables(db_engine, clean_schema):
    # `clean_schema` performs the drop-all/create-all this test verifies; it
    # must be requested explicitly rather than assuming another test already
    # created the schema first (test order is not guaranteed, and
    # `clean_schema`'s own teardown drops everything again afterward).
    async with db_engine.connect() as connection:
        table_names = await connection.run_sync(lambda conn: conn.dialect.get_table_names(conn))
    assert set(table_names) == {"products", "reviews", "store_policies"}


async def test_product_upsert_overwrites_existing_row_in_place(db_session_factory):
    async with db_session_factory() as session:
        async with session.begin():
            await persist_batch(session, products=[_product(price=Decimal("19.99"))])

    async with db_session_factory() as session:
        async with session.begin():
            await persist_batch(session, products=[_product(price=Decimal("24.99"), stock=50)])

    async with db_session_factory() as session:
        rows = (await session.execute(select(ProductRecord))).scalars().all()

    assert len(rows) == 1
    assert rows[0].price == Decimal("24.99")
    assert rows[0].stock == 50


async def test_review_with_orphan_product_id_is_rejected(db_session_factory):
    # No product with id "SP9999" has been persisted in this clean schema.
    with pytest.raises(IntegrityError):
        async with db_session_factory() as session:
            async with session.begin():
                await persist_batch(session, reviews=[_review(product_id="SP9999")])

    async with db_session_factory() as session:
        rows = (await session.execute(select(ReviewRecord))).scalars().all()
    assert rows == []


async def test_persist_batch_rolls_back_entire_transaction_on_partial_failure(
    db_session_factory,
):
    # products=[valid] and reviews=[orphan] are persisted in ONE persist_batch
    # call, i.e. one transaction. The orphan review's FK violation must roll
    # back the product insert too, proving persist_batch is all-or-nothing.
    with pytest.raises(IntegrityError):
        async with db_session_factory() as session:
            async with session.begin():
                await persist_batch(
                    session,
                    products=[_product()],
                    reviews=[_review(product_id="SP9999")],
                )

    async with db_session_factory() as session:
        product_rows = (await session.execute(select(ProductRecord))).scalars().all()
        review_rows = (await session.execute(select(ReviewRecord))).scalars().all()

    assert product_rows == []
    assert review_rows == []


async def test_duplicate_review_is_ignored_on_rerun(db_session_factory):
    async with db_session_factory() as session:
        async with session.begin():
            await persist_batch(session, products=[_product()])

    review = _review()
    for _ in range(2):
        async with db_session_factory() as session:
            async with session.begin():
                await persist_batch(session, reviews=[review])

    async with db_session_factory() as session:
        rows = (await session.execute(select(ReviewRecord))).scalars().all()
    assert len(rows) == 1


async def test_policy_upsert_replaces_conditions_for_same_identity(db_session_factory):
    async with db_session_factory() as session:
        async with session.begin():
            await persist_batch(session, policies=[_policy(conditions=["Original condition"])])

    async with db_session_factory() as session:
        async with session.begin():
            await persist_batch(
                session, policies=[_policy(conditions=["Updated condition", "Second condition"])]
            )

    async with db_session_factory() as session:
        rows = (await session.execute(select(StorePolicyRecord))).scalars().all()

    assert len(rows) == 1
    assert rows[0].conditions == ["Updated condition", "Second condition"]


async def test_rerunning_an_identical_batch_is_idempotent(db_session_factory):
    batch = {
        "products": [_product()],
        "reviews": [_review()],
        "policies": [_policy()],
    }

    for _ in range(2):
        async with db_session_factory() as session:
            async with session.begin():
                await persist_batch(session, **batch)

    async with db_session_factory() as session:
        product_rows = (await session.execute(select(ProductRecord))).scalars().all()
        review_rows = (await session.execute(select(ReviewRecord))).scalars().all()
        policy_rows = (await session.execute(select(StorePolicyRecord))).scalars().all()

    assert len(product_rows) == 1
    assert len(review_rows) == 1
    assert len(policy_rows) == 1
