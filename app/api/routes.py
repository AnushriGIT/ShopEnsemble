"""HTTP routes: GET /health, GET /products, POST /query, DELETE /session.

The /query route is a thin wrapper — all the actual logic (classification,
dispatch, sanitization, retry) already lives in
``app.agents.coordinator.handle_turn`` and its sub-agents; nothing is
reimplemented here. Phase 4b adds a cache check ahead of the coordinator and a
rate-limit dependency, both scoped to ``/query`` only — ``/health`` and
``/products`` stay unthrottled and uncached: ``/health`` so monitoring and the
UI's sidebar indicator can always reach it, ``/products`` because browsing the
catalog is a plain data read, not an LLM call — routing "what products exist"
through the coordinator would cost real tokens/latency for something that needs
neither classification nor generation.

Phase 5 adds optional per-conversation memory to /query (spec B7): when the
request carries a ``session_id`` the coordinator is given that session's
context, and the session's memory is updated afterwards. The response cache
interacts with this in one important way — see the comments in ``query``.
"""

import logging

from fastapi import APIRouter, Depends, Header, Response

from app.agents.conversation import ConversationContext
from app.agents.coordinator import CoordinatorResponse, TurnResult, handle_turn
from app.agents.sanitize import sanitize_query
from app.api.cache import TTLCache, get_query_cache
from app.api.dependencies import AppState, get_app_state
from app.api.rate_limit import check_rate_limit
from app.api.schemas import SESSION_ID_PATTERN, QueryRequest
from app.api.session_store import SessionStore, get_session_store
from app.models import Product

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/products", response_model=list[Product])
async def products(app_state: AppState = Depends(get_app_state)) -> list[Product]:
    return app_state.catalog.products


@router.post("/query", response_model=CoordinatorResponse)
async def query(
    request: QueryRequest,
    app_state: AppState = Depends(get_app_state),
    query_cache: TTLCache = Depends(get_query_cache),
    session_store: SessionStore = Depends(get_session_store),
    _rate_limit: None = Depends(check_rate_limit),
) -> CoordinatorResponse:
    """Answer one query, optionally as part of a remembered conversation.

    Flow (spec B7): load the session's context (if a ``session_id`` was sent);
    consult the response cache only when that is safe; otherwise run the
    coordinator; then record the turn in the session's memory.

    **Cache policy** — the cache is keyed by query text alone, which is only
    valid for answers that depend on the text alone. A turn that has conversation
    context ("review both of those") is answered using that context, so caching
    it under the bare text would serve one customer's answer to a different
    customer who typed the same words. Therefore the cache is read AND written
    only for requests with no session, or a session with no prior turns (whose
    answer is context-free). Later turns of a conversation bypass it entirely.
    """

    session_id = request.session_id
    context = session_store.get(session_id) if session_id else None

    # Keyed by the sanitized query text — the same normalized form the
    # coordinator itself sanitizes to internally, so a cache hit is checked
    # against exactly what the coordinator would actually see.
    sanitized_query = sanitize_query(request.query)
    # Stateless and session requests are cached in SEPARATE partitions. Only
    # session requests get the coordinator's ID guard, so a stateless answer
    # may contain IDs the model invented; if it shared an entry with a session's
    # first turn, that unguarded answer would be served to a brand-new session
    # and bypass the guard entirely (found in review, 2026-09-26).
    cache_key = f"{'session' if session_id else 'stateless'}:{sanitized_query}"
    use_cache = context is None or context.is_empty

    result: TurnResult | None = query_cache.get(cache_key) if use_cache else None
    if result is None:
        result = await handle_turn(
            app_state.coordinator_agent, app_state.sub_agents, app_state.catalog, request.query, context=context
        )
        if use_cache:
            query_cache.set(cache_key, result)

    if session_id:
        # Recorded even when the answer came from the cache: the cached
        # TurnResult carries the turn's facts, so a first turn served from the
        # cache still seeds this session's memory (IDs and filters included).
        updated = (context or ConversationContext()).with_turn(
            sanitized_query, result.facts, app_state.catalog, max_turns=session_store.max_turns
        )
        session_store.save(session_id, updated)
        # Only an 8-char prefix is ever logged: the full ID is a bearer secret.
        logger.info("session_memory session=%s turns=%d", session_id[:8], len(updated.turns))

    return result.response


@router.delete("/session", status_code=204)
async def delete_session(
    x_session_id: str = Header(alias="X-Session-ID", pattern=SESSION_ID_PATTERN),
    session_store: SessionStore = Depends(get_session_store),
) -> Response:
    """Forget the caller's conversation ("New chat").

    The session ID is taken from the ``X-Session-ID`` header, NOT the URL path.
    It is a bearer secret (there is no auth: knowing it is what grants access to
    that conversation's memory), and request URLs are written to uvicorn's access
    log, reverse-proxy logs and HTTP-client logs — the security gate found the
    first design (``DELETE /sessions/{id}``) printing full IDs on the server
    console. A header appears in none of those.

    Idempotent and non-revealing: always 204 for a well-formed ID, whether or
    not that session existed, so the endpoint can't be used to probe which
    session IDs are live. Not rate-limited — it's a cheap in-memory delete and
    holding the (unguessable) ID is the only way to target a session.
    """

    session_store.clear(x_session_id)
    return Response(status_code=204)
