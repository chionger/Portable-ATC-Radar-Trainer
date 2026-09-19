"""Immutable version-1 scenario data; no expressions or executable actions."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")]
Finite = Annotated[float, Field(allow_inf_nan=False, ge=-1000000, le=1000000)]
Seconds = Annotated[float, Field(allow_inf_nan=False, ge=0, le=86400)]


class ScenarioData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Point(ScenarioData):
    x: Finite
    y: Finite


class Runway(ScenarioData):
    id: Identifier
    threshold: Point
    end: Point
    width_m: Annotated[float, Field(gt=0, le=200, allow_inf_nan=False)]

    @model_validator(mode="after")
    def nonzero(self) -> Self:
        if self.threshold == self.end:
            raise ValueError("threshold and end must differ")
        return self


class Taxiway(ScenarioData):
    id: Identifier
    points: Annotated[tuple[Point, ...], Field(min_length=2, max_length=256)]

    @model_validator(mode="after")
    def nonzero(self) -> Self:
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("adjacent points must differ")
        return self


class HoldingPoint(ScenarioData):
    id: Identifier
    position: Point
    runway_id: Identifier
    taxiway_id: Identifier


class Geometry(ScenarioData):
    coordinate_system: Literal["local_metres"] = "local_metres"
    runways: Annotated[tuple[Runway, ...], Field(min_length=1, max_length=16)]
    taxiways: Annotated[tuple[Taxiway, ...], Field(max_length=256)] = ()
    holding_points: Annotated[tuple[HoldingPoint, ...], Field(max_length=256)] = ()


class Environment(ScenarioData):
    wind_direction_deg: Annotated[float, Field(ge=0, lt=360, allow_inf_nan=False)] = 0
    wind_speed_kt: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 0
    visibility_m: Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)] = 10000
    frequency_mhz: Annotated[float, Field(ge=118, le=137, allow_inf_nan=False)]


class Entity(ScenarioData):
    id: Identifier
    callsign: Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9 -]{0,31}$")]
    position: Point
    state: Literal["PARKED", "TAXIING", "HOLDING", "INBOUND", "FINAL"]
    route: Annotated[tuple[Identifier, ...], Field(max_length=256)] = ()


class ScheduledEvent(ScenarioData):
    id: Identifier
    at_seconds: Seconds
    entity_id: Identifier
    action: Literal["activate", "request_taxi", "report_inbound"]


class Objective(ScenarioData):
    id: Identifier
    description: Annotated[str, Field(min_length=1, max_length=512)]
    entity_id: Identifier
    target_id: Identifier
    kind: Literal["reach", "hold", "vacate"]


class ErrorInjection(ScenarioData):
    id: Identifier
    entity_id: Identifier
    at_seconds: Seconds
    kind: Literal["incorrect_readback", "delayed_response"]
    probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1


class EndConditions(ScenarioData):
    time_limit_seconds: Annotated[float, Field(gt=0, le=86400, allow_inf_nan=False)]
    success_objectives: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=256)]
    failure_on_timeout: bool = True


class Presentation(ScenarioData):
    title: Annotated[str, Field(min_length=1, max_length=128)]
    description: Annotated[str, Field(max_length=2048)] = ""


class Scenario(ScenarioData):
    schema_version: Literal["1.0"]
    id: Identifier
    version: Identifier
    default_seed: Annotated[int, Field(ge=0, le=2**63 - 1)]
    presentation: Presentation
    geometry: Geometry
    environment: Environment
    entities: Annotated[tuple[Entity, ...], Field(min_length=1, max_length=256)]
    schedules: Annotated[tuple[ScheduledEvent, ...], Field(max_length=1024)] = ()
    objectives: Annotated[tuple[Objective, ...], Field(min_length=1, max_length=256)]
    error_injections: Annotated[tuple[ErrorInjection, ...], Field(max_length=1024)] = ()
    end_conditions: EndConditions

    def content_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ScenarioLoadedPayload(ScenarioData):
    """Future initialisation event contract; not activated/emitted by FP-009."""

    scenario_id: Identifier
    scenario_version: Identifier
    scenario_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    scenario_schema_version: Literal["1.0"] = "1.0"
