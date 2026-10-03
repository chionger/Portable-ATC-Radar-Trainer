"""Session projection and durable unit-of-work contracts (FP-006)."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from packages.application.traffic_projection import project_traffic
from packages.domain.events import (
    ComponentHealthChangedPayload,
    DomainEvent,
    SessionCreatedPayload,
    SessionTransitionPayload,
)
from packages.domain.session import (
    CreateSessionRequest,
    Session,
    SessionLifecycleState,
    TransitionRequest,
    create_session,
    transition_session,
)
from packages.domain.traffic import (
    AircraftRouteAssignedPayload,
    AircraftSpawnedPayload,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
)

PROJECTION_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class SessionProjection:
    session: Session
    source_sequence: int
    projection_version: str = PROJECTION_VERSION


def project_session(events: tuple[DomainEvent, ...]) -> SessionProjection:
    """Reconstruct state using the same lifecycle policy as live commands."""
    if not events:
        raise ValueError("session history is empty")
    session: Session | None = None
    for sequence, supplied in enumerate(events, 1):
        event = DomainEvent.model_validate_json(supplied.model_dump_json())
        if event.sequence != sequence or event.session_id != events[0].session_id:
            raise ValueError("session history must be contiguous")
        payload = event.payload
        if isinstance(payload, SessionCreatedPayload) and session is None:
            session = create_session(
                CreateSessionRequest(
                    event.session_id,
                    payload.scenario_id,
                    payload.scenario_version,
                    payload.seed,
                    payload.versions,
                    event.wall_time_utc,
                    payload.scenario_hash,
                )
            )
        elif isinstance(payload, SessionTransitionPayload) and session is not None:
            if (
                payload.previous_version != session.version
                or payload.previous_state != session.lifecycle_state
            ):
                raise ValueError("transition does not follow committed aggregate")
            session = transition_session(
                session,
                TransitionRequest(
                    payload.state,
                    event.wall_time_utc,
                    event.sim_time,
                    payload.failure,
                ),
            ).session
        elif isinstance(payload, ComponentHealthChangedPayload) and session is not None:
            if (
                event.sim_time != session.simulation_time
                or event.wall_time_utc < session.updated_at
            ):
                raise ValueError("health event must retain committed session time")
        elif (
            isinstance(
                payload,
                AircraftSpawnedPayload
                | AircraftRouteAssignedPayload
                | AircraftStateChangedPayload
                | RunwayOccupancyChangedPayload,
            )
            and session is not None
        ):
            required = (
                SessionLifecycleState.INITIALISING
                if isinstance(payload, AircraftSpawnedPayload)
                else SessionLifecycleState.RUNNING
            )
            if (
                session.lifecycle_state != required
                or event.sim_time != session.simulation_time
                or event.wall_time_utc < session.updated_at
            ):
                raise ValueError("traffic event conflicts with committed session lifecycle/time")
        else:
            raise ValueError("history must start with one creation event")
    assert session is not None
    project_traffic(events)
    return SessionProjection(session, len(events))


@dataclass(frozen=True, slots=True)
class WriteRequest:
    session_id: str
    idempotency_key: str
    command_type: str
    expected_version: int
    semantic_input_json: str

    def fingerprint(self) -> str:
        """Canonical command input, excluding transport metadata and generated IDs."""
        for value in (self.session_id, self.idempotency_key, self.command_type):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("request identifiers must be non-empty")
        if type(self.expected_version) is not int or self.expected_version < 0:
            raise ValueError("expected version must be a non-negative integer")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate semantic input key")
                result[key] = value
            return result

        value = json.loads(self.semantic_input_json, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError("semantic input must be a JSON object")
        return json.dumps(
            [self.command_type, self.session_id, self.expected_version, value],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


@dataclass(frozen=True, slots=True)
class CommitResult:
    """Original committed events and state, including on a retry after later writes."""

    events: tuple[DomainEvent, ...]
    projection: SessionProjection


# Builder receives the next sequence under the write lock. It must be pure: no I/O,
# publication, adapter calls or mutation of live state before commit returns.
EventBuilder = Callable[[int], tuple[DomainEvent, ...]]


class SessionUnitOfWork(Protocol):
    def commit(self, request: WriteRequest, build: EventBuilder) -> CommitResult: ...
    def get_session(self, session_id: str) -> SessionProjection | None: ...
