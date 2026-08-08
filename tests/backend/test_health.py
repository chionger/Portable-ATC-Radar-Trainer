from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.models import HealthResponse

client = TestClient(app)


def test_health_response_model() -> None:
    assert HealthResponse(status="ok").model_dump() == {"status": "ok"}


def test_health_endpoint_returns_http_200() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

