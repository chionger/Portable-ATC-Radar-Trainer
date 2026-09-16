"""Stateless application boundary; durable orchestration is deferred to FP-008."""

from typing import Protocol

from packages.domain.session import (
    CreateSessionRequest,
    Session,
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
