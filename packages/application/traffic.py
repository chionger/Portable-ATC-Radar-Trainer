"""Durable traffic effects: aircraft and occupancy share one event transaction."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from packages.application.events import EventRepository
from packages.application.persistence import CommitResult, SessionUnitOfWork, WriteRequest
from packages.application.traffic_projection import initial_traffic, project_traffic
from packages.domain.events import DomainEvent, EventActor, EventSource, EventType
from packages.domain.scenario import Scenario
from packages.domain.session import SessionLifecycleState
from packages.domain.traffic import (
    AircraftSpawnedPayload,
    AircraftState,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
    TrafficConflict,
    TrafficState,
    transition_traffic,
)


class TrafficStore(SessionUnitOfWork, EventRepository, Protocol):
    pass


class TrafficService:
    def __init__(
        self, store: TrafficStore, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.store = store
        self.clock = clock

    def get(self, session_id: str) -> TrafficState | None:
        return project_traffic(self.store.read_after(session_id, 0))

    def _commit(
        self,
        session_id: str,
        key: UUID,
        correlation_id: UUID,
        expected_session_version: int,
        command: str,
        inputs: dict[str, object],
        observed_sequence: int,
        effects: Callable[
            [],
            tuple[
                AircraftSpawnedPayload
                | AircraftStateChangedPayload
                | RunwayOccupancyChangedPayload,
                ...,
            ],
        ],
    ) -> CommitResult:
        current = self.store.get_session(session_id)
        if current is None:
            raise TrafficConflict("session not found")
        now = self.clock()
        request = WriteRequest(
            session_id,
            str(key),
            command,
            expected_session_version,
            json.dumps(inputs, sort_keys=True),
        )
        # Identity/time allocation precedes the pure builder. At most 256 scenario
        # aircraft are allowed; normal state changes emit one or two facts.
        ids = tuple(str(uuid4()) for _ in range(256))

        def build(sequence: int) -> tuple[DomainEvent, ...]:
            if sequence != observed_sequence + 1:
                raise TrafficConflict("traffic history changed; reload before a new command")
            required = (
                SessionLifecycleState.INITIALISING
                if command == "traffic.initialise"
                else SessionLifecycleState.RUNNING
            )
            if current.session.lifecycle_state != required:
                raise TrafficConflict("session lifecycle does not permit traffic operation")
            result = []
            for offset, payload in enumerate(effects()):
                kind = (
                    EventType.AIRCRAFT_SPAWNED
                    if isinstance(payload, AircraftSpawnedPayload)
                    else EventType.AIRCRAFT_STATE_CHANGED
                    if isinstance(payload, AircraftStateChangedPayload)
                    else EventType.RUNWAY_OCCUPANCY_CHANGED
                )
                result.append(
                    DomainEvent(
                        event_id=ids[offset],
                        event_type=kind,
                        session_id=session_id,
                        sequence=sequence + offset,
                        sim_time=current.session.simulation_time,
                        wall_time_utc=now,
                        actor=EventActor(kind="system"),
                        source=EventSource(component="traffic", version="1.0"),
                        correlation_id=str(correlation_id),
                        payload=payload,
                    )
                )
            return tuple(result)

        return self.store.commit(request, build)

    def initialise(
        self,
        session_id: str,
        scenario: Scenario,
        *,
        expected_session_version: int,
        idempotency_key: UUID,
        correlation_id: UUID,
    ) -> CommitResult:
        current = self.store.get_session(session_id)
        if current is None:
            raise TrafficConflict("session not found")
        history = self.store.read_after(session_id, 0)
        existing = project_traffic(history)
        mapped = initial_traffic(scenario)

        def effects() -> tuple[AircraftSpawnedPayload, ...]:
            if existing is not None:
                raise TrafficConflict("traffic already initialised")
            if (
                current.session.scenario_id,
                current.session.scenario_version,
                current.session.scenario_hash,
            ) != (scenario.id, scenario.version, scenario.content_hash()):
                raise TrafficConflict("scenario does not match pinned session")
            return tuple(
                AircraftSpawnedPayload(aircraft=a, aerodrome=mapped.aerodrome if i == 0 else None)
                for i, a in enumerate(mapped.aircraft)
            )

        return self._commit(
            session_id,
            idempotency_key,
            correlation_id,
            expected_session_version,
            "traffic.initialise",
            {"scenario_hash": scenario.content_hash()},
            history[-1].sequence,
            effects,
        )

    def transition(
        self,
        session_id: str,
        aircraft_id: str,
        target: AircraftState,
        *,
        expected_session_version: int,
        expected_version: int,
        expected_runway_version: int | None = None,
        holding_point_id: str | None = None,
        runway_id: str | None = None,
        idempotency_key: UUID,
        correlation_id: UUID,
    ) -> CommitResult:
        history = self.store.read_after(session_id, 0)
        current = project_traffic(history)

        def effects() -> tuple[AircraftStateChangedPayload | RunwayOccupancyChangedPayload, ...]:
            if current is None:
                raise TrafficConflict("traffic not initialised")
            _, facts = transition_traffic(
                current,
                aircraft_id,
                target,
                expected_version=expected_version,
                expected_runway_version=expected_runway_version,
                holding_point_id=holding_point_id,
                runway_id=runway_id,
            )
            return facts

        return self._commit(
            session_id,
            idempotency_key,
            correlation_id,
            expected_session_version,
            "traffic.transition",
            {
                "aircraft_id": aircraft_id,
                "target": target.value,
                "expected_version": expected_version,
                "expected_runway_version": expected_runway_version,
                "holding_point_id": holding_point_id,
                "runway_id": runway_id,
            },
            history[-1].sequence if history else 0,
            effects,
        )
