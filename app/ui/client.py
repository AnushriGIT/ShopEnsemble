"""Thin HTTP client for app/api/ — the UI's only path to the coordinator.

Deliberately talks to the real API over HTTP rather than importing
``app.agents``/``app.api`` in-process (Phase 4a implementation plan's
architecture decision) — that indirection is the entire point of having
built the FastAPI layer in Phase 3b.
"""

import os

import httpx
import streamlit as st

API_BASE_URL_ENV = "SMARTSHOP_API_BASE_URL"
DEFAULT_API_BASE_URL = "http://localhost:8000"


class SmartshopAPIError(Exception):
    """Raised for any failure talking to the API — connection refused, a
    timeout, or a non-2xx response. The message is always safe to show
    directly in the UI (never a raw exception/stack trace)."""


class SmartshopAPIClient:
    """Wraps a single ``httpx.Client`` for the lifetime of the Streamlit session."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # `transport` is a testability hook (standard httpx.Client pattern) —
        # tests inject an httpx.MockTransport instead of a real socket;
        # production code never passes it, so `None` -> httpx's real default.
        self._base_url = base_url or os.getenv(API_BASE_URL_ENV, DEFAULT_API_BASE_URL)
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout, transport=transport)

    def health(self) -> dict:
        try:
            response = self._client.get("/health")
        except httpx.ConnectError as error:
            raise SmartshopAPIError(f"Can't reach the Smartshop API at {self._base_url}.") from error
        except httpx.TimeoutException as error:
            raise SmartshopAPIError("The Smartshop API took too long to respond.") from error

        if response.status_code != 200:
            raise SmartshopAPIError(f"Health check failed (HTTP {response.status_code}).")
        return response.json()

    def list_products(self) -> list[dict]:
        """GET /products and return the full catalog as parsed JSON.

        No caching/rate-limiting on the server side (it's a plain data
        read, not an LLM call) — the caller (the Browse Catalog page) is
        expected to cache this itself via ``st.cache_data``, since the
        catalog doesn't change within a session.
        """

        try:
            response = self._client.get("/products")
        except httpx.ConnectError as error:
            raise SmartshopAPIError(f"Can't reach the Smartshop API at {self._base_url}.") from error
        except httpx.TimeoutException as error:
            raise SmartshopAPIError("The Smartshop API took too long to respond.") from error

        if response.status_code >= 400:
            raise SmartshopAPIError(f"Request failed (HTTP {response.status_code}).")
        return response.json()

    def query(self, text: str) -> dict:
        """POST /query and return the parsed JSON response body.

        Raises ``SmartshopAPIError`` with a safe, displayable message for
        every failure mode — connection refused, a timeout, a validation
        error (422, e.g. an empty or over-length query), or an unexpected
        server error (500, the global exception handler's generic envelope).
        """

        try:
            response = self._client.post("/query", json={"query": text})
        except httpx.ConnectError as error:
            raise SmartshopAPIError(f"Can't reach the Smartshop API at {self._base_url}.") from error
        except httpx.TimeoutException as error:
            raise SmartshopAPIError("The Smartshop API took too long to respond.") from error

        if response.status_code == 422:
            detail = response.json().get("detail", [])
            message = detail[0]["msg"] if detail else "Invalid query."
            raise SmartshopAPIError(message)

        if response.status_code >= 400:
            # Matches AgentErrorEnvelope's shape for the global exception
            # handler's 500s; falls back to the raw status for anything else.
            try:
                message = response.json()["error"]["message"]
            except (KeyError, ValueError):
                message = f"Request failed (HTTP {response.status_code})."
            raise SmartshopAPIError(message)

        return response.json()


@st.cache_resource
def get_client() -> SmartshopAPIClient:
    """One ``SmartshopAPIClient`` (one ``httpx.Client``, one connection pool)
    per Streamlit process, not one per page render — the same "instantiate
    once, not per call" idiom every other singleton resource in this project
    follows (spec Section 7)."""

    return SmartshopAPIClient()
