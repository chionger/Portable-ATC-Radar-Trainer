"""Canonical immutable traffic state and the sole runway membership policy."""

from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.domain.scenario import Geometry, Identifier, Point, Runway


class AircraftState(StrEnum):
    PARKED = "PARKED"
    READY_TO_TAXI = "READY_TO_TAXI"
    TAXIING = "TAXIING"
    HOLDING = "HOLDING"
    LINED_UP = "LINED_UP"
    TAKEOFF_ROLL = "TAKEOFF_ROLL"
    AIRBORNE = "AIRBORNE"
    INBOUND = "INBOUND"
    FINAL = "FINAL"
    LANDING_ROLL = "LANDING_ROLL"
    VACATING = "VACATING"
    STOPPED = "STOPPED"


S = AircraftState
TRANSITIONS = MappingProxyType(
    {
        S.PARKED: frozenset({S.READY_TO_TAXI, S.STOPPED}),
        S.READY_TO_TAXI: frozenset({S.TAXIING, S.STOPPED}),
        S.TAXIING: frozenset({S.HOLDING, S.PARKED, S.STOPPED}),
        S.HOLDING: frozenset({S.TAXIING, S.LINED_UP, S.STOPPED}),
        S.LINED_UP: frozenset({S.TAKEOFF_ROLL, S.VACATING, S.STOPPED}),
        S.TAKEOFF_ROLL: frozenset({S.AIRBORNE, S.STOPPED}),
        S.AIRBORNE: frozenset({S.INBOUND}),
        S.INBOUND: frozenset({S.FINAL, S.AIRBORNE}),
        S.FINAL: frozenset({S.LANDING_ROLL, S.AIRBORNE}),
        S.LANDING_ROLL: frozenset({S.VACATING, S.STOPPED}),
        S.VACATING: frozenset({S.TAXIING, S.STOPPED}),
        S.STOPPED: frozenset(),
    }
)
RUNWAY_STATES = frozenset({S.LINED_UP, S.TAKEOFF_ROLL, S.LANDING_ROLL, S.VACATING})


class TrafficConflict(ValueError):
    """Stale entity version or illegal effect; original state is retained."""


class TrafficData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    def canonical_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class Aircraft(TrafficData):
    aircraft_id: Identifier
    callsign: Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9 -]{0,31}$")]
    aircraft_type: Identifier = "GENERIC"
    wake_category: Literal["LIGHT", "MEDIUM", "HEAVY", "SUPER"] | None = None
    position: Point
    heading_deg: Annotated[float, Field(ge=0, lt=360, allow_inf_nan=False)] = 0.0
    ground_speed_kt: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)] = 0.0
    altitude_ft: Annotated[float, Field(ge=-2000, le=100000, allow_inf_nan=False)] = 0.0
    state: AircraftState
    version: Annotated[int, Field(ge=1)] = 1
    route: tuple[Identifier, ...] = ()
    route_progress: Annotated[int, Field(ge=0)] = 0
    assigned_runway_id: Identifier | None = None
    holding_point_id: Identifier | None = None
    occupied_runway_id: Identifier | None = None
    clearance_id: Identifier | None = None
    clearance_state: Literal["NONE", "ACTIVE", "CANCELLED"] = "NONE"
    pilot_profile: Identifier = "default"
    response_state: Literal["IDLE", "PENDING", "RESPONDING"] = "IDLE"

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.clearance_state == "NONE") != (self.clearance_id is None):
            raise ValueError("clearance state requires a matching clearance identity")
        if self.route_progress > len(self.route):
            raise ValueError("route progress exceeds route length")
        if (self.state == S.HOLDING) != (self.holding_point_id is not None):
            raise ValueError("HOLDING requires a holding point, other states forbid it")
        if self.state in RUNWAY_STATES and self.occupied_runway_id is None:
            raise ValueError("runway state requires occupancy")
        if self.occupied_runway_id is not None:
            if self.state not in RUNWAY_STATES | {S.STOPPED}:
                raise ValueError("state cannot occupy a runway")
            if self.assigned_runway_id != self.occupied_runway_id:
                raise ValueError("occupancy must match assigned runway")
        return self


class RunwayState(TrafficData):
    geometry: Runway
    designator: Identifier
    operational_status: Literal["OPEN", "CLOSED"] = "OPEN"
    version: Annotated[int, Field(ge=1)] = 1
    occupants: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def unique_members(self) -> Self:
        if tuple(sorted(set(self.occupants))) != self.occupants:
            raise ValueError("occupancy members must be unique and sorted")
        return self

    @property
    def occupied(self) -> bool:
        return bool(self.occupants)


