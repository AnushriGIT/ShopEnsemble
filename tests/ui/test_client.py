"""Unit tests for ShopEnsembleAPIClient's error handling.

Uses ``httpx.MockTransport`` (the standard way to test an ``httpx.Client``
without a real socket) rather than ``FakeClient`` — these tests exercise
``client.py`` itself, not code that calls it."""

import httpx
import pytest

from app.ui.client import ShopEnsembleAPIClient, ShopEnsembleAPIError


def _client(handler) -> ShopEnsembleAPIClient:
    return ShopEnsembleAPIClient(base_url="http://testserver", transport=httpx.MockTransport(handler))


def test_query_returns_the_parsed_response_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "ok"})

    result = _client(handler).query("hello")

    assert result == {"message": "ok"}


def test_query_raises_a_safe_message_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(ShopEnsembleAPIError, match="Can't reach the ShopEnsemble API"):
        _client(handler).query("hello")


def test_query_raises_a_safe_message_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with pytest.raises(ShopEnsembleAPIError, match="took too long"):
        _client(handler).query("hello")


def test_query_extracts_the_field_error_on_422_validation_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"msg": "String should have at least 1 character"}]})

    with pytest.raises(ShopEnsembleAPIError, match="at least 1 character"):
        _client(handler).query("")


def test_query_extracts_the_safe_message_on_a_500_without_leaking_raw_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "internal_error", "message": "An unexpected error occurred."}})

    with pytest.raises(ShopEnsembleAPIError, match="An unexpected error occurred."):
        _client(handler).query("anything")


def test_health_returns_the_parsed_body_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    assert _client(handler).health() == {"status": "ok"}


def test_health_raises_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(ShopEnsembleAPIError, match="Can't reach the ShopEnsemble API"):
        _client(handler).health()


# --- Phase 5 spec B8: session_id on query(), best-effort delete_session() ------


def test_query_sends_the_session_id_when_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": "ok"})

    _client(handler).query("hello", session_id="a" * 32)

    import json

    assert json.loads(seen["body"]) == {"query": "hello", "session_id": "a" * 32}


def test_query_omits_the_session_id_field_when_none():
    # The form-based pages never pass one, and their request body must stay
    # exactly what it was before Phase 5.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": "ok"})

    _client(handler).query("hello")

    import json

    assert json.loads(seen["body"]) == {"query": "hello"}


def test_delete_session_sends_the_id_in_a_header_never_in_the_url():
    # The ID is a bearer secret and URLs get logged (uvicorn access log,
    # proxies, httpx's own INFO log) — so it must travel in a header.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["header"] = request.headers.get("X-Session-ID")
        return httpx.Response(204)

    _client(handler).delete_session("b" * 32)

    assert seen["method"] == "DELETE"
    assert seen["url"] == "http://testserver/session"
    assert "b" * 32 not in seen["url"]
    assert seen["header"] == "b" * 32


@pytest.mark.parametrize(
    "failure",
    [
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused", request=request)),
        lambda request: (_ for _ in ()).throw(httpx.TimeoutException("slow", request=request)),
        lambda request: httpx.Response(500, json={"error": {"message": "boom"}}),
    ],
    ids=["connection-refused", "timeout", "server-error"],
)
def test_delete_session_never_raises_because_it_is_best_effort(failure):
    # TTL expiry on the server is the backstop, so a failed cleanup must never
    # surface to (or break) the page that triggered it.
    _client(failure).delete_session("c" * 32)  # must simply return
