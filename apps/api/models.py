from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Typed response returned by the process health endpoint."""

    status: Literal["ok"]

