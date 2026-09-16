from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import product

import pytest

from packages.domain.session import (
    CreateSessionRequest,
    SessionFailure,
    SessionOutcome,
    SessionTransitionError,
    SessionVersions,
    TransitionRequest,
    VersionReference,
    allowed_transitions,
    create_session,
    transition_session,
)
from packages.domain.session import (
    SessionLifecycleState as State,
)
from packages.domain.session import (
    TransitionErrorCode as Code,
)

T0 = datetime(2026, 9, 16, tzinfo=UTC)
PINS = SessionVersions(
    "1",
    "a" * 64,
    "rules-1",
    "schema-1",
    (VersionReference("simulator", "1"),),
    (VersionReference("recognizer", "2"),),
)
FAILURE = SessionFailure("initialization", "Scenario unavailable")
# Independent baseline table: 14 legal edges, 50 rejected edges (including self).
LEGAL = {
    ("CREATED", "INITIALISING"),
    ("CREATED", "FAILED"),
    ("INITIALISING", "READY"),
    ("INITIALISING", "FAILED"),
    ("READY", "RUNNING"),
    ("READY", "FAILED"),
    ("RUNNING", "PAUSED"),
    ("RUNNING", "COMPLETED"),
    ("RUNNING", "STOPPED"),
    ("RUNNING", "FAILED"),
    ("PAUSED", "RUNNING"),
    ("PAUSED", "COMPLETED"),
    ("PAUSED", "STOPPED"),
    ("PAUSED", "FAILED"),
}


def initial():
    return create_session(CreateSessionRequest("s-1", "approach", "3", 42, PINS, T0))


def in_state(state):
    session = initial()
    path = [State.INITIALISING, State.READY, State.RUNNING, State.PAUSED]
    if state in (State.COMPLETED, State.STOPPED, State.FAILED):
        path = path[:3] + [state]
    if state == State.CREATED:
        return session
    for target in path:
        session = transition_session(
            session,
            TransitionRequest(
                target,
                session.updated_at + timedelta(seconds=1),
                failure=FAILURE if target == State.FAILED else None,
            ),
        ).session
        if target == state:
            return session
    raise AssertionError(state)


@pytest.mark.parametrize(
    "source,target", list(product(State, repeat=2)), ids=lambda value: value.value
)
def test_complete_transition_matrix(source, target):
    original = in_state(source)
    snapshot = asdict(original)
    occurred = original.updated_at + timedelta(seconds=10)
    request = TransitionRequest(
        target, occurred, failure=FAILURE if target == State.FAILED else None
    )
    if (source.value, target.value) not in LEGAL:
        with pytest.raises(SessionTransitionError) as caught:
            transition_session(original, request)
        assert caught.value.code == Code.ILLEGAL_TRANSITION
        assert target not in allowed_transitions(source)
    else:
        result = transition_session(original, request)
        updated, fact = result.session, result.fact
        assert updated is not original
        assert updated.lifecycle_state == target
        assert updated.version == original.version + 1
        assert updated.versions is original.versions
        assert (
            updated.session_id,
            updated.scenario_id,
            updated.scenario_version,
            updated.seed,
        ) == ("s-1", "approach", "3", 42)
        assert updated.created_at == T0
        assert updated.updated_at == occurred
        assert updated.simulation_time == original.simulation_time
        assert updated.started_at == (
            occurred if source == State.READY and target == State.RUNNING else original.started_at
        )
        terminal = target in (State.COMPLETED, State.STOPPED, State.FAILED)
        assert updated.ended_at == (occurred if terminal else None)
        assert updated.outcome == (SessionOutcome(target.value) if terminal else None)
        assert updated.failure == request.failure
        assert (fact.previous_state, fact.state) == (source, target)
        assert (fact.previous_version, fact.version) == (original.version, updated.version)
        assert (fact.session_id, fact.occurred_at, fact.simulation_time) == (
            updated.session_id,
            occurred,
            updated.simulation_time,
        )
        assert (fact.outcome, fact.failure) == (updated.outcome, updated.failure)
        assert target in allowed_transitions(source)
    assert asdict(original) == snapshot


