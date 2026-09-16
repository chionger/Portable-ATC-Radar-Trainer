from datetime import UTC, datetime

import pytest

from packages.application.sessions import DomainSessionLifecycle, SessionLifecycle
from packages.domain.session import (
    CreateSessionRequest,
    SessionOutcome,
    SessionTransitionError,
    SessionVersions,
    TransitionRequest,
)
from packages.domain.session import (
    SessionLifecycleState as State,
)
from packages.infrastructure.configuration import load_settings


def test_application_boundary_pins_configuration_and_runs_lifecycle():
    settings = load_settings(environ={})
    service: SessionLifecycle = DomainSessionLifecycle()
    now = datetime(2026, 9, 16, tzinfo=UTC)
    pins = SessionVersions("1", settings.configuration_hash(), "rules-1", "schema-1")
    session = service.create(CreateSessionRequest("s-1", "scenario", "1", 42, pins, now))
    for target in (
        State.INITIALISING,
        State.READY,
        State.RUNNING,
        State.PAUSED,
        State.RUNNING,
        State.COMPLETED,
    ):
        result = service.transition(session, TransitionRequest(target, now))
        assert result.fact.previous_version == session.version
        session = result.session
    assert session.outcome == SessionOutcome.COMPLETED
    assert session.version == 7
    assert session.versions.configuration_hash == settings.configuration_hash()
    with pytest.raises(SessionTransitionError):
        service.transition(session, TransitionRequest(State.RUNNING, now))
    assert session.lifecycle_state == State.COMPLETED
    independent = service.create(CreateSessionRequest("s-2", "scenario", "1", 42, pins, now))
    assert independent.lifecycle_state == State.CREATED
    assert independent.version == 1
