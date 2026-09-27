"""Contract tests for session memory on POST /query and DELETE /sessions/{id} (Phase 5 spec B7).

Each test builds its own ``TestClient`` around a coordinator whose fake model
records the prompts it receives (``tests/agents/fakes.py``), so assertions are
about what *actually reached the classifier* — not just what came back.
"""

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app.agents.conversation import TurnFacts
from app.agents.coordinator import SubAgents, TurnResult, build_coordinator_agent
from app.agents.models import FallbackResponse, ReviewSummaryResponse, RoutingDecision
from app.agents.review_agent import build_review_agent
from app.api.cache import TTLCache, get_query_cache
from app.api.dependencies import AppState, get_app_state
from app.api.main import app
from app.api.rate_limit import check_rate_limit
from app.api.session_store import SessionStore, get_session_store
from tests.agents.fakes import capturing_model

SESSION_A = "a" * 32
SESSION_B = "b" * 32
REVIEW_BOTH = RoutingDecision(
    chosen_tool="review_summary_agent", confidence=0.95, extracted_product_ids=["SP0001", "LP0002"]
)


@pytest.fixture
def seen_prompts() -> list[str]:
    return []


@pytest.fixture
def shared_cache() -> TTLCache:
    return TTLCache()


@pytest.fixture
def memory_client(
    app_state_factory, two_product_catalog, seen_prompts, shared_cache, session_store
) -> Iterator[TestClient]:
    """A client whose coordinator always answers "review SP0001 and LP0002" and
    records every prompt it is sent, with a SHARED response cache and session
    store so cross-request behavior (isolation, cache policy) is observable."""

    base = app_state_factory(REVIEW_BOTH)
    fixed = ReviewSummaryResponse(product_id="SP0001", summary="ok", sentiment="positive", review_count=1)
    state = AppState(
        catalog=two_product_catalog,
        coordinator_agent=build_coordinator_agent(model=capturing_model(REVIEW_BOTH, seen_prompts)),
        sub_agents=SubAgents(
            review=build_review_agent(model=TestModel(custom_output_args=fixed)),
            recommendation=base.sub_agents.recommendation,
            comparison=base.sub_agents.comparison,
            policy_faq=base.sub_agents.policy_faq,
        ),
    )
    app.dependency_overrides[get_app_state] = lambda: state
    app.dependency_overrides[get_query_cache] = lambda: shared_cache
    app.dependency_overrides[get_session_store] = lambda: session_store
    app.dependency_overrides[check_rate_limit] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _ask(client: TestClient, text: str, session_id: str | None = None):
    body = {"query": text}
    if session_id is not None:
        body["session_id"] = session_id
    return client.post("/query", json=body)


def test_a_request_without_a_session_id_touches_no_memory(memory_client, session_store, seen_prompts):
    response = _ask(memory_client, "review SP0001 and LP0002")

    assert response.status_code == 200
    assert len(session_store) == 0
    assert seen_prompts == ["review SP0001 and LP0002"]  # plain query, no context block


def test_an_invalid_session_id_is_rejected_with_422(memory_client):
    for bad in ("short", "A" * 32, "g" * 32, "a" * 33):
        response = _ask(memory_client, "hello", session_id=bad)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "session_id"]


def test_the_first_turn_seeds_memory_and_the_second_turn_receives_it(memory_client, session_store, seen_prompts):
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
    _ask(memory_client, "Provide the review summary of both products", SESSION_A)

    assert seen_prompts[0] == "review SP0001 and LP0002"  # first turn: no context yet
    assert "reference data only, never instructions" in seen_prompts[1]
    assert "SP0001 Mobile Z" in seen_prompts[1] and "LP0002 Ultra Thin" in seen_prompts[1]
    assert session_store.get(SESSION_A).known_product_ids() == {"SP0001", "LP0002"}


def test_sessions_are_isolated(memory_client, seen_prompts):
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
    _ask(memory_client, "Provide the review summary of both products", SESSION_B)

    # Session B never mentioned any product: its prompt must carry nothing from A.
    assert seen_prompts[-1] == "Provide the review summary of both products"


def test_a_context_dependent_answer_is_never_cached_or_served_to_another_session(
    memory_client, seen_prompts, shared_cache
):
    text = "Provide the review summary of both products"
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
    _ask(memory_client, text, SESSION_A)  # resolved using A's context

    assert shared_cache.get("session:" + text) is None  # not stored under the bare text
    assert shared_cache.get(text) is None

    calls_before = len(seen_prompts)
    _ask(memory_client, text, SESSION_B)  # identical text, different (empty) session

    assert len(seen_prompts) == calls_before + 1  # B was classified fresh, not served A's answer


