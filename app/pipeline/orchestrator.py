"""Pipeline orchestration and dry-run/full-run reporting for ShopEnsemble source data."""

from __future__ import annotations  # Evaluate type hints without runtime ordering issues.

from dataclasses import dataclass, field  # Build the run report with defaults.
from datetime import datetime, timezone  # Store UTC start and finish timestamps.
from pathlib import Path  # Accept platform-independent data directory paths.
from time import monotonic  # Measure elapsed execution time safely.

from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Product, Review, StorePolicy
from app.pipeline.etl import (
    QuarantineRecord,
    iter_validated_batches,
    normalize_policy_row,
    normalize_product_row,
    normalize_review_row,
)
from app.pipeline.ingestion import (
    POLICY_HEADERS,
    PRODUCT_HEADERS,
    REVIEW_HEADERS,
    iter_csv_rows,
)
from app.pipeline.persistence import (
    create_engine,
    create_schema,
    create_session_factory,
    persist_batch_with_retry,
)


@dataclass
class PipelineRunReport:
    """Short-lived result object containing one pipeline run's status and metrics."""

    run_id: str  # Identifies this run in logs and future reports.
    status: str = "running"  # Becomes dry_run, success, or failed when execution finishes.
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    rows_read: dict[str, int] = field(default_factory=dict)  # Raw rows per source.
    rows_validated: dict[str, int] = field(default_factory=dict)  # Accepted rows.
    rows_persisted: dict[str, int] = field(default_factory=dict)  # Rows written per source (full run only).
    retries: int = 0  # Persistence retry count, summed across all batches.
    batch_count: int = 0  # Number of batches persisted (full run only).
    persistence_latency_seconds: float = 0.0  # Cumulative time inside successful persist calls.
    quarantine: list[QuarantineRecord] = field(default_factory=list)  # Rejected rows.

    @property
    def duration_seconds(self) -> float | None:
        """Return elapsed wall time when the run has finished."""

        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()

    def finish(self, status: str) -> None:
        """Set the terminal status and completion timestamp."""

        self.status = status
        self.ended_at = datetime.now(timezone.utc)


@dataclass
class _ValidatedBatches:
    """Validated batches for one run, ready for either reporting or persistence."""

    products: list[list[Product]]
    reviews: list[list[Review]]
    policies: list[list[StorePolicy]]


def _run_id() -> str:
    """Create a UTC identifier that is sortable and useful in logs."""

    return datetime.now(timezone.utc).strftime("shopensemble-%Y%m%dT%H%M%SZ")


def _count_rows(source: str, source_rows) -> tuple[list, int]:
    """Materialize one source iterator and return its rows plus count."""

    # The current dry run needs product IDs before it can validate reviews.
    rows = list(source_rows)
    return rows, len(rows)


def _run_validation_phase(
    data_root: str | Path | None,
    batch_size: int,
    max_invalid_rows: int,
    report: PipelineRunReport,
) -> _ValidatedBatches:
    """Load, normalize, and validate all three sources into ``report``.

    Shared by ``run_dry_run`` and ``run_full_pipeline`` so the fail-fast,
    zero-invalid-row threshold logic exists in exactly one place. Only what
    happens after this call (stop and report vs. persist) differs between
    the two modes.
    """

    # Products are loaded first because reviews require their IDs for
    # referential validation.
    product_rows, product_count = _count_rows(
        "products",
        iter_csv_rows("products.csv", PRODUCT_HEADERS, data_root),
    )
    report.rows_read["products"] = product_count
    product_batches = list(
        iter_validated_batches(
            product_rows,
            normalize_product_row,
            report.quarantine,
            batch_size,
            max_invalid_rows,
        )
    )
    report.rows_validated["products"] = sum(len(batch) for batch in product_batches)
    product_ids = {product.id for batch in product_batches for product in batch}

    # Review normalization receives the validated product key set rather
    # than querying the database, keeping validation deterministic.
    review_rows, review_count = _count_rows(
        "reviews",
        iter_csv_rows("reviews.csv", REVIEW_HEADERS, data_root),
    )
    report.rows_read["reviews"] = review_count
    review_batches = list(
        iter_validated_batches(
            review_rows,
            lambda row: normalize_review_row(row, product_ids),
            report.quarantine,
            batch_size,
            max_invalid_rows,
        )
    )
    report.rows_validated["reviews"] = sum(len(batch) for batch in review_batches)

    # Policies are independent of the catalog but still pass through the
    # same batch, quarantine, and threshold machinery.
    policy_rows, policy_count = _count_rows(
        "policies",
        iter_csv_rows("store_policies.csv", POLICY_HEADERS, data_root),
    )
    report.rows_read["policies"] = policy_count
    policy_batches = list(
        iter_validated_batches(
            policy_rows,
            normalize_policy_row,
            report.quarantine,
            batch_size,
            max_invalid_rows,
        )
    )
    report.rows_validated["policies"] = sum(len(batch) for batch in policy_batches)

    return _ValidatedBatches(
        products=product_batches, reviews=review_batches, policies=policy_batches
    )