def occupancy(
    runway: RunwayState, aircraft_id: str, present: bool, expected_version: int
) -> RunwayState:
    """Set membership idempotently; never implicitly clear another occupant."""
    if type(expected_version) is not int or expected_version != runway.version:
        raise TrafficConflict("runway version changed")
    if type(present) is not bool:
        raise ValueError("membership must be boolean")
    if (aircraft_id in runway.occupants) == present:
        return runway
    if present and runway.operational_status != "OPEN":
        raise TrafficConflict("runway is closed")
    members = set(runway.occupants)
    if present:
        members.add(aircraft_id)
    else:
        members.remove(aircraft_id)
    return RunwayState.model_validate(
        runway.model_dump()
        | {
            "occupants": tuple(sorted(members)),
            "version": runway.version + 1,
        }
    )


class Aerodrome(TrafficData):
    geometry: Geometry
    runways: tuple[RunwayState, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        identifiers = [
            item.id
            for group in (
                self.geometry.runways,
                self.geometry.taxiways,
                self.geometry.holding_points,
            )
            for item in group
        ]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("duplicate geometry identifier")
        runway_ids = {r.id for r in self.geometry.runways}
        taxiway_ids = {t.id for t in self.geometry.taxiways}
        if any(
            h.runway_id not in runway_ids or h.taxiway_id not in taxiway_ids
            for h in self.geometry.holding_points
        ):
            raise ValueError("unknown holding point geometry reference")
        if len({r.geometry.id for r in self.runways}) != len(self.runways):
            raise ValueError("duplicate runway")
        if {r.geometry.id: r.geometry for r in self.runways} != {
            r.id: r for r in self.geometry.runways
        }:
            raise ValueError("runway geometry mismatch")
        return self


class TrafficState(TrafficData):
    aerodrome: Aerodrome
    aircraft: tuple[Aircraft, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len({a.aircraft_id for a in self.aircraft}) != len(self.aircraft):
            raise ValueError("duplicate aircraft")
        if len({a.callsign for a in self.aircraft}) != len(self.aircraft):
            raise ValueError("duplicate callsign")
        runways = {r.geometry.id: r for r in self.aerodrome.runways}
        holds = {h.id: h for h in self.aerodrome.geometry.holding_points}
        routes = set(runways) | set(holds) | {t.id for t in self.aerodrome.geometry.taxiways}
        for aircraft in self.aircraft:
            if any(item not in routes for item in aircraft.route):
                raise ValueError("unknown route reference")
            if (
                aircraft.assigned_runway_id is not None
                and aircraft.assigned_runway_id not in runways
            ):
                raise ValueError("unknown assigned runway")
            if aircraft.holding_point_id is not None:
                hold = holds.get(aircraft.holding_point_id)
                if hold is None or hold.runway_id != aircraft.assigned_runway_id:
                    raise ValueError("invalid holding point/runway assignment")
        for runway_id, runway in runways.items():
            expected = tuple(
                sorted(a.aircraft_id for a in self.aircraft if a.occupied_runway_id == runway_id)
            )
            if runway.occupants != expected:
                raise ValueError("aircraft/runway occupancy mismatch")
        return self


class AircraftSpawnedPayload(TrafficData):
    aircraft: Aircraft
    aerodrome: Aerodrome | None = None

    @model_validator(mode="after")
    def initial(self) -> Self:
        if self.aircraft.version != 1 or self.aircraft.occupied_runway_id is not None:
            raise ValueError("spawn must be initial and outside runway occupancy")
        if self.aerodrome and any(r.version != 1 or r.occupants for r in self.aerodrome.runways):
            raise ValueError("spawn geometry must have initial empty occupancy")
        return self


def change_aircraft(
    before: Aircraft,
    target: AircraftState,
    *,
    expected_version: int,
    holding_point_id: str | None = None,
    runway_id: str | None = None,
) -> Aircraft:
    if type(expected_version) is not int or expected_version != before.version:
        raise TrafficConflict("aircraft version changed")
    if target not in TRANSITIONS[before.state]:
        raise TrafficConflict("illegal aircraft transition")
    assigned = runway_id if runway_id is not None else before.assigned_runway_id
    if before.occupied_runway_id and assigned != before.assigned_runway_id:
        raise TrafficConflict("cannot reassign an occupied runway")
    occupied = (
        assigned
        if target in RUNWAY_STATES
        else before.occupied_runway_id
        if target == S.STOPPED
        else None
    )
    return Aircraft.model_validate(
        before.model_dump()
        | {
            "state": target,
            "version": before.version + 1,
            "holding_point_id": holding_point_id,
            "assigned_runway_id": assigned,
            "occupied_runway_id": occupied,
        }
    )


class AircraftStateChangedPayload(TrafficData):
    before: Aircraft
    after: Aircraft

    @model_validator(mode="after")
    def legal(self) -> Self:
        expected = change_aircraft(
            self.before,
            self.after.state,
            expected_version=self.before.version,
            holding_point_id=self.after.holding_point_id,
            runway_id=self.after.assigned_runway_id,
        )
        if self.after != expected:
            raise ValueError("state change modifies unrelated aircraft fields")
        return self


class RunwayOccupancyChangedPayload(TrafficData):
    before: RunwayState
    after: RunwayState
    aircraft_id: Identifier
    present: bool

    @model_validator(mode="after")
    def legal(self) -> Self:
        expected = occupancy(self.before, self.aircraft_id, self.present, self.before.version)
        if self.after != expected or self.after == self.before:
            raise ValueError("occupancy fact must be one material membership change")
        return self


def assign_route(before: Aircraft, route: tuple[str, ...], expected_version: int) -> Aircraft:
    if type(expected_version) is not int or expected_version != before.version:
        raise TrafficConflict("aircraft version changed")
    if before.occupied_runway_id or before.state not in {S.READY_TO_TAXI, S.TAXIING, S.HOLDING}:
        raise TrafficConflict("route assignment requires a ground aircraft outside the runway")
    if not route or len(route) > 256 or route == before.route:
        raise TrafficConflict("route assignment requires a material non-empty route")
    return Aircraft.model_validate(
        before.model_dump()
        | {
            "route": route,
            "route_progress": 0,
            "version": before.version + 1,
        }
    )


class AircraftRouteAssignedPayload(TrafficData):
    before: Aircraft
    after: Aircraft

    @model_validator(mode="after")
    def legal(self) -> Self:
        if self.after != assign_route(self.before, self.after.route, self.before.version):
            raise ValueError("route assignment modifies unrelated aircraft fields")
        return self


def route_traffic(
    state: TrafficState, aircraft_id: str, route: tuple[str, ...], expected_version: int
) -> tuple[TrafficState, AircraftRouteAssignedPayload]:
    before = next((a for a in state.aircraft if a.aircraft_id == aircraft_id), None)
    if before is None:
        raise TrafficConflict("unknown aircraft")
    after = assign_route(before, route, expected_version)
    updated = TrafficState(
        aerodrome=state.aerodrome,
        aircraft=tuple(after if a.aircraft_id == aircraft_id else a for a in state.aircraft),
    )
    return updated, AircraftRouteAssignedPayload(before=before, after=after)


def transition_traffic(
    state: TrafficState,
    aircraft_id: str,
    target: AircraftState,
    *,
    expected_version: int,
    expected_runway_version: int | None = None,
    holding_point_id: str | None = None,
    runway_id: str | None = None,
) -> tuple[TrafficState, tuple[AircraftStateChangedPayload | RunwayOccupancyChangedPayload, ...]]:
    if expected_runway_version is not None and type(expected_runway_version) is not int:
        raise TrafficConflict("runway version must be an integer")
    state = TrafficState.model_validate_json(state.model_dump_json())
    before = next((a for a in state.aircraft if a.aircraft_id == aircraft_id), None)
    if before is None:
        raise TrafficConflict("unknown aircraft")
    after = change_aircraft(
        before,
        target,
        expected_version=expected_version,
        holding_point_id=holding_point_id,
        runway_id=runway_id,
    )
    facts: list[AircraftStateChangedPayload | RunwayOccupancyChangedPayload] = [
        AircraftStateChangedPayload(before=before, after=after)
    ]
    runways = list(state.aerodrome.runways)
    if before.occupied_runway_id != after.occupied_runway_id:
        runway = before.occupied_runway_id or after.occupied_runway_id
        for index, item in enumerate(runways):
            if item.geometry.id == runway:
                if expected_runway_version is None:
                    raise TrafficConflict("runway version required")
                updated = occupancy(
                    item, aircraft_id, after.occupied_runway_id is not None, expected_runway_version
                )
                facts.append(
                    RunwayOccupancyChangedPayload(
                        before=item,
                        after=updated,
                        aircraft_id=aircraft_id,
                        present=after.occupied_runway_id is not None,
                    )
                )
                runways[index] = updated
                break
        else:
            raise TrafficConflict("unknown runway")
    elif expected_runway_version is not None:
        assigned_runway = next(
            (r for r in runways if r.geometry.id == after.assigned_runway_id), None
        )
        if assigned_runway is None or assigned_runway.version != expected_runway_version:
            raise TrafficConflict("runway version changed")
    result = TrafficState(
        aerodrome=Aerodrome(geometry=state.aerodrome.geometry, runways=tuple(runways)),
        aircraft=tuple(after if a.aircraft_id == aircraft_id else a for a in state.aircraft),
    )
    return result, tuple(facts)
