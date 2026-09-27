"""Fixtures for the coordinator-agent evaluation harness.

Everything under ``tests/agents/eval/`` is marked ``eval`` (see
``pyproject.toml``) and calls the real OpenAI API — the one place in the
test suite that intentionally does so, mirroring
``tests/conftest.py``'s ``postgres_available`` skip-if-unreachable idiom for
a missing dependency, but for a missing API key instead of an unreachable
database (spec Section 12, Phase 3a implementation plan).

The durable per-run results file (Rule 4) lives in the root
``tests/conftest.py``'s ``pytest_terminal_summary`` hook, not here — it
covers every pytest run project-wide (fast suite, integration, eval, or a
mix), not just this directory. It used to be a separate eval-only hook
writing to ``reports/eval-results/``; consolidated to avoid two near-
duplicate mechanisms writing to two different locations (Rule 12).
"""

import os

import pytest

from app.agents.comparison_agent import build_comparison_agent
from app.agents.coordinator import SubAgents, build_coordinator_agent
from app.agents.data import CatalogData, load_catalog_data
from app.agents.policy_faq_agent import build_policy_faq_agent
from app.agents.recommendation_agent import build_recommendation_agent
from app.agents.review_agent import build_review_agent
from tests.agents.eval.groundedness import build_groundedness_judge


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run every eval test on ONE shared, session-scoped asyncio event loop.

    Why: the eval agents below are session-scoped, so they share a single
    OpenAI HTTP client (one httpx connection pool) for the whole run. By
    default pytest-asyncio gives each test its own function-scoped event
    loop and closes it afterward, so a pooled keep-alive TLS connection
    opened during an earlier test is reused by a later test after its loop
    is already closed — failing with ``RuntimeError: Event loop is closed``.
    That failure is deceptive: each test passes when run alone, which looks
    like flaky LLM behavior rather than a harness bug (found 2026-09-26:
    4 of 7 eval tests failed together, 7 of 7 pass with this fix).

    Scoped to this directory only (this hook receives every collected item,
    so it filters by path) — the fast and integration suites keep the
    default per-test loops, untouched. Don't "clean this up" without
    re-running ``-m eval`` as one combined process.

    Inputs: ``items`` — every collected test item in the session.
    Output: none; mutates matching items in place by adding the
    ``asyncio(loop_scope="session")`` marker.
    """

    eval_dir = os.path.dirname(__file__)
    for item in items:
        if str(item.path).startswith(eval_dir):
            # append=False puts this marker FIRST so it takes precedence over
            # the default-scope asyncio marker pytest-asyncio's auto mode adds.
            item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


def _require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set; skipping real-API eval tests.")


@pytest.fixture(scope="session")
def eval_catalog() -> CatalogData:
    _require_api_key()
    return load_catalog_data()


@pytest.fixture(scope="session")
def eval_coordinator_agent(eval_catalog: CatalogData):
    _require_api_key()
    return build_coordinator_agent()


@pytest.fixture(scope="session")
def eval_sub_agents(eval_catalog: CatalogData) -> SubAgents:
    _require_api_key()
    return SubAgents(
        review=build_review_agent(),
        recommendation=build_recommendation_agent(),
        comparison=build_comparison_agent(),
        policy_faq=build_policy_faq_agent(),
    )


@pytest.fixture(scope="session")
def eval_groundedness_judge(eval_catalog: CatalogData):
    _require_api_key()
    return build_groundedness_judge()