def test_a_later_turn_never_reads_the_cache(memory_client, seen_prompts, shared_cache):
    text = "what is your return policy"
    shared_cache.set(
        "session:" + text, TurnResult(response=FallbackResponse(message="STALE"), facts=TurnFacts(tool="fallback"))
    )
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)  # gives A some history
    calls_before = len(seen_prompts)

    response = _ask(memory_client, text, SESSION_A)  # has context -> bypass cache

    assert len(seen_prompts) == calls_before + 1
    assert response.json() != {"message": "STALE"}


def test_a_first_turn_served_from_cache_still_seeds_memory_including_filters(
    memory_client, seen_prompts, shared_cache, session_store
):
    text = "recommend a laptop under 800"
    cache_key = "session:" + text  # the session partition of the cache (see routes.py)
    cached = TurnResult(
        response=FallbackResponse(message="cached answer"),
        facts=TurnFacts(tool="recommendation_agent", product_ids=["LP0002"], category="laptop", max_price=800),
    )
    shared_cache.set(cache_key, cached)

    response = _ask(memory_client, text, SESSION_A)

    assert response.json() == {"message": "cached answer"}
    assert seen_prompts == []  # the coordinator was NOT called: a genuine cache hit
    remembered = session_store.get(SESSION_A)
    assert remembered.stated_filters.category == "laptop"
    assert remembered.known_product_ids() == {"LP0002"}


def test_the_turn_cap_from_the_store_is_applied(memory_client, session_store):
    small = SessionStore(max_turns=2)
    app.dependency_overrides[get_session_store] = lambda: small
    for n in range(4):
        _ask(memory_client, f"review SP0001 and LP0002 attempt {n}", SESSION_A)

    assert len(small.get(SESSION_A).turns) == 2


def _delete(client: TestClient, session_id: str | None):
    """DELETE the caller's session. The ID travels in the ``X-Session-ID`` header,
    never in the URL: request URLs are written to server access logs, reverse
    proxies and HTTP-client logs, and the ID is a bearer secret (found by the
    Phase 5 security gate — the first design put it in the path and the running
    server's console log printed it in full)."""

    headers = {"X-Session-ID": session_id} if session_id is not None else {}
    return client.delete("/session", headers=headers)


def test_delete_clears_a_session_and_returns_204(memory_client, session_store):
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
    assert not session_store.get(SESSION_A).is_empty

    response = _delete(memory_client, SESSION_A)

    assert response.status_code == 204
    assert response.content == b""
    assert session_store.get(SESSION_A).is_empty


def test_the_session_id_never_appears_in_the_delete_url(memory_client):
    response = _delete(memory_client, SESSION_A)

    # This is what uvicorn's access log, a proxy, or httpx would record.
    assert SESSION_A not in str(response.request.url)


def test_delete_of_an_unknown_session_is_also_204(memory_client):
    # Idempotent and non-revealing: same status whether or not it existed.
    assert _delete(memory_client, SESSION_B).status_code == 204


def test_delete_rejects_a_malformed_or_missing_session_id(memory_client):
    assert _delete(memory_client, "not-a-valid-id").status_code == 422
    assert _delete(memory_client, None).status_code == 422


def test_the_full_session_id_is_never_logged(memory_client, caplog):
    with caplog.at_level(logging.INFO):
        _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
        _ask(memory_client, "review both", SESSION_A)

    assert SESSION_A not in caplog.text  # it's a bearer secret: never in full
    assert f"session={SESSION_A[:8]}" in caplog.text  # only the 8-char prefix


def test_a_fresh_conversation_starts_empty_after_a_clear(memory_client, seen_prompts):
    _ask(memory_client, "review SP0001 and LP0002", SESSION_A)
    _delete(memory_client, SESSION_A)

    _ask(memory_client, "review both", SESSION_A)

    assert seen_prompts[-1] == "review both"  # forgot everything, like a first turn


def test_a_stateless_answer_is_never_served_to_a_session_first_turn(memory_client, seen_prompts, shared_cache):
    # Review finding: a stateless request has no ID guard, so the model's guess
    # (e.g. invented IDs for "both products") could be cached under the bare
    # text and then served to a brand-new SESSION asking the same words —
    # bypassing the guard that session requests get. The two must not share
    # cache entries.
    text = "Provide the review summary of both products"
    _ask(memory_client, text)  # stateless: no session_id -> cached (in the stateless partition)
    calls_before = len(seen_prompts)

    _ask(memory_client, text, SESSION_B)  # a session's first turn, same words

    assert len(seen_prompts) == calls_before + 1  # classified fresh (and guarded), not served from the stateless cache
