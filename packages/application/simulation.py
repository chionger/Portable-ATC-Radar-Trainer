"""Neutral provider port, defensive translation and durable command orchestration."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from packages.application.persistence import CommitResult
from packages.application.traffic import TrafficService, TrafficStore
from packages.application.traffic_projection import project_traffic
from packages.domain.simulation import (
    TARGET_STATES,
    ApplyResult,
    RejectionCode,
    RouteEffect,
    SimulationCommand,
    StateEffect,
)
from packages.domain.traffic import (
    AircraftRouteAssignedPayload,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
    TrafficConflict,
    TrafficState,
    route_traffic,
    transition_traffic,
)

TrafficFact = (
    AircraftRouteAssignedPayload | AircraftStateChangedPayload | RunwayOccupancyChangedPayload
)


class SimulationPort(Protocol):
    """Pure calculation over an immutable snapshot; no storage, events, IDs or clocks."""

    def apply(self, command: SimulationCommand, state: TrafficState) -> ApplyResult: ...


class SimulationRejected(ValueError):
    def __init__(self, code: RejectionCode) -> None:
        self.code = code
        super().__init__(code.value)


def translate_effects(
    state: TrafficState, command: SimulationCommand, supplied: ApplyResult
) -> tuple[TrafficState, tuple[TrafficFact, ...]]:
    """Revalidate provider output, scope, intent, versions and all domain invariants."""
    command = SimulationCommand.model_validate_json(command.model_dump_json())
    result = ApplyResult.model_validate_json(supplied.model_dump_json())
    if not result.accepted:
        assert result.rejection_code is not None
        raise SimulationRejected(result.rejection_code)
    aircraft = next((a for a in state.aircraft if a.aircraft_id == command.aircraft_id), None)
    if aircraft is None or aircraft.version != command.expected_entity_version:
        raise TrafficConflict("command entity/version does not match authoritative state")
    route_changes = bool(command.parameters.route and command.parameters.route != aircraft.route)
    expected_types = ("ROUTE_ASSIGNED", "STATE_CHANGED") if route_changes else ("STATE_CHANGED",)
    if tuple(effect.effect_type for effect in result.effects) != expected_types:
        raise ValueError("provider effects do not match command structure")
    facts: list[TrafficFact] = []
    current = state
    for effect in result.effects:
        if effect.entity_id != command.aircraft_id:
            raise ValueError("provider effect targets another aircraft")
        payload = effect.structured_payload
        if isinstance(payload, RouteEffect):
            if payload.route != command.parameters.route:
                raise ValueError("provider changed requested route")
            current, fact = route_traffic(
                current, effect.entity_id, payload.route, payload.expected_entity_version
            )
            facts.append(fact)
        elif isinstance(payload, StateEffect):
            if (
                payload.target != TARGET_STATES[command.action]
                or payload.holding_point_id != command.parameters.holding_point_id
                or payload.runway_id != command.parameters.runway_id
            ):
                raise ValueError("provider state effect does not match command intent")
            current, changes = transition_traffic(
                current,
                effect.entity_id,
                payload.target,
                expected_version=payload.expected_entity_version,
                expected_runway_version=payload.expected_runway_version,
                holding_point_id=payload.holding_point_id,
                runway_id=payload.runway_id,
            )
            facts.extend(changes)
    changed = next(a for a in current.aircraft if a.aircraft_id == command.aircraft_id)
    if changed.version != result.resulting_entity_version:
        raise ValueError("provider resulting version is inconsistent")
    return current, tuple(facts)


class SimulationService(TrafficService):
    def __init__(
        self,
        store: TrafficStore,
        provider: SimulationPort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        on_committed: Callable[[CommitResult], None] | None = None,
    ) -> None:
        super().__init__(store, clock=clock)
        self.provider = provider
        self.on_committed = on_committed

    def apply(
        self,
        session_id: str,
        command: SimulationCommand,
        *,
        expected_session_version: int,
        idempotency_key: UUID,
        correlation_id: UUID,
    ) -> CommitResult:
        command = SimulationCommand.model_validate_json(command.model_dump_json())
        history = self.store.read_after(session_id, 0)
        state = project_traffic(history)
        current = self.store.get_session(session_id)
        facts: tuple[TrafficFact, ...] = ()
        failure: Exception | None = None
        # Provider work is outside the write lock. Defer failure so durable retries
        # still return their original result even if the provider is now unavailable.
        try:
            if state is None or current is None:
                raise TrafficConflict("traffic not initialised")
            if command.issued_at_sim_time != current.session.simulation_time:
                raise TrafficConflict("command simulation time does not match session")
            supplied = self.provider.apply(command, state)
            _, facts = translate_effects(state, command, supplied)
        except Exception as error:
            failure = error

        def effects() -> tuple[TrafficFact, ...]:
            if failure is not None:
                raise failure
            return facts

        result = self._commit(
            session_id,
            idempotency_key,
            correlation_id,
            expected_session_version,
            "simulation.apply",
            command.canonical_fields(),
            history[-1].sequence if history else 0,
            effects,
            causation_id=command.command_id,
        )
        # Publication notification is strictly after durable commit. The durable
        # outbox owns delivery. Retries can notify again; consumers must deduplicate.
        if self.on_committed is not None:
            self.on_committed(result)
        return result
