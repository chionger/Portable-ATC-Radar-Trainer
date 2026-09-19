"""Validation diagnostics and immutable catalogue ports."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from packages.domain.scenario import (
    Entity,
    ErrorInjection,
    HoldingPoint,
    Objective,
    Runway,
    Scenario,
    ScheduledEvent,
    Taxiway,
)


@dataclass(frozen=True)
class ScenarioIssue:
    location: str
    code: str


class ScenarioInvalid(ValueError):
    def __init__(self, *issues: ScenarioIssue) -> None:
        self.issues = issues
        super().__init__("Scenario validation failed")


class ScenarioMissing(ValueError):
    pass


class ScenarioCatalogue(Protocol):
    def list(self) -> tuple[Scenario, ...]: ...
    def get(self, scenario_id: str, version: str | None = None) -> Scenario: ...


def validate_references(scenario: Scenario) -> None:
    issues = []
    groups: dict[
        str,
        Sequence[
            Runway | Taxiway | HoldingPoint | Entity | ScheduledEvent | Objective | ErrorInjection
        ],
    ] = {
        "geometry.runways": scenario.geometry.runways,
        "geometry.taxiways": scenario.geometry.taxiways,
        "geometry.holding_points": scenario.geometry.holding_points,
        "entities": scenario.entities,
        "schedules": scenario.schedules,
        "objectives": scenario.objectives,
        "error_injections": scenario.error_injections,
    }
    seen: set[str] = set()
    for group, items in groups.items():
        for index, item in enumerate(items):
            if item.id in seen:
                issues.append(ScenarioIssue(f"{group}.{index}.id", "duplicate_id"))
            seen.add(item.id)
    runways = {item.id for item in scenario.geometry.runways}
    taxiways = {item.id for item in scenario.geometry.taxiways}
    geometry = runways | taxiways | {item.id for item in scenario.geometry.holding_points}
    entities = {item.id for item in scenario.entities}
    objectives = {item.id for item in scenario.objectives}

    def reference(value: str, allowed: set[str], location: str) -> None:
        if value not in allowed:
            issues.append(ScenarioIssue(location, "unknown_reference"))

    for index, item in enumerate(scenario.geometry.holding_points):
        reference(item.runway_id, runways, f"geometry.holding_points.{index}.runway_id")
        reference(item.taxiway_id, taxiways, f"geometry.holding_points.{index}.taxiway_id")
    callsigns: set[str] = set()
    for index, entity in enumerate(scenario.entities):
        if entity.callsign in callsigns:
            issues.append(ScenarioIssue(f"entities.{index}.callsign", "duplicate_callsign"))
        callsigns.add(entity.callsign)
        for route_index, target in enumerate(entity.route):
            reference(target, geometry, f"entities.{index}.route.{route_index}")
    references: tuple[tuple[str, Sequence[ScheduledEvent | Objective | ErrorInjection]], ...] = (
        ("schedules", scenario.schedules),
        ("objectives", scenario.objectives),
        ("error_injections", scenario.error_injections),
    )
    for group, entries in references:
        for index, entry in enumerate(entries):
            reference(entry.entity_id, entities, f"{group}.{index}.entity_id")
    for index, objective in enumerate(scenario.objectives):
        reference(objective.target_id, geometry, f"objectives.{index}.target_id")
    for index, target in enumerate(scenario.end_conditions.success_objectives):
        reference(target, objectives, f"end_conditions.success_objectives.{index}")
    for group, entries in (
        ("schedules", scenario.schedules),
        ("error_injections", scenario.error_injections),
    ):
        for index, timed in enumerate(entries):
            if (
                isinstance(timed, ScheduledEvent | ErrorInjection)
                and timed.at_seconds > scenario.end_conditions.time_limit_seconds
            ):
                issues.append(ScenarioIssue(f"{group}.{index}.at_seconds", "after_end"))
    if issues:
        raise ScenarioInvalid(*issues)
