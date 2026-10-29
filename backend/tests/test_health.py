from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app


def test_health_returns_200_with_expected_body() -> None:
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "status": "ok",
        "service": "travelmate-ai",
        "version": __version__,
    }


def test_health_response_has_exactly_the_documented_fields() -> None:
    client = TestClient(create_app(Settings(app_env="test")))

    body = client.get("/health").json()

    assert set(body) == {"status", "service", "version"}
    assert isinstance(body["status"], str)
    assert isinstance(body["service"], str)
    assert isinstance(body["version"], str)


def test_health_needs_no_secrets_or_external_services() -> None:
    # Building the app with default settings and calling /health must not
    # depend on any API key or external network access.
    client = TestClient(create_app(Settings()))

    assert client.get("/health").status_code == 200