def run_dry_run(
    data_root: str | Path | None = None,
    batch_size: int = 500,
    max_invalid_rows: int = 0,
) -> PipelineRunReport:
    """Validate all ShopEnsemble CSVs without writing to PostgreSQL.

    ``str | Path | None`` allows a text path, a pathlib path, or the default
    configured data directory. The return annotation promises a run report.
    """

    report = PipelineRunReport(run_id=_run_id())
    started = monotonic()
    try:
        _run_validation_phase(data_root, batch_size, max_invalid_rows, report)
        report.finish("dry_run")
    except Exception as error:
        # Preserve the failed status for callers while re-raising the original
        # exception so CLI/API layers can decide how to present it. Attaching
        # the report lets a caller (e.g. app/main.py) still write out the
        # quarantine detail after a fail-fast validation error.
        report.finish("failed")
        error.pipeline_report = report
        raise
    finally:
        _ = monotonic() - started

    return report


async def run_full_pipeline(
    data_root: str | Path | None = None,
    database_url: str | None = None,
    batch_size: int = 500,
    max_invalid_rows: int = 0,
    max_retries: int = 3,
    backoff_base_seconds: float = 0.5,
    backoff_max_seconds: float = 8.0,
    engine: AsyncEngine | None = None,
) -> PipelineRunReport:
    """Validate all ShopEnsemble CSVs, then persist them to PostgreSQL.

    Reuses the same validation phase as ``run_dry_run`` so the fail-fast,
    zero-invalid-row threshold policy is identical between modes; only the
    persistence tail differs. ``engine`` is injectable so callers that
    already manage an engine's lifecycle (tests, long-lived services) can
    pass one in; when omitted, this function creates its own engine from
    ``database_url`` (or ``SHOPENSEMBLE_DATABASE_URL``/the built-in default)
    and disposes it before returning.

    Checkpoint/resume support is intentionally not implemented: at the
    current data volume (2,000 products / 4,000 reviews / 22 policies) a
    full rerun is cheap, and because ``persist_batch`` upserts/ignores on
    conflict, reruns are already idempotent without needing to resume from a
    partial run.
    """

    report = PipelineRunReport(run_id=_run_id())
    started = monotonic()
    owns_engine = engine is None
    try:
        validated = _run_validation_phase(data_root, batch_size, max_invalid_rows, report)

        engine = engine or create_engine(database_url)
        try:
            await create_schema(engine)
            session_factory = create_session_factory(engine)

            for source_name, batches, kwarg in (
                ("products", validated.products, "products"),
                ("reviews", validated.reviews, "reviews"),
                ("policies", validated.policies, "policies"),
            ):
                persisted = 0
                for batch in batches:
                    stats = await persist_batch_with_retry(
                        session_factory,
                        max_retries=max_retries,
                        backoff_base_seconds=backoff_base_seconds,
                        backoff_max_seconds=backoff_max_seconds,
                        **{kwarg: batch},
                    )
                    report.batch_count += 1
                    report.retries += stats.retries
                    report.persistence_latency_seconds += stats.latency_seconds
                    persisted += len(batch)
                report.rows_persisted[source_name] = persisted
        finally:
            if owns_engine:
                await engine.dispose()

        report.finish("success")
    except Exception as error:
        report.finish("failed")
        error.pipeline_report = report
        raise
    finally:
        _ = monotonic() - started

    return report
