"""In-memory catalog/review data access for agents.

Phase 1 reads product and review data from CSV into memory at process start
(spec Section 3, "Phase 1 data access") rather than querying the PostgreSQL
persistence layer. This mirrors the load-and-validate sequence already used
by ``app.pipeline.orchestrator._run_validation_phase``, minus the
report/quarantine bookkeeping that orchestration needs but agents don't.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.models import PolicyType, Product, Review, StorePolicy
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

# Recommendation candidates are capped the same way review_agent caps reviews
# per summary call — bound the prompt, favor the most relevant (here: highest
# rated) records rather than an arbitrary CSV-order slice.
MAX_RECOMMENDATION_CANDIDATES = 20


@dataclass(frozen=True)
class CatalogData:
    """Validated product, review, and policy records held in memory for agent use."""

    products: list[Product]
    reviews: list[Review]
    policies: list[StorePolicy]


def load_catalog_data(
    data_root: str | Path | None = None,
    batch_size: int = 500,
    max_invalid_rows: int = 0,
) -> CatalogData:
    """Load and validate ``products.csv``/``reviews.csv``/``store_policies.csv`` into memory.

    Invalid rows are silently quarantined up to ``max_invalid_rows`` (default
    zero-tolerance, matching the pipeline's default) rather than surfaced —
    agents don't need the report/quarantine detail that
    ``app.pipeline.orchestrator`` builds for pipeline runs.
    """

    quarantine: list[QuarantineRecord] = []

    product_rows = iter_csv_rows("products.csv", PRODUCT_HEADERS, data_root)
    product_batches = iter_validated_batches(
        product_rows, normalize_product_row, quarantine, batch_size, max_invalid_rows
    )
    products = [product for batch in product_batches for product in batch]
    product_ids = {product.id for product in products}

    review_rows = iter_csv_rows("reviews.csv", REVIEW_HEADERS, data_root)
    review_batches = iter_validated_batches(
        review_rows,
        lambda row: normalize_review_row(row, product_ids),
        quarantine,
        batch_size,
        max_invalid_rows,
    )
    reviews = [review for batch in review_batches for review in batch]

    policy_rows = iter_csv_rows("store_policies.csv", POLICY_HEADERS, data_root)
    policy_batches = iter_validated_batches(
        policy_rows, normalize_policy_row, quarantine, batch_size, max_invalid_rows
    )
    policies = [policy for batch in policy_batches for policy in batch]

    return CatalogData(products=products, reviews=reviews, policies=policies)


def reviews_for_product(catalog: CatalogData, product_id: str) -> list[Review]:
    """Return every review for ``product_id``, or an empty list if none exist."""

    return [review for review in catalog.reviews if review.product_id == product_id]


def product_exists(catalog: CatalogData, product_id: str) -> bool:
    """Return whether ``product_id`` is a known catalog product."""

    return any(product.id == product_id for product in catalog.products)


def products_by_ids(catalog: CatalogData, product_ids: list[str]) -> list[Product]:
    """Return the catalog products matching ``product_ids``, in *request* order.

    Order follows ``product_ids`` (not catalog order) and repeated IDs yield
    one product. Phase 5 spec B5: with session memory, "the first one" is a
    valid follow-up reference, so the order shown on screen must equal the
    order the customer asked in. Unknown IDs are silently omitted — callers
    (``comparison_agent``) check the returned count against the requested
    count to detect misses.
    """

    by_id = {product.id: product for product in catalog.products}
    ordered: list[Product] = []
    seen: set[str] = set()
    for product_id in product_ids:
        if product_id in by_id and product_id not in seen:
            seen.add(product_id)
            ordered.append(by_id[product_id])
    return ordered


def filter_products(
    catalog: CatalogData,
    max_price: Decimal | None = None,
    category: str | None = None,
) -> list[Product]:
    """Return catalog products matching the given filters, highest-rated first.

    Capped to ``MAX_RECOMMENDATION_CANDIDATES`` so the recommendation prompt
    stays bounded, the same rationale as ``review_agent``'s review cap.
    """

    candidates = catalog.products
    if max_price is not None:
        candidates = [product for product in candidates if product.price <= max_price]
    if category is not None:
        # Defense-in-depth against the LLM extracting a near-miss category
        # (plural, mixed case) despite the coordinator prompt listing the
        # exact values — observed via manual smoke testing ("speakers" vs.
        # the catalog's "speaker"). Try an exact match first, then a
        # case-insensitive singular/plural-tolerant fallback.
        normalized = category.strip().casefold().removesuffix("s")
        exact_matches = [product for product in candidates if product.category == category]
        candidates = exact_matches or [
            product for product in candidates if product.category.casefold().removesuffix("s") == normalized
        ]

    return sorted(candidates, key=lambda product: product.rating, reverse=True)[
        :MAX_RECOMMENDATION_CANDIDATES
    ]


def policies_by_type(catalog: CatalogData, policy_type: PolicyType | None) -> list[StorePolicy]:
    """Return policies matching ``policy_type``, or every policy if ``None``."""

    if policy_type is None:
        return list(catalog.policies)
    return [policy for policy in catalog.policies if policy.policy_type == policy_type]