def test_creation_and_deep_immutability():
    session = initial()
    assert session.lifecycle_state == State.CREATED
    assert session.version == 1 and session.simulation_time == 0
    assert session.started_at is session.ended_at is session.outcome is session.failure is None
    for obj, field, value in [
        (session, "seed", 7),
        (session.versions, "rule_version", "changed"),
        (session.versions.models[0], "version", "changed"),
        (FAILURE, "reason", "changed"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    result = transition_session(session, TransitionRequest(State.FAILED, T0, failure=FAILURE))
    with pytest.raises(FrozenInstanceError):
        result.fact.version = 99
    with pytest.raises(FrozenInstanceError):
        result.session = session


@pytest.mark.parametrize(
    "source", [State.CREATED, State.INITIALISING, State.READY, State.RUNNING, State.PAUSED]
)
def test_failure_preserves_details_at_every_nonterminal_state(source):
    before = in_state(source)
    after = transition_session(
        before, TransitionRequest(State.FAILED, before.updated_at, failure=FAILURE)
    ).session
    assert after.failure is FAILURE
    assert after.started_at == before.started_at
    assert after.ended_at == before.updated_at
    assert after.outcome == SessionOutcome.FAILED


@pytest.mark.parametrize("timestamp", [T0 - timedelta(seconds=1), T0.replace(tzinfo=None), None])
def test_invalid_timestamps_are_typed_and_do_not_mutate(timestamp):
    session = initial()
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(session, TransitionRequest(State.INITIALISING, timestamp))
    assert caught.value.code == Code.INVALID_TIMESTAMP
    assert session == initial()


def test_clock_cannot_regress_after_creation():
    session = in_state(State.READY)
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(session, TransitionRequest(State.RUNNING, T0))
    assert caught.value.code == Code.INVALID_TIMESTAMP


def test_utc_normalization_equal_times_and_resume_preserve_start():
    offset = timezone(timedelta(hours=8))
    session = create_session(CreateSessionRequest("s", "x", "1", 0, PINS, T0.astimezone(offset)))
    assert session.created_at.tzinfo is UTC
    for state in [State.INITIALISING, State.READY, State.RUNNING, State.PAUSED, State.RUNNING]:
        session = transition_session(
            session, TransitionRequest(state, T0.astimezone(offset))
        ).session
    assert session.started_at == T0
    assert session.updated_at.tzinfo is UTC
    assert session.version == 6


def test_simulation_time_is_explicit_and_frozen_during_pause():
    running = in_state(State.RUNNING)
    paused = transition_session(
        running, TransitionRequest(State.PAUSED, T0 + timedelta(hours=1), simulation_time=12.5)
    ).session
    resumed = transition_session(
        paused, TransitionRequest(State.RUNNING, T0 + timedelta(hours=2))
    ).session
    completed = transition_session(
        resumed, TransitionRequest(State.COMPLETED, T0 + timedelta(hours=3), simulation_time=14.2)
    ).session
    assert resumed.simulation_time == 12.5
    assert completed.simulation_time == 14.2
    assert completed.started_at == running.started_at


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "1", 10**400])
def test_invalid_simulation_values_are_typed(value):
    session = in_state(State.RUNNING)
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(session, TransitionRequest(State.PAUSED, session.updated_at, value))
    assert caught.value.code == Code.INVALID_SIMULATION_TIME
    assert session.simulation_time == 0


@pytest.mark.parametrize("state", [State.CREATED, State.INITIALISING, State.READY, State.PAUSED])
def test_simulation_cannot_advance_when_not_running(state):
    session = in_state(state)
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(session, TransitionRequest(State.FAILED, session.updated_at, 1, FAILURE))
    assert caught.value.code == Code.INVALID_SIMULATION_TIME


def test_simulation_cannot_go_backwards():
    session = in_state(State.RUNNING)
    session = transition_session(
        session, TransitionRequest(State.PAUSED, session.updated_at, 5)
    ).session
    session = transition_session(
        session, TransitionRequest(State.RUNNING, session.updated_at)
    ).session
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(session, TransitionRequest(State.STOPPED, session.updated_at, 4))
    assert caught.value.code == Code.INVALID_SIMULATION_TIME


@pytest.mark.parametrize(
    "target,failure", [(State.FAILED, None), (State.FAILED, "oops"), (State.INITIALISING, FAILURE)]
)
def test_failure_metadata_is_required_only_for_failure(target, failure):
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(initial(), TransitionRequest(target, T0, failure=failure))
    assert caught.value.code == Code.INVALID_FAILURE


@pytest.mark.parametrize("target", ["REPLAY", "RUNNING", None])
def test_untyped_and_replay_targets_are_rejected(target):
    with pytest.raises(SessionTransitionError) as caught:
        transition_session(in_state(State.READY), TransitionRequest(target, T0))
    assert caught.value.code == Code.ILLEGAL_TRANSITION


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": " "},
        {"scenario_id": ""},
        {"scenario_version": ""},
        {"seed": -1},
        {"seed": True},
        {"version": 0},
        {"version": True},
        {"version": 2},
        {"versions": None},
        {"lifecycle_state": "CREATED"},
        {"simulation_time": 1},
        {"created_at": None},
        {"created_at": T0.replace(tzinfo=None)},
        {"updated_at": T0 - timedelta(seconds=1)},
        {"updated_at": T0 + timedelta(seconds=1)},
        {"started_at": T0},
        {"ended_at": T0},
        {"outcome": SessionOutcome.COMPLETED},
        {"failure": FAILURE},
        {"lifecycle_state": State.RUNNING},
    ],
)
def test_inconsistent_snapshots_are_rejected(changes):
    with pytest.raises(ValueError):
        replace(initial(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"ended_at": None},
        {"outcome": None},
        {"outcome": SessionOutcome.STOPPED},
        {"started_at": T0 - timedelta(seconds=1)},
        {"started_at": T0 + timedelta(days=1)},
        {"failure": FAILURE},
    ],
)
def test_terminal_snapshot_invariants(changes):
    with pytest.raises(ValueError):
        replace(in_state(State.COMPLETED), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"configuration_version": ""},
        {"configuration_hash": "not-a-hash"},
        {"rule_version": ""},
        {"schema_version": ""},
        {"models": []},
        {"adapters": ("wrong",)},
        {"models": (VersionReference("x", "1"), VersionReference("x", "2"))},
    ],
)
def test_invalid_version_pins_are_rejected(changes):
    with pytest.raises(ValueError):
        replace(PINS, **changes)


@pytest.mark.parametrize("category,reason", [("", "reason"), ("category", " ")])
def test_failure_requires_category_and_reason(category, reason):
    with pytest.raises(ValueError):
        SessionFailure(category, reason)
