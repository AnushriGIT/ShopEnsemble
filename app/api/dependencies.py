"""Request-scoped access to the app's singleton resources.

``AppState`` is built once, at process startup, by ``main.py``'s
``lifespan`` — mirroring ``app.agents.cli.py::_run()``'s "load the catalog
once, build every agent once" sequence, but for the API's process lifetime
rather than one CLI invocation (spec Section 7's singleton-resources
requirement).

Routes depend on ``get_app_state`` rather than reading ``request.app.state``
directly so tests can swap it out via FastAPI's own
``app.dependency_overrides`` — the FastAPI-idiomatic equivalent of this
project's existing ``monkeypatch``/fake-agent test convention
(``tests/agents/test_coordinator.py::_fake_sub_agents``), without any real
OpenAI calls in the contract-test suite.
"""

from dataclasses import dataclass

from fastapi import Request
from pydantic_ai import Agent

from app.agents.coordinator import SubAgents
from app.agents.data import CatalogData
from app.agents.models import RoutingDecision


@dataclass(frozen=True)
class AppState:
    catalog: CatalogData
    coordinator_agent: Agent[None, RoutingDecision]
    sub_agents: SubAgents


def get_app_state(request: Request) -> AppState:
    return request.app.state.shopensemble
