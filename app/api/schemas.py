"""API-boundary-only request models.

``QueryRequest`` is deliberately separate from every ``*Request`` model in
``app/agents/models.py`` (spec's own requirement: "separate request and
response models where lifecycle or authorization differs") — those are
internal, per-sub-agent request shapes constructed *after* routing;
``QueryRequest`` is the one thing an external HTTP caller actually sends.
Response shapes need no equivalent new model: ``CoordinatorResponse``
(the same 7-member union ``handle_query`` already returns) is reused as-is
for ``POST /query``.
"""

from pydantic import Field

from app.agents.sanitize import MAX_QUERY_LENGTH
from app.models import ShopEnsembleModel

# A session ID is a client-generated ``uuid4().hex``: 32 lowercase hex chars
# (128 bits of randomness). It acts as a bearer secret — there is no auth in
# this project, so knowing the ID is what grants access to that conversation's
# memory — hence a strict pattern here (also reused to validate the
# ``DELETE /sessions/{session_id}`` path parameter) and never logging it in full.
SESSION_ID_PATTERN = r"^[a-f0-9]{32}$"


class QueryRequest(ShopEnsembleModel):
    """Body of ``POST /query``.

    ``max_length`` mirrors ``app.agents.sanitize.MAX_QUERY_LENGTH`` —
    defense-in-depth at the HTTP boundary itself, not a replacement for
    ``handle_query``'s own ``sanitize_query()`` call one layer down (same
    two-layer pattern already used for ``RecommendationRequest.query``/
    ``PolicyRequest.question`` after the code-review pass).
    """

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    session_id: str | None = Field(default=None, pattern=SESSION_ID_PATTERN)
    """Optional (Phase 5): identifies one chat conversation so the coordinator
    can remember what was already said in it. Omitted by the CLI and the
    form-based UI pages, which stay exactly as stateless as before."""
