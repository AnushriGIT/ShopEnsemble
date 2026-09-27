"""PostgreSQL persistence boundary for validated ShopEnsemble records."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from time import monotonic

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.models import Product, Review, StorePolicy

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://shopensemble:shopensemble@localhost:5432/shopensemble"
)
DATABASE_URL_ENV = "SHOPENSEMBLE_DATABASE_URL"


class Base(DeclarativeBase):
    """Base class collecting ShopEnsemble PostgreSQL table metadata."""


class ProductRecord(Base):
    """Relational catalog record with a stable product identifier."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, index=True)


class ReviewRecord(Base):
    """Review record linked to its product by a foreign key."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "review_date", "text", name="uq_review_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(7),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)


class StorePolicyRecord(Base):
    """Policy record with validated conditions stored as PostgreSQL JSONB."""

    __tablename__ = "store_policies"
    __table_args__ = (
        UniqueConstraint(
            "policy_type",
            "description",
            "timeframe_days",
            name="uq_policy_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframe_days: Mapped[int] = mapped_column(Integer, nullable=False)


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an async PostgreSQL engine from configuration."""

    # Keep connection details outside source control while allowing tests to
    # inject a deterministic URL directly.
    url = database_url or os.getenv(DATABASE_URL_ENV) or DEFAULT_DATABASE_URL
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create the async session factory used by pipeline writes."""

    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine: AsyncEngine) -> None:
    """Create the declared tables for local development and tests."""

    # DDL runs through an explicit transaction so schema creation is complete
    # before callers begin inserting pipeline batches.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def persist_batch(
    session: AsyncSession,
    products: Sequence[Product] = (),
    reviews: Sequence[Review] = (),
    policies: Sequence[StorePolicy] = (),
) -> None:
    """Upsert one validated batch inside the caller's transaction."""

    # Each entity is written only when its batch is non-empty; the caller owns
    # the surrounding transaction and decides when all writes are committed.
    if products:
        product_rows = [
            {
                "id": product.id,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "price": product.price,
                "description": product.description,
                "stock": product.stock,
                "rating": product.rating,
            }
            for product in products
        ]
        product_insert = insert(ProductRecord).values(product_rows)
        # Products are mutable catalog records, so reruns update the existing
        # stable ID instead of creating duplicates.
        await session.execute(
            product_insert.on_conflict_do_update(
                index_elements=[ProductRecord.id],
                set_={
                    "name": product_insert.excluded.name,
                    "brand": product_insert.excluded.brand,
                    "category": product_insert.excluded.category,
                    "price": product_insert.excluded.price,
                    "description": product_insert.excluded.description,
                    "stock": product_insert.excluded.stock,
                    "rating": product_insert.excluded.rating,
                },
            )
        )

    if reviews:
        review_rows = [
            {
                "product_id": review.product_id,
                "rating": review.rating,
                "text": review.text,
                "review_date": review.date,
            }
            for review in reviews
        ]
        review_insert = insert(ReviewRecord).values(review_rows)
        # Review identity is enforced by the unique constraint; duplicate
        # source rows are harmless on rerun.
        await session.execute(
            review_insert.on_conflict_do_nothing(index_elements=[
                "product_id",
                "review_date",
                "text",
            ])
        )

    if policies:
        policy_rows = [
            {
                "policy_type": policy.policy_type,
                "description": policy.description,
                "conditions": policy.conditions,
                "timeframe_days": policy.timeframe,
            }
            for policy in policies
        ]
        policy_insert = insert(StorePolicyRecord).values(policy_rows)
        # Policy conditions may change while the policy identity remains the
        # same, so conflicts update the JSONB payload.
        await session.execute(
            policy_insert.on_conflict_do_update(
                index_elements=[
                    "policy_type",
                    "description",
                    "timeframe_days",
                ],
                set_={"conditions": policy_insert.excluded.conditions},
            )
        )


@dataclass(frozen=True)
class RetryStats:
    """Retry and timing metrics for one ``persist_batch_with_retry`` call."""

    retries: int
    latency_seconds: float


async def persist_batch_with_retry(
    session_factory: async_sessionmaker[AsyncSession],
    products: Sequence[Product] = (),
    reviews: Sequence[Review] = (),
    policies: Sequence[StorePolicy] = (),
    *,
    max_retries: int = 3,
    backoff_base_seconds: float = 0.5,
    backoff_max_seconds: float = 8.0,
) -> RetryStats:
    """Persist one batch, retrying only bounded transient connection failures.

    A fresh session and transaction is opened on every attempt: a session that
    failed mid-flush is left in a non-reusable state, so retrying inside the
    same session risks masking the original failure. ``OperationalError``
    (connection refused, pool timeout, disconnects) is treated as transient
    per the governing spec's error-handling table; any other exception
    (constraint violations, programming errors) is a data or code problem and
    is raised immediately with no retry and no backoff delay.
    """
    started = monotonic()
    attempts = 0

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(OperationalError),
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential_jitter(initial=backoff_base_seconds, max=backoff_max_seconds),
        reraise=True,
    ):
        with attempt:
            attempts += 1
            async with session_factory() as session:
                async with session.begin():
                    await persist_batch(session, products=products, reviews=reviews, policies=policies)

    return RetryStats(retries=attempts - 1, latency_seconds=monotonic() - started)
