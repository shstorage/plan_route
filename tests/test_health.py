import pytest
from fastapi.testclient import TestClient

from plan_route.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173"])
def test_local_origins_allowed(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin

    preflight = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    ["https://example.com", "http://localhost:5174", "http://localhost:5173.example.com"],
)
def test_other_origins_not_allowed(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_health_is_read_only(client):
    assert client.post("/api/health").status_code == 405


def test_unknown_endpoint(client):
    assert client.get("/api/unknown").status_code == 404
