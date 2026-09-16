import json
import logging

import pytest
from fastapi.testclient import TestClient

from apps.api.factory import create_app
from apps.api.main import app
from apps.api.models import HealthResponse
from packages.infrastructure.configuration import ConfigurationError, load_settings


def test_health_response_model() -> None:
    assert HealthResponse(status="ok", configuration_version="1.0").model_dump() == {
        "status": "ok",
        "configuration_version": "1.0",
    }


def test_health_endpoint_returns_http_200() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "configuration_version": "1.0"}


def test_override_profile_is_injected_and_health_does_not_expose_it() -> None:
    settings = load_settings(environ={"ATC_API_PORT": "8123", "ATC_LOGGING_LEVEL": "DEBUG"})
    custom = create_app(settings)
    assert custom.state.settings is settings
    with TestClient(custom) as client:
        assert client.get("/health").json() == {"status": "ok", "configuration_version": "1.0"}


def test_invalid_configuration_prevents_app_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATC_API_PORT", "0")
    with pytest.raises(ConfigurationError, match="api.port"):
        create_app()


def test_cors_uses_configuration() -> None:
    settings = load_settings(environ={"ATC_API_CORS_ORIGINS": '["http://localhost:6000"]'})
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:6000"})
        denied = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:6000"
    assert "access-control-allow-origin" not in denied.headers


def test_startup_report_redacts_local_paths(caplog: pytest.LogCaptureFixture) -> None:
    settings = load_settings(
        environ={
            "ATC_PATHS_DATA_ROOT": "C:/private-location/data",
            "ATC_FEATURES_REPORT_CONFIGURATION": "true",
        }
    )
    with caplog.at_level(logging.INFO):
        create_app(settings)
    assert "private-location" not in caplog.text
    assert settings.configuration_hash() in caplog.text
    assert json.dumps("[REDACTED]") in caplog.text
