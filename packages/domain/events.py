"""Versioned event contracts. No clocks, identity allocation or persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_validator,
    model_serializer,
    model_validator,
)

from packages.domain.health import ComponentHealth, HealthStatus
from packages.domain.session import (
    SessionFailure,
    SessionLifecycleState,
    SessionOutcome,
    SessionVersions,
    allowed_transitions,
)
from packages.domain.traffic import (
    AircraftSpawnedPayload,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
)

EVENT_SCHEMA_VERSION = "1.0"
CANONICAL_PROJECTION_VERSION = "1.0"
Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]


class EventType(StrEnum):
    SESSION_CREATED = "session.created"
    SESSION_INITIALISING = "session.initialising"
    SESSION_READY = "session.ready"
    SESSION_STARTED = "session.started"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"
    SESSION_COMPLETED = "session.completed"
    SESSION_STOPPED = "session.stopped"
    SESSION_FAILED = "session.failed"
    SCENARIO_LOADED = "scenario.loaded"
    SCENARIO_PHASE_CHANGED = "scenario.phase_changed"
    SCENARIO_OBJECTIVE_UPDATED = "scenario.objective_updated"
    SCENARIO_EVENT_TRIGGERED = "scenario.event_triggered"
    CONTROLLER_PTT_STARTED = "controller.ptt_started"
    CONTROLLER_PTT_STOPPED = "controller.ptt_stopped"
    AUDIO_RECEIVED = "audio.received"
    TRANSCRIPT_CREATED = "transcript.created"
    TRANSCRIPT_FAILED = "transcript.failed"
    COMMAND_EXTRACTED = "command.extracted"
    COMMAND_ACCEPTED = "command.accepted"
    COMMAND_REJECTED = "command.rejected"
    COMMAND_CLARIFICATION_REQUIRED = "command.clarification_required"
    COMMAND_DISPATCHED = "command.dispatched"
    CLEARANCE_ISSUED = "clearance.issued"
    CLEARANCE_READBACK_RECEIVED = "clearance.readback_received"
    CLEARANCE_READBACK_INCORRECT = "clearance.readback_incorrect"
    CLEARANCE_CORRECTED = "clearance.corrected"
    CLEARANCE_ACKNOWLEDGED = "clearance.acknowledged"
    INSTRUCTOR_MARKER_ADDED = "instructor.marker_added"
    INSTRUCTOR_OVERRIDE_APPLIED = "instructor.override_applied"
    RADIO_TRANSMISSION_QUEUED = "radio.transmission_queued"
    RADIO_TRANSMISSION_STARTED = "radio.transmission_started"
    RADIO_TRANSMISSION_FINISHED = "radio.transmission_finished"
    RADIO_TRANSMISSION_BLOCKED = "radio.transmission_blocked"
    AIRCRAFT_SPAWNED = "aircraft.spawned"
    AIRCRAFT_STATE_CHANGED = "aircraft.state_changed"
    AIRCRAFT_ROUTE_ASSIGNED = "aircraft.route_assigned"
    RUNWAY_OCCUPANCY_CHANGED = "runway.occupancy_changed"
    SIMULATION_SNAPSHOT_CREATED = "simulation.snapshot_created"
    SIMULATION_TIMING_ANOMALY = "simulation.timing_anomaly"
    COMPETENCY_OBSERVATION_DETECTED = "competency.observation_detected"
    COMPETENCY_OBSERVATION_RESOLVED = "competency.observation_resolved"
    SCORE_UPDATED = "score.updated"
    DEBRIEF_GENERATED = "debrief.generated"
    COMPONENT_HEALTH_CHANGED = "component.health_changed"
    ADAPTER_TIMEOUT = "adapter.timeout"
    ADAPTER_FAILED = "adapter.failed"


class ImmutableContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class EventActor(ImmutableContract):
    kind: Literal["system", "controller", "instructor", "adapter"]
    identifier: Text | None = None


class EventSource(ImmutableContract):
    component: Text
    version: Text


class TypedPayload(Protocol):
    def canonical_fields(self) -> dict[str, object]: ...


class SessionCreatedPayload(ImmutableContract):
    scenario_id: Text
    scenario_version: Text
    scenario_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    seed: Annotated[int, Field(strict=True, ge=0)]
    versions: SessionVersions
    state: Literal[SessionLifecycleState.CREATED] = SessionLifecycleState.CREATED
    version: Literal[1] = 1

    @model_serializer(mode="wrap")
    def compatible_document(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.scenario_hash is None:
            result.pop("scenario_hash", None)
        return result

    @field_validator("version", mode="before")
    @classmethod
    def exact_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value

    def canonical_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class SessionTransitionPayload(ImmutableContract):
    previous_state: SessionLifecycleState
    state: SessionLifecycleState
    previous_version: PositiveInt
    version: PositiveInt
    outcome: SessionOutcome | None = None
    failure: SessionFailure | None = None

    @model_validator(mode="after")
    def valid_transition(self) -> Self:
        if self.state not in allowed_transitions(self.previous_state):
            raise ValueError("illegal session transition")
        if self.version != self.previous_version + 1:
            raise ValueError("session version must advance by one")
        if self.previous_state == SessionLifecycleState.CREATED and self.previous_version != 1:
            raise ValueError("CREATED must have initial session version")
        terminal = self.state in {
            SessionLifecycleState.COMPLETED,
            SessionLifecycleState.STOPPED,
            SessionLifecycleState.FAILED,
        }
        if self.outcome != (SessionOutcome(self.state.value) if terminal else None):
            raise ValueError("outcome does not match destination state")
        if (self.failure is not None) != (self.state == SessionLifecycleState.FAILED):
            raise ValueError("failure details required exactly for FAILED")
        return self

    def canonical_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ComponentHealthChangedPayload(ImmutableContract):
    previous_status: HealthStatus | None
    health: ComponentHealth

    def canonical_fields(self) -> dict[str, object]:
        return {"previous_status": self.previous_status, "health": self.health.material_fields()}


def transition_event_type(payload: SessionTransitionPayload) -> EventType:
    if payload.state == SessionLifecycleState.RUNNING:
        return (
            EventType.SESSION_RESUMED
            if payload.previous_state == SessionLifecycleState.PAUSED
            else EventType.SESSION_STARTED
        )
    return EventType(f"session.{payload.state.value.lower()}")


@dataclass(frozen=True, slots=True)
class EventSchema:
    event_type: EventType
    payload_type: (
        type[SessionCreatedPayload]
        | type[SessionTransitionPayload]
        | type[ComponentHealthChangedPayload]
        | type[AircraftSpawnedPayload]
        | type[AircraftStateChangedPayload]
        | type[RunwayOccupancyChangedPayload]
        | None
    )
    schema_version: str = EVENT_SCHEMA_VERSION
    projection_version: str = CANONICAL_PROJECTION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise ValueError("event name must be in the catalogue")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported schema version")
        if self.projection_version != CANONICAL_PROJECTION_VERSION:
            raise ValueError("unsupported projection version")
        expected = (
            SessionCreatedPayload
            if self.event_type == EventType.SESSION_CREATED
            else SessionTransitionPayload
            if self.event_type.value.startswith("session.")
            else ComponentHealthChangedPayload
            if self.event_type == EventType.COMPONENT_HEALTH_CHANGED
            else AircraftSpawnedPayload
            if self.event_type == EventType.AIRCRAFT_SPAWNED
            else AircraftStateChangedPayload
            if self.event_type == EventType.AIRCRAFT_STATE_CHANGED
            else RunwayOccupancyChangedPayload
            if self.event_type == EventType.RUNWAY_OCCUPANCY_CHANGED
            else None
        )
        if self.payload_type is not expected:
            raise ValueError("payload type must match implemented or reserved catalogue entry")


@dataclass(frozen=True, slots=True)
class EventRegistry:
    entries: tuple[EventSchema, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or any(
            not isinstance(entry, EventSchema) for entry in self.entries
        ):
            raise ValueError("registry entries must be an immutable tuple of schemas")
        if len({entry.event_type for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate event name")

    def get(self, event_type: EventType) -> EventSchema:
        for entry in self.entries:
            if entry.event_type == event_type:
                return entry
        raise ValueError("unregistered event type")


EVENT_REGISTRY = EventRegistry(
    tuple(
        EventSchema(
            event_type,
            SessionCreatedPayload
            if event_type == EventType.SESSION_CREATED
            else SessionTransitionPayload
            if event_type.value.startswith("session.")
            else ComponentHealthChangedPayload
            if event_type == EventType.COMPONENT_HEALTH_CHANGED
            else AircraftSpawnedPayload
            if event_type == EventType.AIRCRAFT_SPAWNED
            else AircraftStateChangedPayload
            if event_type == EventType.AIRCRAFT_STATE_CHANGED
            else RunwayOccupancyChangedPayload
            if event_type == EventType.RUNWAY_OCCUPANCY_CHANGED
            else None,
        )
        for event_type in EventType
    )
)


class DomainEvent(ImmutableContract):
    event_id: Text
    event_type: EventType
    schema_version: Text = EVENT_SCHEMA_VERSION
    session_id: Text
    sequence: PositiveInt
    sim_time: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    wall_time_utc: datetime
    actor: EventActor
    source: EventSource
    correlation_id: Text
    causation_id: Text | None = None
    payload: (
        SessionCreatedPayload
        | SessionTransitionPayload
        | ComponentHealthChangedPayload
        | AircraftSpawnedPayload
        | AircraftStateChangedPayload
        | RunwayOccupancyChangedPayload
    )

    @field_validator("wall_time_utc")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("wall_time_utc must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def registered_contract(self) -> Self:
        entry = EVENT_REGISTRY.get(self.event_type)
        if self.schema_version != entry.schema_version:
            raise ValueError("unsupported event schema version; explicit migration required")
        if entry.payload_type is None:
            raise ValueError("event payload is reserved for a later producer")
        if type(self.payload) is not entry.payload_type:
            raise ValueError("payload does not match event type")
        if isinstance(self.payload, SessionCreatedPayload):
            if self.sequence != 1 or self.sim_time != 0:
                raise ValueError("session.created must be first with zero simulation time")
        elif isinstance(self.payload, ComponentHealthChangedPayload):
            if self.sequence <= 1 or self.payload.health.observed_at != self.wall_time_utc:
                raise ValueError("health event requires a session and matching observation time")
        elif isinstance(
            self.payload,
            AircraftSpawnedPayload | AircraftStateChangedPayload | RunwayOccupancyChangedPayload,
        ):
            if self.sequence <= 1:
                raise ValueError("traffic event requires a session")
        else:
            if self.sequence <= 1:
                raise ValueError("session transition must follow session.created")
            if self.sequence < self.payload.version:
                raise ValueError("event sequence cannot precede session version")
            if transition_event_type(self.payload) != self.event_type:
                raise ValueError("event name does not match transition")
            if (
                self.payload.previous_state
                in {
                    SessionLifecycleState.CREATED,
                    SessionLifecycleState.INITIALISING,
                    SessionLifecycleState.READY,
                }
                and self.sim_time != 0
            ):
                raise ValueError("simulation time cannot advance before starting")
        return self

    def canonical_projection(self) -> dict[str, object]:
        """Fresh comparison document; generated identity and wall time are excluded."""
        return {
            "projection_version": EVENT_REGISTRY.get(self.event_type).projection_version,
            "event_type": self.event_type.value,
            "sequence": self.sequence,
            "sim_time": self.sim_time,
            "actor_kind": self.actor.kind,
            "source": self.source.model_dump(mode="json"),
            "payload": self.payload.canonical_fields(),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_projection(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
