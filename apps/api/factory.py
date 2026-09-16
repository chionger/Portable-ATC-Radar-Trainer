import json
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api.models import HealthResponse
from packages.infrastructure.configuration import AppSettings, load_settings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    effective = settings if settings is not None else load_settings()
    application = FastAPI(title="Portable ATC Radar Trainer API", version="0.1.0")
    application.state.settings = effective
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(effective.api.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    if effective.features.report_configuration:
        logging.getLogger(__name__).info(
            "Effective configuration: %s", json.dumps(effective.redacted_report(), sort_keys=True)
        )

    @application.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        return HealthResponse(
            status="ok", configuration_version=request.app.state.settings.schema_version
        )

    return application
