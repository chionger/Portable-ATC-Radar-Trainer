"""Event factory and repository ports; atomic persistence is deferred to FP-005/006."""

from dataclasses import dataclass
from typing import Protocol

from packages.domain.events import (
    DomainEvent,
    EventActor,
    EventSource,
    EventType,
    SessionCreatedPayload,
    SessionTransitionPayload,
    transition_event_type,
)
from packages.domain.session import Session, SessionLifecycleState, SessionTransitionFact


@dataclass(frozen=True, slots=True)
class EventContext:
    event_id: str
    sequence: int
    previous_sequence: int
    actor: EventActor
    source: EventSource
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.previous_sequence) is not int or self.previous_sequence < 0:
            raise ValueError("previous sequence must be a non-negative integer")
        if type(self.sequence) is not int or self.sequence != self.previous_sequence + 1:
            raise ValueError("sequence must follow the observed last sequence")


class EventFactory(Protocol):
    def created(self, session: Session, context: EventContext) -> DomainEvent: ...
    def transitioned(self, fact: SessionTransitionFact, context: EventContext) -> DomainEvent: ...


class SessionEventFactory:
    def created(self, session: Session, context: EventContext) -> DomainEvent:
        if session.lifecycle_state != SessionLifecycleState.CREATED:
            raise ValueError("creation requires a CREATED session")
        return DomainEvent(
            event_id=context.event_id,
            event_type=EventType.SESSION_CREATED,
            session_id=session.session_id,
            sequence=context.sequence,
            sim_time=session.simulation_time,
            wall_time_utc=session.created_at,
            actor=context.actor,
            source=context.source,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            payload=SessionCreatedPayload(
                scenario_id=session.scenario_id,
                scenario_version=session.scenario_version,
                seed=session.seed,
                versions=session.versions,
            ),
        )

    def transitioned(self, fact: SessionTransitionFact, context: EventContext) -> DomainEvent:
        payload = SessionTransitionPayload(
            previous_state=fact.previous_state,
            state=fact.state,
            previous_version=fact.previous_version,
            version=fact.version,
            outcome=fact.outcome,
            failure=fact.failure,
        )
        return DomainEvent(
            event_id=context.event_id,
            event_type=transition_event_type(payload),
            session_id=fact.session_id,
            sequence=context.sequence,
            sim_time=fact.simulation_time,
            wall_time_utc=fact.occurred_at,
            actor=context.actor,
            source=context.source,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            payload=payload,
        )


def validate_append_batch(
    session_id: str, expected_last_sequence: int, events: tuple[DomainEvent, ...]
) -> None:
    """Local preconditions only; the repository must atomically check its actual tail."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required")
    if type(expected_last_sequence) is not int or expected_last_sequence < 0:
        raise ValueError("expected last sequence must be a non-negative integer")
    if not isinstance(events, tuple) or not events:
        raise ValueError("append requires a non-empty immutable batch")
    identities: set[str] = set()
    for sequence, event in enumerate(events, expected_last_sequence + 1):
        if not isinstance(event, DomainEvent):
            raise ValueError("batch contains an invalid event")
        if event.session_id != session_id or event.sequence != sequence:
            raise ValueError("batch must contain contiguous events for one session")
        if event.event_id in identities:
            raise ValueError("duplicate event identity in batch")
        identities.add(event.event_id)


class EventRepository(Protocol):
    """Append immutable records before projection/publication; never rewrite history.

    Implementations must atomically compare the session tail with expected_last_sequence,
    enforce unique event IDs and (session_id, sequence), then durably append the entire
    validated batch or nothing. Reads return ascending sequence strictly after the cursor.
    Projection consistency/recovery is gated by FP-005, not implemented by this port.
    """

    def append(
        self, session_id: str, expected_last_sequence: int, events: tuple[DomainEvent, ...]
    ) -> None: ...
    def read_after(self, session_id: str, sequence: int) -> tuple[DomainEvent, ...]: ...
