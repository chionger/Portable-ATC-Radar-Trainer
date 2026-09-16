"""Immutable live-session state and pure lifecycle policy (FP-003)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum


class SessionLifecycleState(StrEnum):
    CREATED = "CREATED"
    INITIALISING = "INITIALISING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class SessionOutcome(StrEnum):
    """Termination disposition, not a training score or competency assessment."""

    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _simulation_time(value: float) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("simulation_time must be finite non-negative seconds")
    return float(value)


@dataclass(frozen=True, slots=True)
class VersionReference:
    name: str
    version: str

    def __post_init__(self) -> None:
        _text(self.name, "name")
        _text(self.version, "version")


@dataclass(frozen=True, slots=True)
class SessionVersions:
    configuration_version: str
    configuration_hash: str
    rule_version: str
    schema_version: str
    adapters: tuple[VersionReference, ...] = ()
    models: tuple[VersionReference, ...] = ()

    def __post_init__(self) -> None:
        for field in ("configuration_version", "rule_version", "schema_version"):
            _text(getattr(self, field), field)
        if not isinstance(self.configuration_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.configuration_hash
        ):
            raise ValueError("configuration_hash must be a lowercase SHA-256 identifier")
        for group in (self.adapters, self.models):
            if not isinstance(group, tuple) or any(
                not isinstance(item, VersionReference) for item in group
            ):
                raise ValueError("version references must be an immutable tuple")
            if len({item.name for item in group}) != len(group):
                raise ValueError("version reference names must be unique within each group")


@dataclass(frozen=True, slots=True)
class SessionFailure:
    category: str
    reason: str

    def __post_init__(self) -> None:
        _text(self.category, "failure.category")
        _text(self.reason, "failure.reason")


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    scenario_id: str
    scenario_version: str
    seed: int
    versions: SessionVersions
    created_at: datetime
    updated_at: datetime
    lifecycle_state: SessionLifecycleState = SessionLifecycleState.CREATED
    version: int = 1
    simulation_time: float = 0.0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    outcome: SessionOutcome | None = None
    failure: SessionFailure | None = None

    def __post_init__(self) -> None:
        for field in ("session_id", "scenario_id", "scenario_version"):
            _text(getattr(self, field), field)
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.versions, SessionVersions):
            raise ValueError("versions must be SessionVersions")
        if not isinstance(self.lifecycle_state, SessionLifecycleState):
            raise ValueError("lifecycle_state must be SessionLifecycleState")
        object.__setattr__(self, "simulation_time", _simulation_time(self.simulation_time))
        for field in ("created_at", "updated_at", "started_at", "ended_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _utc(value))
            elif field in ("created_at", "updated_at"):
                raise ValueError(f"{field} is required")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at precedes creation")
        if self.started_at is not None and not (
            self.created_at <= self.started_at <= self.updated_at
        ):
            raise ValueError("started_at is outside the session timeline")
        state = self.lifecycle_state
        if (
            state
            in {
                SessionLifecycleState.CREATED,
                SessionLifecycleState.INITIALISING,
                SessionLifecycleState.READY,
            }
            and self.started_at is not None
        ):
            raise ValueError("pre-running sessions must not have started_at")
        if state in {
            SessionLifecycleState.RUNNING,
            SessionLifecycleState.PAUSED,
            SessionLifecycleState.COMPLETED,
            SessionLifecycleState.STOPPED,
        }:
            if self.started_at is None:
                raise ValueError("started_at is required after starting")
        if self.started_at is None and self.simulation_time != 0:
            raise ValueError("simulation time cannot advance before starting")
        if state == SessionLifecycleState.CREATED and (
            self.version != 1 or self.updated_at != self.created_at
        ):
            raise ValueError("created state must retain its initial version and timestamp")
        terminal = state in {
            SessionLifecycleState.COMPLETED,
            SessionLifecycleState.STOPPED,
            SessionLifecycleState.FAILED,
        }
        if terminal:
            if self.ended_at != self.updated_at:
                raise ValueError("terminal ended_at must equal updated_at")
            if not isinstance(self.outcome, SessionOutcome) or self.outcome.value != state.value:
                raise ValueError("terminal outcome must match lifecycle state")
        elif self.ended_at is not None or self.outcome is not None:
            raise ValueError("live sessions must not have ended_at or an outcome")
        if state == SessionLifecycleState.FAILED:
            if not isinstance(self.failure, SessionFailure):
                raise ValueError("failed sessions require failure category and reason")
        elif self.failure is not None:
            raise ValueError("failure information is valid only for failed sessions")


@dataclass(frozen=True, slots=True)
class CreateSessionRequest:
    session_id: str
    scenario_id: str
    scenario_version: str
    seed: int
    versions: SessionVersions
    created_at: datetime


def create_session(request: CreateSessionRequest) -> Session:
    """Caller supplies identity, pinned versions and wall time; no adapters are invoked."""
    return Session(
        session_id=request.session_id,
        scenario_id=request.scenario_id,
        scenario_version=request.scenario_version,
        seed=request.seed,
        versions=request.versions,
        created_at=request.created_at,
        updated_at=request.created_at,
    )


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    target: SessionLifecycleState
    occurred_at: datetime
    simulation_time: float | None = None
    failure: SessionFailure | None = None


class TransitionErrorCode(StrEnum):
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_SIMULATION_TIME = "INVALID_SIMULATION_TIME"
    INVALID_FAILURE = "INVALID_FAILURE"


class SessionTransitionError(ValueError):
    def __init__(self, code: TransitionErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SessionTransitionFact:
    """Unpersisted transition fact; FP-004 owns event envelopes and sequencing."""

    session_id: str
    previous_state: SessionLifecycleState
    state: SessionLifecycleState
    previous_version: int
    version: int
    occurred_at: datetime
    simulation_time: float
    outcome: SessionOutcome | None
    failure: SessionFailure | None


@dataclass(frozen=True, slots=True)
class TransitionResult:
    session: Session
    fact: SessionTransitionFact


def allowed_transitions(state: SessionLifecycleState) -> frozenset[SessionLifecycleState]:
    match state:
        case SessionLifecycleState.CREATED:
            return frozenset({SessionLifecycleState.INITIALISING, SessionLifecycleState.FAILED})
        case SessionLifecycleState.INITIALISING:
            return frozenset({SessionLifecycleState.READY, SessionLifecycleState.FAILED})
        case SessionLifecycleState.READY:
            return frozenset({SessionLifecycleState.RUNNING, SessionLifecycleState.FAILED})
        case SessionLifecycleState.RUNNING | SessionLifecycleState.PAUSED:
            other = (
                SessionLifecycleState.PAUSED
                if state == SessionLifecycleState.RUNNING
                else SessionLifecycleState.RUNNING
            )
            return frozenset(
                {
                    other,
                    SessionLifecycleState.COMPLETED,
                    SessionLifecycleState.STOPPED,
                    SessionLifecycleState.FAILED,
                }
            )
        case _:
            return frozenset()


def transition_session(session: Session, request: TransitionRequest) -> TransitionResult:
    target = request.target
    if not isinstance(target, SessionLifecycleState) or target not in allowed_transitions(
        session.lifecycle_state
    ):
        raise SessionTransitionError(
            TransitionErrorCode.ILLEGAL_TRANSITION, "Illegal live session transition"
        )
    try:
        occurred_at = _utc(request.occurred_at)
        if occurred_at < session.updated_at:
            raise ValueError("transition timestamp precedes previous transition")
    except ValueError as error:
        raise SessionTransitionError(TransitionErrorCode.INVALID_TIMESTAMP, str(error)) from None
    try:
        simulation_time = _simulation_time(
            session.simulation_time if request.simulation_time is None else request.simulation_time
        )
        if simulation_time < session.simulation_time:
            raise ValueError("simulation_time cannot move backwards")
        if session.lifecycle_state != SessionLifecycleState.RUNNING and (
            simulation_time != session.simulation_time
        ):
            raise ValueError("simulation_time can advance only from RUNNING")
    except ValueError as error:
        raise SessionTransitionError(
            TransitionErrorCode.INVALID_SIMULATION_TIME, str(error)
        ) from None
    if target == SessionLifecycleState.FAILED:
        if not isinstance(request.failure, SessionFailure):
            raise SessionTransitionError(
                TransitionErrorCode.INVALID_FAILURE, "Failure category and reason are required"
            )
    elif request.failure is not None:
        raise SessionTransitionError(
            TransitionErrorCode.INVALID_FAILURE, "Failure details require a FAILED transition"
        )
    terminal = target in {
        SessionLifecycleState.COMPLETED,
        SessionLifecycleState.STOPPED,
        SessionLifecycleState.FAILED,
    }
    updated = replace(
        session,
        lifecycle_state=target,
        version=session.version + 1,
        updated_at=occurred_at,
        simulation_time=simulation_time,
        started_at=(
            occurred_at
            if session.lifecycle_state == SessionLifecycleState.READY
            and target == SessionLifecycleState.RUNNING
            else session.started_at
        ),
        ended_at=occurred_at if terminal else None,
        outcome=SessionOutcome(target.value) if terminal else None,
        failure=request.failure,
    )
    return TransitionResult(
        session=updated,
        fact=SessionTransitionFact(
            session_id=updated.session_id,
            previous_state=session.lifecycle_state,
            state=target,
            previous_version=session.version,
            version=updated.version,
            occurred_at=occurred_at,
            simulation_time=simulation_time,
            outcome=updated.outcome,
            failure=updated.failure,
        ),
    )
