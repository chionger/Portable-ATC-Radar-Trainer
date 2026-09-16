from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Readiness and non-sensitive configuration schema version only."""

    status: Literal["ok"]
    configuration_version: Literal["1.0"]
