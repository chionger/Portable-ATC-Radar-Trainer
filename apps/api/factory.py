import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from apps.api.models import HealthResponse
from packages.application.health import HealthRegistry
from packages.domain.health import HealthReason, HealthStatus, MetricName, MetricObservation
from packages.infrastructure.configuration import AppSettings, load_settings
from packages.infrastructure.structured_logging import LogEvent, StructuredLog


def create_app(
    settings: AppSettings | None = None,
    *,
    health_registry: HealthRegistry | None = None,
    structured_log: StructuredLog | None = None,
) -> FastAPI:
    effective = settings if settings is not None else load_settings()
    registry = (
        health_registry
        if health_registry is not None
        else HealthRegistry(effective.health.timeout_seconds)
    )
    registry.register("api")
    registry.register("logging", required=False)
    correlation = uuid4()
    for component in ("api", "logging"):
        registry.report(
            component, HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
        )
    logger = (
        structured_log
        if structured_log is not None
        else StructuredLog(
            level=effective.logging.level,
            path=Path(effective.logging.file_path) if effective.logging.file_path else None,
            max_bytes=effective.logging.max_bytes,
            backup_count=effective.logging.backup_count,
        )
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            logger.close()

    application = FastAPI(
        title="Portable ATC Radar Trainer API", version="0.1.0", lifespan=lifespan
    )
    application.state.settings = effective
    application.state.health_registry = registry
    application.state.structured_log = logger
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(effective.api.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    if effective.features.report_configuration:
        logging.getLogger(__name__).info(
            "Effective configuration: %s", json.dumps(effective.redacted_report(), sort_keys=True)
        )

    @application.middleware("http")
    async def correlated_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            correlation_id = UUID(request.headers.get("X-Correlation-ID", ""))
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = correlation_id
        started = perf_counter()
        registry.report(
            "api", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation_id
        )
        event = LogEvent.REQUEST_COMPLETED
        try:
            response = await call_next(request)
        except Exception:
            event = LogEvent.REQUEST_FAILED
            response = JSONResponse(
                {"code": "INTERNAL_ERROR", "correlation_id": str(correlation_id)}, status_code=500
            )
        metric = MetricObservation(
            name=MetricName.REQUEST_DURATION_MS, value=(perf_counter() - started) * 1000
        )
        registry.observe_metric(metric)
        try:
            logger.emit(
                event,
                correlation_id=correlation_id,
                status_code=response.status_code,
                metric=metric,
            )
            registry.report(
                "logging",
                HealthStatus.HEALTHY,
                HealthReason.OPERATIONAL,
                correlation_id=correlation_id,
            )
        except OSError:
            registry.report(
                "logging", HealthStatus.DEGRADED, HealthReason.FAILED, correlation_id=correlation_id
            )
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        status, components = registry.snapshot()
        return HealthResponse(
            status="ok",
            configuration_version=effective.schema_version,
            readiness=status,
            components=components,
        )

    return application
