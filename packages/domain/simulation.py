"""Version-one neutral simulation commands and effects; no event or storage ownership."""

from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from packages.domain.scenario import Identifier
from packages.domain.traffic import AircraftState, TrafficData


class SimulationAction(StrEnum):
    TAXI = "TAXI"
    HOLD = "HOLD"
    LINE_UP = "LINE_UP"
    TAKE_OFF = "TAKE_OFF"
    CONTINUE_APPROACH = "CONTINUE_APPROACH"
    LAND = "LAND"
    GO_AROUND = "GO_AROUND"
    VACATE = "VACATE"


TARGET_STATES = MappingProxyType(
    {
        SimulationAction.TAXI: AircraftState.TAXIING,
        SimulationAction.HOLD: AircraftState.HOLDING,
        SimulationAction.LINE_UP: AircraftState.LINED_UP,
        SimulationAction.TAKE_OFF: AircraftState.TAKEOFF_ROLL,
        SimulationAction.CONTINUE_APPROACH: AircraftState.FINAL,
        SimulationAction.LAND: AircraftState.LANDING_ROLL,
        SimulationAction.GO_AROUND: AircraftState.AIRBORNE,
        SimulationAction.VACATE: AircraftState.VACATING,
    }
)


class RejectionCode(StrEnum):
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    ILLEGAL_STATE = "ILLEGAL_STATE"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    RUNWAY_CLOSED = "RUNWAY_CLOSED"


class SimulationParameters(TrafficData):
    route: Annotated[tuple[Identifier, ...], Field(max_length=256)] = ()
    holding_point_id: Identifier | None = None
    runway_id: Identifier | None = None


class SimulationCommand(TrafficData):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identifier
    aircraft_id: Identifier
    action: SimulationAction
    parameters: SimulationParameters = SimulationParameters()
    expected_entity_version: Annotated[int, Field(ge=1)]
    issued_at_sim_time: Annotated[float, Field(ge=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def parameters_for_action(self) -> Self:
        if self.parameters.route and self.action != SimulationAction.TAXI:
            raise ValueError("only TAXI accepts a route")
        if (self.action == SimulationAction.HOLD) != (self.parameters.holding_point_id is not None):
            raise ValueError("HOLD requires a holding point; other actions forbid it")
        return self


class StateEffect(TrafficData):
    target: AircraftState
    expected_entity_version: Annotated[int, Field(ge=1)]
    expected_runway_version: Annotated[int, Field(ge=1)] | None = None
    holding_point_id: Identifier | None = None
    runway_id: Identifier | None = None


class RouteEffect(TrafficData):
    route: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=256)]
    expected_entity_version: Annotated[int, Field(ge=1)]


class ProviderEffect(TrafficData):
    effect_type: Literal["STATE_CHANGED", "ROUTE_ASSIGNED"]
    entity_id: Identifier
    structured_payload: StateEffect | RouteEffect

    @model_validator(mode="after")
    def matching_payload(self) -> Self:
        expected = StateEffect if self.effect_type == "STATE_CHANGED" else RouteEffect
        if type(self.structured_payload) is not expected:
            raise ValueError("effect type/payload mismatch")
        return self


class ApplyResult(TrafficData):
    schema_version: Literal["1.0"] = "1.0"
    accepted: bool
    rejection_code: RejectionCode | None = None
    effects: Annotated[tuple[ProviderEffect, ...], Field(max_length=2)] = ()
    resulting_entity_version: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.accepted:
            if (
                self.rejection_code is not None
                or not self.effects
                or self.resulting_entity_version is None
            ):
                raise ValueError("accepted result requires effects/version and no rejection")
        elif self.rejection_code is None or self.effects:
            raise ValueError("rejection requires a code and no effects")
        return self
