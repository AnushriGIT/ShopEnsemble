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
