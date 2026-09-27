"""Manual smoke-test entry point for the coordinator agent (Phases 1-2).

No API layer yet (that's Phase 3) — this CLI is the in-process verification
path the coordinator-agent spec's Section 1 describes. Loads the catalog
once, builds every agent once, and answers one query per invocation:

    python -m app.agents.cli "What do people say about SP0001?"
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.comparison_agent import build_comparison_agent
from app.agents.coordinator import CoordinatorResponse, SubAgents, build_coordinator_agent, handle_query
from app.agents.data import load_catalog_data
from app.agents.logging_setup import configure_logging
from app.agents.policy_faq_agent import build_policy_faq_agent
from app.agents.recommendation_agent import build_recommendation_agent
from app.agents.review_agent import build_review_agent

load_dotenv()  # No-op if .env is absent; makes a local OPENAI_API_KEY usable.

# Phase 4b finding: without this, every logger.info(...) call anywhere in
# app/agents/ (the routing-decision log, the llm_usage cost/token log) was
# silently dropped — Python's root logger defaults to WARNING. Same fix as
# app/api/main.py, applied here too since the CLI is an independent process
# entry point with its own setup (matches load_dotenv() above being called
# in both places rather than shared). Now also persisted to logs/cli.log,
# not just the console — see app/agents/logging_setup.py.
configure_logging("cli.log")


async def _run(query: str) -> CoordinatorResponse:
    catalog = load_catalog_data()
    coordinator_agent = build_coordinator_agent()
    sub_agents = SubAgents(
        review=build_review_agent(),
        recommendation=build_recommendation_agent(),
        comparison=build_comparison_agent(),
        policy_faq=build_policy_faq_agent(),
    )
    return await handle_query(coordinator_agent, sub_agents, catalog, query)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.agents.cli '<query>'")
        return 1

    query = " ".join(sys.argv[1:])
    try:
        response = asyncio.run(_run(query))
    except Exception as error:
        print(f"Query failed: {error}")
        return 1

    print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
