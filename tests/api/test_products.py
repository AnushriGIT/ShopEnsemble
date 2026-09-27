"""Contract tests for GET /products.

A plain data read — no LLM/coordinator call, no caching, no rate limiting
(same class as GET /health, unlike POST /query). Uses the default ``client``
fixture's ``fake_catalog`` (a single SP0001 product) directly from
``tests/api/conftest.py``.
"""

from fastapi.testclient import TestClient

from app.api.main import app


def test_products_returns_the_full_catalog(client: TestClient):
    response = client.get("/products")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "SP0001"
    assert body[0]["name"] == "Widget Pro"
    assert body[0]["description"] == "A fine speaker"


def test_products_is_never_rate_limited(monkeypatch):
    import app.api.rate_limit as rate_limit_module
    from app.api.rate_limit import FixedWindowRateLimiter

    # A limiter that rejects everything — /products must still succeed
    # since check_rate_limit is only wired onto POST /query, not GET
    # /products (mirrors test_rate_limit.py's equivalent /health check).
    monkeypatch.setattr(rate_limit_module, "_limiter", FixedWindowRateLimiter(requests_per_minute=0))

    with TestClient(app) as test_client:
        response = test_client.get("/products")

    assert response.status_code == 200
