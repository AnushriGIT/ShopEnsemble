"""FastAPI application: builds the coordinator's singleton resources once at
startup (spec Section 7), wires up the routes, and closes the info-
disclosure risk already flagged in the spec's Section 10/Appendix A —
``app.agents.cli.py::main()``'s pattern of printing a caught exception's raw
message would leak internal detail to an external caller if reused verbatim
here; the global exception handler below is the actual fix, not a deferral.

Run for real:

    uvicorn app.api.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agents.comparison_agent import build_comparison_agent
from app.agents.coordinator import SubAgents, build_coordinator_agent
from app.agents.data import load_catalog_data
from app.agents.logging_setup import configure_logging
from app.agents.models import AgentError, AgentErrorEnvelope
from app.agents.policy_faq_agent import build_policy_faq_agent
from app.agents.recommendation_agent import build_recommendation_agent
from app.agents.review_agent import build_review_agent
from app.api.dependencies import AppState
from app.api.rate_limit import RateLimitExceeded
from app.api.routes import router

load_dotenv()  # No-op if .env is absent; makes a local OPENAI_API_KEY usable.

# Phase 4b finding: NO logging configuration existed anywhere in this
# project before this — every logger.info(...) call (the routing-decision
# log in coordinator.py, and this plan's own new llm_usage log in retry.py)
# was silently dropped, since Python's root logger defaults to WARNING and
# nothing here or in uvicorn itself raises app.* loggers to INFO. Without
# this, "Token cost per turn: Tracked" (spec Section 11) wasn't actually
# true in any observable sense — found only by checking real server output
# (Rule 9), not assumed from the code existing. Now also persisted to
# logs/api.log, not just the console — see app/agents/logging_setup.py.
configure_logging("api.log")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the catalog and every agent exactly once, for the process's
    lifetime — not per request. Same construction sequence as
    ``app.agents.cli.py::_run()``, just held on ``app.state`` instead of a
    local variable that returns after one query."""

    catalog = load_catalog_data()
    coordinator_agent = build_coordinator_agent()
    sub_agents = SubAgents(
        review=build_review_agent(),
        recommendation=build_recommendation_agent(),
        comparison=build_comparison_agent(),
        policy_faq=build_policy_faq_agent(),
    )
    app.state.shopensemble = AppState(catalog=catalog, coordinator_agent=coordinator_agent, sub_agents=sub_agents)
    yield


app = FastAPI(title="ShopEnsemble Coordinator Agent API", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Phase 4b: a 429 in the same AgentErrorEnvelope shape as every other
    error response — registered ahead of the generic Exception handler
    below (FastAPI dispatches to the most specific matching handler), so
    this never gets logged/reported as an "unexpected" server error."""

    envelope = AgentErrorEnvelope(
        error=AgentError(code="rate_limited", message=str(exc), sub_agent=None)
    )
    return JSONResponse(status_code=429, content=envelope.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the real error server-side; return a generic envelope externally.

    This is the fix for the risk the spec's Appendix A already flagged:
    never let a caught exception's raw message reach an external caller.
    """

    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    envelope = AgentErrorEnvelope(
        error=AgentError(code="internal_error", message="An unexpected error occurred.", sub_agent=None)
    )
    return JSONResponse(status_code=500, content=envelope.model_dump())
