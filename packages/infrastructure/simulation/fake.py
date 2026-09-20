"""Stateless deterministic contract fake; no movement, clock, API or persistence."""

from packages.domain.simulation import (
    TARGET_STATES,
    ApplyResult,
    ProviderEffect,
    RejectionCode,
    RouteEffect,
    SimulationCommand,
    StateEffect,
)
from packages.domain.traffic import (
    RUNWAY_STATES,
    TRANSITIONS,
    TrafficState,
    route_traffic,
    transition_traffic,
)


class DeterministicFake:
    def apply(self, command: SimulationCommand, state: TrafficState) -> ApplyResult:
        command = SimulationCommand.model_validate_json(command.model_dump_json())
        state = TrafficState.model_validate_json(state.model_dump_json())
        aircraft = next((a for a in state.aircraft if a.aircraft_id == command.aircraft_id), None)
        if aircraft is None:
            return ApplyResult(accepted=False, rejection_code=RejectionCode.UNKNOWN_ENTITY)

        def reject(code: RejectionCode) -> ApplyResult:
            return ApplyResult(
                accepted=False, rejection_code=code, resulting_entity_version=aircraft.version
            )

        if aircraft.version != command.expected_entity_version:
            return reject(RejectionCode.VERSION_CONFLICT)
        target = TARGET_STATES[command.action]
        if target not in TRANSITIONS[aircraft.state]:
            return reject(RejectionCode.ILLEGAL_STATE)
        runway_id = command.parameters.runway_id or aircraft.assigned_runway_id
        runway = next((r for r in state.aerodrome.runways if r.geometry.id == runway_id), None)
        if (
            target in RUNWAY_STATES
            and aircraft.occupied_runway_id is None
            and runway is not None
            and runway.operational_status == "CLOSED"
        ):
            return reject(RejectionCode.RUNWAY_CLOSED)
        effects = []
        current = state
        version = aircraft.version
        try:
            if command.parameters.route and command.parameters.route != aircraft.route:
                current, _ = route_traffic(
                    current, aircraft.aircraft_id, command.parameters.route, version
                )
                effects.append(
                    ProviderEffect(
                        effect_type="ROUTE_ASSIGNED",
                        entity_id=aircraft.aircraft_id,
                        structured_payload=RouteEffect(
                            route=command.parameters.route, expected_entity_version=version
                        ),
                    )
                )
                version += 1
            expected_runway = runway.version if runway is not None else None
            updated, _ = transition_traffic(
                current,
                aircraft.aircraft_id,
                target,
                expected_version=version,
                expected_runway_version=expected_runway,
                holding_point_id=command.parameters.holding_point_id,
                runway_id=command.parameters.runway_id,
            )
            effects.append(
                ProviderEffect(
                    effect_type="STATE_CHANGED",
                    entity_id=aircraft.aircraft_id,
                    structured_payload=StateEffect(
                        target=target,
                        expected_entity_version=version,
                        expected_runway_version=expected_runway,
                        holding_point_id=command.parameters.holding_point_id,
                        runway_id=command.parameters.runway_id,
                    ),
                )
            )
        except ValueError:
            return reject(RejectionCode.INVALID_PARAMETERS)
        after = next(a for a in updated.aircraft if a.aircraft_id == aircraft.aircraft_id)
        return ApplyResult(
            accepted=True, effects=tuple(effects), resulting_entity_version=after.version
        )
