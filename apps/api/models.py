from typing import Literal

from pydantic import BaseModel

from packages.domain.health import ComponentHealth, HealthStatus


class HealthResponse(BaseModel):
    """Readiness and non-sensitive configuration schema version only."""

    status: Literal["ok"]
    configuration_version: Literal["1.0"]
    readiness: HealthStatus = HealthStatus.HEALTHY
    components: tuple[ComponentHealth, ...] = ()
