"""Product-comparison sub-agent (spec Section 3, Phase 2 sub-agent)."""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.settings import ModelSettings

from app.agents.data import CatalogData, products_by_ids
from app.agents.models import (
    PRODUCT_ID_CITATION_RULE,
    AgentError,
    AgentErrorEnvelope,
    ComparisonRequest,
    ComparisonResponse,
)
from app.agents.retry import LLM_CALL_TIMEOUT_SECONDS, call_with_retry
from app.models import Product, ShopEnsembleModel

COMPARISON_SYSTEM_PROMPT = (
    "You compare a small set of products. Given their name, brand, "
    "category, price, rating, and description, list the meaningful "
    "differences between them (price, rating, brand, specific features "
    "mentioned in their descriptions) as short, distinct bullet points. "
    "Base every difference only on the data given — never invent a "
    "specification not present in the descriptions."
    + PRODUCT_ID_CITATION_RULE
)


class ComparisonAnalysis(ShopEnsembleModel):
    """Internal LLM output: just the differences, not the product records.

    The products themselves are already resolved from the catalog before
    the model ever runs (``products_by_ids``) — the model only reasons
    over already-ground-truth data and never reconstructs it.
    """

    differences: list[str]


def build_comparison_agent(
    model: Model | KnownModelName | str = "openai:gpt-4o-mini",
) -> Agent[None, ComparisonAnalysis]:
    return Agent(
        model,
        output_type=ComparisonAnalysis,
        system_prompt=COMPARISON_SYSTEM_PROMPT,
        model_settings=ModelSettings(timeout=LLM_CALL_TIMEOUT_SECONDS),
    )


def _build_prompt(products: list[Product]) -> str:
    lines = [f"Compare these {len(products)} products:"]
    for product in products:
        lines.append(
            f"- {product.id}: {product.name} ({product.brand}, {product.category}) "
            f"${product.price}, rating {product.rating}/5 - {product.description}"
        )
    return "\n".join(lines)


async def compare_products(
    agent: Agent[None, ComparisonAnalysis],
    catalog: CatalogData,
    request: ComparisonRequest,
) -> ComparisonResponse | AgentErrorEnvelope:
    """Compare the products in ``request.product_ids``.

    An unknown product ID, or fewer than 2 resolving IDs, is a contract
    violation (error envelope, spec Section 6) — there's nothing meaningful
    to compare with 0 or 1 real products.
    """

    products = products_by_ids(catalog, request.product_ids)

    if len(products) < len(set(request.product_ids)):
        found_ids = {product.id for product in products}
        missing = sorted(set(request.product_ids) - found_ids)
        return AgentErrorEnvelope(
            error=AgentError(
                code="unknown_product_id",
                message=f"Unknown product id(s): {', '.join(missing)}.",
                sub_agent="comparison_agent",
            )
        )

    if len(products) < 2:
        return AgentErrorEnvelope(
            error=AgentError(
                code="insufficient_product_ids",
                message="At least 2 valid product IDs are required to compare.",
                sub_agent="comparison_agent",
            )
        )

    prompt = _build_prompt(products)
    result, _ = await call_with_retry(lambda: agent.run(prompt), label="comparison_agent")
    return ComparisonResponse(products=products, differences=result.output.differences)
