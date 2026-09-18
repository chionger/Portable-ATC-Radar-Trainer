"""Pure lifecycle adapter and durable session workflows (FP-008)."""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from packages.application.events import EventContext, SessionEventFactory
from packages.application.persistence import SessionUnitOfWork, WriteRequest
from packages.domain.events import DomainEvent, EventActor, EventSource
from packages.domain.session import (
    CreateSessionRequest,
    Session,
    SessionFailure,
    SessionLifecycleState,
    SessionTransitionError,
    SessionVersions,
    TransitionErrorCode,
    TransitionRequest,
    TransitionResult,
    create_session,
    transition_session,
)


class SessionLifecycle(Protocol):
    def create(self, request: CreateSessionRequest) -> Session: ...

    def transition(self, session: Session, request: TransitionRequest) -> TransitionResult: ...


class DomainSessionLifecycle:
    """Delegates to the domain policy without storing state or performing I/O."""

    def create(self, request: CreateSessionRequest) -> Session:
        return create_session(request)

    def transition(self, session: Session, request: TransitionRequest) -> TransitionResult:
        return transition_session(session, request)


class SessionNotFound(ValueError):
    """The requested durable session does not exist."""


class DurableSessionService:
    """Lifecycle events and response projections share one durable commit."""

    def __init__(
        self,
        store: SessionUnitOfWork,
        versions: SessionVersions,
        *,
        default_seed: int = 0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.store = store
        self.versions = versions
        self.default_seed = default_seed
        self.clock = clock
        self.events = SessionEventFactory()

    @staticmethod
    def identity(key: UUID) -> str:
        return str(uuid5(NAMESPACE_URL, f"portable-atc/session/{key}"))

    @staticmethod
    def context(sequence: int, correlation_id: UUID, event_id: str) -> EventContext:
        return EventContext(
            event_id,
            sequence,
            sequence - 1,
            EventActor(kind="system"),
            EventSource(component="session_service", version="1.0"),
            str(correlation_id),
        )

    def get(self, session_id: str) -> Session:
        projection = self.store.get_session(session_id)
        if projection is None:
            raise SessionNotFound("Session not found")
        return projection.session

    def create(
        self,
        *,
        scenario_id: str,
        scenario_version: str,
        seed: int | None,
        idempotency_key: UUID,
        correlation_id: UUID,
    ) -> Session:
        session_id = self.identity(idempotency_key)
        observed_at, event_id = self.clock(), str(uuid4())
        request = WriteRequest(
            session_id,
            str(idempotency_key),
            "session.create",
            0,
            json.dumps(
                {"scenario_id": scenario_id, "scenario_version": scenario_version, "seed": seed},
                sort_keys=True,
            ),
        )

        def build(sequence: int) -> tuple[DomainEvent, ...]:
            session = create_session(
                CreateSessionRequest(
                    session_id,
                    scenario_id,
                    scenario_version,
                    self.default_seed if seed is None else seed,
                    self.versions,
                    observed_at,
                )
            )
            return (self.events.created(session, self.context(sequence, correlation_id, event_id)),)

        return self.store.commit(request, build).projection.session

    def transition(
        self,
        session_id: str,
        target: SessionLifecycleState,
        *,
        expected_version: int,
        idempotency_key: UUID,
        correlation_id: UUID,
        simulation_time: float | None = None,
        failure: SessionFailure | None = None,
        required_state: SessionLifecycleState | None = None,
    ) -> Session:
        # Validate the loaded version under the write lock, after retry lookup.
        current = self.get(session_id)
        observed_at, event_id = self.clock(), str(uuid4())
        request = WriteRequest(
            session_id,
            str(idempotency_key),
            "session.transition",
            expected_version,
            json.dumps(
                {
                    "target": target.value,
                    "required_state": required_state,
                    "simulation_time": simulation_time,
                    "failure": asdict(failure) if failure else None,
                },
                sort_keys=True,
            ),
        )

        def build(sequence: int) -> tuple[DomainEvent, ...]:
            if required_state is not None and current.lifecycle_state != required_state:
                raise SessionTransitionError(
                    TransitionErrorCode.ILLEGAL_TRANSITION, "Illegal lifecycle command"
                )
            result = transition_session(
                current,
                TransitionRequest(
                    target,
                    observed_at,
                    simulation_time,
                    failure,
                ),
            )
            return (
                self.events.transitioned(
                    result.fact, self.context(sequence, correlation_id, event_id)
                ),
            )

        return self.store.commit(request, build).projection.session
