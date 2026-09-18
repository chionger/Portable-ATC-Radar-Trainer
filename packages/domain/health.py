"""Non-sensitive, immutable component health and metric contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREADY = "unready"


class HealthReason(StrEnum):
    OPERATIONAL = "operational"
    STARTING = "starting"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NOT_CONFIGURED = "not_configured"


class HealthSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


SEVERITY = {
    HealthStatus.HEALTHY: HealthSeverity.INFO,
    HealthStatus.DEGRADED: HealthSeverity.WARNING,
    HealthStatus.UNREADY: HealthSeverity.ERROR,
}
ComponentId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,47}$")]


class ComponentHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    component: ComponentId
    required: bool
    status: HealthStatus
    severity: HealthSeverity
    reason: HealthReason
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("health timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.severity != SEVERITY[self.status]:
            raise ValueError("severity must match health status")
        if (self.status == HealthStatus.HEALTHY) != (self.reason == HealthReason.OPERATIONAL):
            raise ValueError("only healthy components are operational")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"observed_at"})


class MetricName(StrEnum):
    REQUEST_DURATION_MS = "request_duration_ms"
    COMPONENT_LATENCY_MS = "component_latency_ms"


class MetricObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    name: MetricName
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)]


def readiness(components: tuple[ComponentHealth, ...]) -> HealthStatus:
    if not components or any(
        item.required and item.status == HealthStatus.UNREADY for item in components
    ):
        return HealthStatus.UNREADY
    if any(item.status != HealthStatus.HEALTHY for item in components):
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY
