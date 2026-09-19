"""Versioned session REST boundary. Storage is opened only for session requests."""

from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.api.scenarios import catalogue
from packages.application.sessions import DurableSessionService
from packages.domain.session import Session, SessionLifecycleState, SessionVersions
from packages.infrastructure.configuration import AppSettings
from packages.infrastructure.persistence.sqlite import SQLiteEventStore
from packages.infrastructure.scenarios import LocalScenarioCatalogue


class CreateSessionBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "scenario_id": "training",
                    "scenario_version": "1.0",
                    "seed": 42,
                }
            ]
        },
    )
    schema_version: Literal["1.0"] = "1.0"
    scenario_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")]
    scenario_version: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    ]
    seed: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = None


class LifecycleBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={"examples": [{"schema_version": "1.0", "expected_version": 3}]},
    )
    schema_version: Literal["1.0"] = "1.0"
    expected_version: Annotated[int, Field(ge=1, le=2**63 - 1)]


class SessionResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    session: Session


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, str] = Field(default_factory=dict)
    correlation_id: UUID


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "code": code,
            "message": message,
            "details": {},
            "correlation_id": str(request.state.correlation_id),
        },
        status_code=status,
    )


class SessionBodyLimit:
    """Bound actual bytes, including chunked requests, before JSON parsing."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith("/api/v1/sessions")
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                await error_response(
                    Request(scope),
                    413,
                    "REQUEST_TOO_LARGE",
                    "Lifecycle request exceeds configured limit",
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def buffered_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)


def service(store: SQLiteEventStore, settings: AppSettings) -> DurableSessionService:
    return DurableSessionService(
        store,
        SessionVersions(settings.schema_version, settings.configuration_hash(), "1.0", "1.0"),
        default_seed=settings.sessions.default_seed,
        scenario_catalogue=LocalScenarioCatalogue(Path(settings.scenarios.directory))
        if settings.scenarios.directory
        else None,
    )


def open_store(settings: AppSettings) -> SQLiteEventStore:
    # No directory creation and no model-root access. A connection belongs to one
    # synchronous request thread and is always closed before that request returns.
    return SQLiteEventStore(
        settings.database_path(),
        migration_mode=settings.persistence.migration_mode,
        busy_timeout_ms=settings.persistence.busy_timeout_ms,
    )


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
    responses={status: {"model": ErrorResponse} for status in (404, 409, 413, 422, 503)},
)


@router.post("", response_model=SessionResponse, status_code=201)
def create_session_route(
    body: CreateSessionBody,
    request: Request,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> SessionResponse:
    settings = request.app.state.settings
    with open_store(settings) as store:
        session = service(store, settings).create(
            scenario_id=body.scenario_id,
            scenario_version=body.scenario_version,
            seed=body.seed,
            resolve_scenario=(
                lambda: catalogue(request).get(body.scenario_id, body.scenario_version)
            )
            if settings.scenarios.directory
            else None,
            idempotency_key=idempotency_key,
            correlation_id=request.state.correlation_id,
        )
    return SessionResponse(session=session)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session_route(session_id: UUID, request: Request) -> SessionResponse:
    settings = request.app.state.settings
    with open_store(settings) as store:
        return SessionResponse(session=service(store, settings).get(str(session_id)))


def lifecycle_route(
    target: SessionLifecycleState, required_state: SessionLifecycleState | None
) -> Any:
    def command(
        session_id: UUID,
        body: LifecycleBody,
        request: Request,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> SessionResponse:
        settings = request.app.state.settings
        with open_store(settings) as store:
            session = service(store, settings).transition(
                str(session_id),
                target,
                expected_version=body.expected_version,
                idempotency_key=idempotency_key,
                correlation_id=request.state.correlation_id,
                required_state=required_state,
            )
        return SessionResponse(session=session)

    return command


for action, target, required_state in (
    ("start", SessionLifecycleState.RUNNING, SessionLifecycleState.READY),
    ("pause", SessionLifecycleState.PAUSED, SessionLifecycleState.RUNNING),
    ("resume", SessionLifecycleState.RUNNING, SessionLifecycleState.PAUSED),
    ("stop", SessionLifecycleState.STOPPED, None),
):
    router.add_api_route(
        "/{session_id}/" + action,
        lifecycle_route(target, required_state),
        methods=["POST"],
        response_model=SessionResponse,
        name=action + "_session",
    )
