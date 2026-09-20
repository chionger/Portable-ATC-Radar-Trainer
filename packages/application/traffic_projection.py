"""Scenario mapping and deterministic traffic replay; no persistence or provider I/O."""

from packages.application.scenarios import validate_references
from packages.domain.events import DomainEvent
from packages.domain.scenario import Scenario
from packages.domain.traffic import (
    Aerodrome,
    Aircraft,
    AircraftSpawnedPayload,
    AircraftState,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
    RunwayState,
    TrafficState,
    occupancy,
)


def initial_traffic(scenario: Scenario) -> TrafficState:
    validate_references(scenario)
    runways = tuple(RunwayState(geometry=r, designator=r.id) for r in scenario.geometry.runways)
    runway_ids = {r.id for r in scenario.geometry.runways}
    aircraft = []
    for entity in scenario.entities:
        assigned = [item for item in entity.route if item in runway_ids]
        if len(set(assigned)) > 1:
            raise ValueError("initial route has ambiguous runway assignment")
        runway = assigned[0] if assigned else None
        hold = None
        if entity.state == "HOLDING":
            matches = [
                h
                for h in scenario.geometry.holding_points
                if h.position == entity.position and h.id in entity.route
            ]
            if len(matches) != 1:
                raise ValueError("HOLDING requires one matching holding point in the route")
            hold = matches[0].id
            if runway is not None and runway != matches[0].runway_id:
                raise ValueError("holding point conflicts with assigned runway")
            runway = matches[0].runway_id
        aircraft.append(
            Aircraft(
                aircraft_id=entity.id,
                callsign=entity.callsign,
                position=entity.position,
                state=AircraftState(entity.state),
                route=entity.route,
                assigned_runway_id=runway,
                holding_point_id=hold,
            )
        )
    return TrafficState(
        aerodrome=Aerodrome(geometry=scenario.geometry, runways=runways), aircraft=tuple(aircraft)
    )


def project_traffic(events: tuple[DomainEvent, ...]) -> TrafficState | None:
    aerodrome = None
    aircraft: dict[str, Aircraft] = {}
    runways: dict[str, RunwayState] = {}
    pending: RunwayOccupancyChangedPayload | None = None
    for event in events:
        payload = event.payload
        if pending is not None and payload != pending:
            raise ValueError("occupancy effect must immediately follow aircraft effect")
        if isinstance(payload, AircraftSpawnedPayload):
            if payload.aerodrome is not None:
                if aerodrome is not None:
                    raise ValueError("traffic geometry already initialised")
                aerodrome = payload.aerodrome
                runways = {r.geometry.id: r for r in aerodrome.runways}
            if aerodrome is None or payload.aircraft.aircraft_id in aircraft:
                raise ValueError("missing geometry or duplicate spawn")
            aircraft[payload.aircraft.aircraft_id] = payload.aircraft
        elif isinstance(payload, AircraftStateChangedPayload):
            if aircraft.get(payload.before.aircraft_id) != payload.before:
                raise ValueError("aircraft fact does not follow committed state")
            aircraft[payload.after.aircraft_id] = payload.after
            before_id, after_id = (
                payload.before.occupied_runway_id,
                payload.after.occupied_runway_id,
            )
            if before_id != after_id:
                runway = runways.get(before_id or after_id or "")
                if runway is None:
                    raise ValueError("occupancy change references unknown runway")
                pending = RunwayOccupancyChangedPayload(
                    before=runway,
                    after=occupancy(
                        runway, payload.after.aircraft_id, after_id is not None, runway.version
                    ),
                    aircraft_id=payload.after.aircraft_id,
                    present=after_id is not None,
                )
        elif isinstance(payload, RunwayOccupancyChangedPayload):
            if pending is None:
                raise ValueError("occupancy fact lacks associated aircraft effect")
            pending = None
            if runways.get(payload.before.geometry.id) != payload.before:
                raise ValueError("runway fact does not follow committed state")
            runways[payload.after.geometry.id] = payload.after
    if pending is not None:
        raise ValueError("incomplete aircraft/occupancy batch")
    if aerodrome is None:
        return None
    return TrafficState(
        aerodrome=Aerodrome(geometry=aerodrome.geometry, runways=tuple(runways.values())),
        aircraft=tuple(aircraft.values()),
    )
