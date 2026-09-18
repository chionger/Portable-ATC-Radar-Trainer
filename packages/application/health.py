"""Local health registry; session changes become visible only after persistence."""

import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from packages.application.events import EventRepository
from packages.application.persistence import SessionUnitOfWork, WriteRequest
from packages.domain.events import (
    ComponentHealthChangedPayload,
    DomainEvent,
    EventActor,
    EventSource,
    EventType,
)
from packages.domain.health import (
    SEVERITY,
    ComponentHealth,
    HealthReason,
    HealthStatus,
    MetricObservation,
    readiness,
)


@dataclass(frozen=True, slots=True)
class SessionHealthContext:
    session_id: str
    expected_version: int
    idempotency_key: UUID


class HealthEventStore(SessionUnitOfWork, EventRepository, Protocol):
    """Durable writes plus retained history for retry-safe health reconstruction."""


class _UnchangedHealth(ValueError):
    """A heartbeat needs no durable event or sequence reservation."""


class HealthRegistry:
    def __init__(
        self,
        timeout_seconds: float = 30,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        unit_of_work: HealthEventStore | None = None,
    ) -> None:
        if not 0 < timeout_seconds <= 3600:
            raise ValueError("health timeout must be 0..3600 seconds")
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self._unit_of_work = unit_of_work
        self._lock = RLock()
        self._components: dict[str, ComponentHealth] = {}
        self._metrics: deque[MetricObservation] = deque(maxlen=100)

    def register(self, component: str, *, required: bool = True) -> None:
        initial = ComponentHealth(
            component=component,
            required=required,
            status=HealthStatus.UNREADY,
            severity=SEVERITY[HealthStatus.UNREADY],
            reason=HealthReason.STARTING,
            observed_at=self.clock(),
        )
        with self._lock:
            if component in self._components:
                raise ValueError("component already registered")
            self._components[component] = initial

    def observe_metric(self, observation: MetricObservation) -> None:
        validated = MetricObservation.model_validate_json(observation.model_dump_json())
        with self._lock:
            self._metrics.append(validated)

    def metrics(self) -> tuple[MetricObservation, ...]:
        with self._lock:
            return tuple(self._metrics)

    def snapshot(self) -> tuple[HealthStatus, tuple[ComponentHealth, ...]]:
        """Derive stale readiness without I/O or session mutation from GET /health."""
        with self._lock:
            now = self.clock()
            components = []
            for component in sorted(self._components):
                value = self._components[component]
                age = (now - value.observed_at).total_seconds()
                if age < 0 or age >= self.timeout_seconds:
                    value = value.model_copy(
                        update={
                            "status": HealthStatus.UNREADY,
                            "severity": SEVERITY[HealthStatus.UNREADY],
                            "reason": HealthReason.TIMEOUT,
                        }
                    )
                components.append(value)
            values = tuple(components)
            return readiness(values), values

    def report(
        self,
        component: str,
        status: HealthStatus,
        reason: HealthReason,
        *,
        correlation_id: UUID,
        session: SessionHealthContext | None = None,
    ) -> bool:
        """Return whether material fields changed. Callers use fixed registered IDs.

        Retain the session context on retries, including after an uncertain commit.
        Observations contain no exception, transcript, audio or configuration text.
        """
        if not isinstance(correlation_id, UUID):
            raise ValueError("correlation ID must be a UUID")
        with self._lock:
            previous = self._components[component]
            candidate = ComponentHealth(
                component=component,
                required=previous.required,
                status=status,
                severity=SEVERITY[status],
                reason=reason,
                observed_at=self.clock(),
            )
            if candidate.observed_at < previous.observed_at:
                raise ValueError("health observation cannot move backwards")
            old: ComponentHealth | None = previous
            if session is not None:
                if self._unit_of_work is None:
                    raise ValueError("session health requires a durable unit of work")
                prior_health = [
                    event.payload.health
                    for event in self._unit_of_work.read_after(session.session_id, 0)
                    if isinstance(event.payload, ComponentHealthChangedPayload)
                    and event.payload.health.component == component
                ]
                old = prior_health[-1] if prior_health else None
            changed = old is None or old.material_fields() != candidate.material_fields()
            if session is not None:
                if self._unit_of_work is None:
                    raise ValueError("session health requires a durable unit of work")
                request = WriteRequest(
                    session.session_id,
                    str(session.idempotency_key),
                    "component.health_changed",
                    session.expected_version,
                    json.dumps(candidate.material_fields(), sort_keys=True),
                )
                current = self._unit_of_work.get_session(session.session_id)
                if current is None:
                    raise ValueError("session health requires an existing session")

                def build(sequence: int) -> tuple[DomainEvent, ...]:
                    if not changed:
                        raise _UnchangedHealth()
                    return (
                        DomainEvent(
                            event_id=str(uuid4()),
                            event_type=EventType.COMPONENT_HEALTH_CHANGED,
                            session_id=session.session_id,
                            sequence=sequence,
                            sim_time=current.session.simulation_time,
                            wall_time_utc=candidate.observed_at,
                            actor=EventActor(kind="system"),
                            source=EventSource(component="health", version="1.0"),
                            correlation_id=str(correlation_id),
                            payload=ComponentHealthChangedPayload(
                                previous_status=old.status if old else None, health=candidate
                            ),
                        ),
                    )

                try:
                    result = self._unit_of_work.commit(request, build)
                except _UnchangedHealth:
                    pass
                else:
                    payload = result.events[-1].payload
                    if not isinstance(payload, ComponentHealthChangedPayload):
                        raise ValueError("unexpected durable health result")
                    # A matching old retry can return an earlier event. Reconstruct
                    # the latest durable health rather than reinstalling stale state.
                    durable = [
                        event.payload.health
                        for event in self._unit_of_work.read_after(session.session_id, 0)
                        if isinstance(event.payload, ComponentHealthChangedPayload)
                        and event.payload.health.component == component
                    ]
                    candidate = durable[-1]
                    changed = old is None or old.material_fields() != candidate.material_fields()
            # No candidate is installed if persistence fails. Heartbeats refresh the
            # observation but do not emit duplicate material-change events.
            self._components[component] = candidate
            return changed

    def expire(self, *, correlation_id: UUID, session: SessionHealthContext | None = None) -> None:
        """Explicit producer hook for material timeouts; never invoked by a health read."""
        _, values = self.snapshot()
        for value in values:
            if value.reason == HealthReason.TIMEOUT:
                self.report(
                    value.component,
                    HealthStatus.UNREADY,
                    HealthReason.TIMEOUT,
                    correlation_id=correlation_id,
                    session=replace(
                        session, idempotency_key=uuid5(session.idempotency_key, value.component)
                    )
                    if session
                    else None,
                )
