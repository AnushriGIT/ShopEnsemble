"""Streamlit UI for the ShopEnsemble coordinator agent (Phase 4a).

Talks to ``app/api/`` over real HTTP (``httpx``) — never imports
``app.agents``/``app.api`` in-process. See
``specs/2_coordinator-agent/shopensemble-coordinator-agent-phase4a-ui-implementation-plan.md``.
"""
