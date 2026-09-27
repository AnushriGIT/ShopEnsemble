"""Contract tests for the ShopEnsemble PostgreSQL persistence boundary."""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateTable

from app.pipeline import persistence
from app.pipeline.persistence import (
    Base,
    StorePolicyRecord,
    create_engine,
)


def test_persistence_declares_all_domain_tables():
    assert set(Base.metadata.tables) == {"products", "reviews", "store_policies"}


def test_review_has_product_foreign_key_and_identity_constraint():
    review_table = Base.metadata.tables["reviews"]

    assert {str(key.column) for key in review_table.foreign_keys} == {"products.id"}
    assert "uq_review_identity" in {
        constraint.name for constraint in review_table.constraints
    }


def test_policy_uses_jsonb_and_unique_business_identity():
    policy_table = StorePolicyRecord.__table__
    compiled_sql = str(CreateTable(policy_table).compile(dialect=postgresql.dialect()))

    assert "JSONB" in compiled_sql
    assert "uq_policy_identity" in compiled_sql


def test_create_engine_uses_asyncpg_url():
    engine = create_engine("postgresql+asyncpg://user:pass@localhost/db")

    assert engine.url.drivername == "postgresql+asyncpg"
    engine.sync_engine.dispose()


class _FakeTransaction:
    """Minimal async context manager standing in for ``session.begin()``."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Minimal async context manager standing in for an ``AsyncSession``."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def begin(self):
        return _FakeTransaction()


def _fake_session_factory():
    # No real engine/session is needed: persist_batch itself is monkeypatched
    # below, so this factory only has to satisfy persist_batch_with_retry's
    # `async with session_factory() as session: async with session.begin():`
    # shape.
    return _FakeSession()


async def test_persist_batch_with_retry_recovers_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = {"count": 0}

    async def flaky_persist_batch(session, **kwargs):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise OperationalError("stmt", {}, Exception("connection reset"))

    monkeypatch.setattr(persistence, "persist_batch", flaky_persist_batch)

    stats = await persistence.persist_batch_with_retry(
        _fake_session_factory,
        products=[],
        max_retries=3,
        backoff_base_seconds=0.01,
        backoff_max_seconds=0.05,
    )

    assert calls["count"] == 3
    assert stats.retries == 2
    assert stats.latency_seconds >= 0


async def test_persist_batch_with_retry_fails_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = {"count": 0}

    async def always_fails(session, **kwargs):
        calls["count"] += 1
        raise OperationalError("stmt", {}, Exception("still down"))

    monkeypatch.setattr(persistence, "persist_batch", always_fails)

    with pytest.raises(OperationalError):
        await persistence.persist_batch_with_retry(
            _fake_session_factory,
            products=[],
            max_retries=2,
            backoff_base_seconds=0.01,
            backoff_max_seconds=0.02,
        )

    # 1 initial attempt + 2 retries = 3 total calls.
    assert calls["count"] == 3


async def test_persist_batch_with_retry_does_not_retry_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = {"count": 0}

    async def raises_value_error(session, **kwargs):
        calls["count"] += 1
        raise ValueError("not a transient connection failure")

    monkeypatch.setattr(persistence, "persist_batch", raises_value_error)

    with pytest.raises(ValueError):
        await persistence.persist_batch_with_retry(
            _fake_session_factory,
            products=[],
            max_retries=5,
        )

    # A non-OperationalError must fail immediately with zero retries/backoff.
    assert calls["count"] == 1
