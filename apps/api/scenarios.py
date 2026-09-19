"""Metadata-only scenario catalogue routes; captures never run scenario actions."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi import Path as PathParameter
from pydantic import BaseModel

from packages.domain.scenario import Scenario
from packages.infrastructure.scenarios import LocalScenarioCatalogue


class ScenarioMetadata(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    version: str
    content_hash: str
    title: str
    description: str
    default_seed: int


def metadata(scenario: Scenario) -> ScenarioMetadata:
    return ScenarioMetadata(
        id=scenario.id,
        version=scenario.version,
        content_hash=scenario.content_hash(),
        title=scenario.presentation.title,
        description=scenario.presentation.description,
        default_seed=scenario.default_seed,
    )


def catalogue(request: Request) -> LocalScenarioCatalogue:
    with request.app.state.scenario_lock:
        if request.app.state.scenario_catalogue is None:
            directory = request.app.state.settings.scenarios.directory
            request.app.state.scenario_catalogue = LocalScenarioCatalogue(
                Path(directory) if directory else None,
            )
        result: LocalScenarioCatalogue = request.app.state.scenario_catalogue
        return result


router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioMetadata])
def list_scenarios(request: Request) -> list[ScenarioMetadata]:
    return [metadata(item) for item in catalogue(request).list()]


@router.get("/{scenario_id}", response_model=ScenarioMetadata)
def get_scenario(
    scenario_id: Annotated[str, PathParameter(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")],
    request: Request,
    version: Annotated[str | None, Query(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")] = None,
) -> ScenarioMetadata:
    return metadata(catalogue(request).get(scenario_id, version))
