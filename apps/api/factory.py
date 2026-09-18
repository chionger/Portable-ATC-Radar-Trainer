import json
import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from apps.api.models import HealthResponse
from apps.api.sessions import SessionBodyLimit, error_response, router
from packages.application.health import HealthRegistry
from packages.application.sessions import SessionNotFound
from packages.domain.health import HealthReason, HealthStatus, MetricName, MetricObservation
from packages.domain.session import SessionTransitionError
from packages.infrastructure.configuration import AppSettings, load_settings
from packages.infrastructure.persistence.sqlite import PersistenceError, WriteConflict
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
    application.include_router(router)
    application.add_middleware(SessionBodyLimit, limit=effective.sessions.max_request_bytes)
    application.state.settings = effective
    application.state.health_registry = registry
    application.state.structured_log = logger
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(effective.api.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    if effective.features.report_configuration:
        logging.getLogger(__name__).info(
            "Effective configuration: %s", json.dumps(effective.redacted_report(), sort_keys=True)
        )

    @application.exception_handler(SessionNotFound)
    async def not_found(request: Request, error: SessionNotFound) -> JSONResponse:
        return error_response(request, 404, "SESSION_NOT_FOUND", "Session not found")

    @application.exception_handler(WriteConflict)
    async def conflict(request: Request, error: WriteConflict) -> JSONResponse:
        return error_response(request, 409, "WRITE_CONFLICT", "Version or idempotency conflict")

    @application.exception_handler(SessionTransitionError)
    async def invalid_transition(request: Request, error: SessionTransitionError) -> JSONResponse:
        return error_response(request, 409, error.code.value, "Lifecycle transition rejected")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "INVALID_REQUEST", "Request validation failed")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(request, error.status_code, "HTTP_ERROR", "Request rejected")

    async def storage_error(request: Request, error: Exception) -> JSONResponse:
        return error_response(
            request, 503, "PERSISTENCE_UNAVAILABLE", "Session storage unavailable"
        )

    application.add_exception_handler(PersistenceError, storage_error)
    application.add_exception_handler(sqlite3.Error, storage_error)
    application.add_exception_handler(OSError, storage_error)

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
                {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": {},
                    "correlation_id": str(correlation_id),
                },
                status_code=500,
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
