import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.application.events import (
    EventContext,
    EventFactory,
    SessionEventFactory,
    validate_append_batch,
)
from packages.domain.events import (
    CANONICAL_PROJECTION_VERSION,
    EVENT_REGISTRY,
    DomainEvent,
    EventActor,
    EventRegistry,
    EventSchema,
    EventSource,
    EventType,
    SessionCreatedPayload,
)
from packages.domain.session import (
    CreateSessionRequest,
    SessionFailure,
    SessionLifecycleState,
    SessionVersions,
    TransitionRequest,
    create_session,
    transition_session,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "events"
NOW = datetime(2026, 9, 17, tzinfo=UTC)
FACTORY: EventFactory = SessionEventFactory()


def session():
    return create_session(
        CreateSessionRequest(
            "session-1",
            "approach",
            "1",
            42,
            SessionVersions("1.0", "a" * 64, "rules-1", "schema-1"),
            NOW,
        )
    )


def context(sequence=1):
    return EventContext(
        f"event-{sequence}",
        sequence,
        sequence - 1,
        EventActor(kind="system", identifier="actor-1"),
        EventSource(component="session-service", version="1"),
        "correlation-1",
    )


def created():
    return FACTORY.created(session(), context())


def initialising():
    result = transition_session(
        session(), TransitionRequest(SessionLifecycleState.INITIALISING, NOW)
    )
    return FACTORY.transitioned(result.fact, context(2))


def test_catalogue_matches_architecture_and_has_no_ticks():
    baseline = (
        Path(__file__).parents[2]
        / "docs/architecture/baseline/ATC_Portable_Trainer_Phase1_Architecture_Baseline_v1.0.md"
    )
    import re

    section = baseline.read_text(encoding="utf-8").split("## 15.2 Minimum event catalogue")[1]
    names = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", section.split("## 15.3")[0]))
    assert len(names) == 47
    assert {entry.event_type.value for entry in EVENT_REGISTRY.entries} == names
    assert len([entry for entry in EVENT_REGISTRY.entries if entry.payload_type]) == 9
    assert "simulation.tick" not in names


@pytest.mark.parametrize(
    "name", [kind for kind in EventType if not kind.value.startswith("session.")]
)
def test_reserved_entries_cannot_emit_placeholder_payloads(name):
    raw = json.loads(created().model_dump_json())
    raw["event_type"] = name.value
    with pytest.raises(ValidationError, match="reserved"):
        DomainEvent.model_validate_json(json.dumps(raw))


def test_registry_is_immutable_and_rejects_duplicate_or_invalid_entries():
    entry = EVENT_REGISTRY.entries[0]
    with pytest.raises(ValueError, match="duplicate"):
        EventRegistry((entry, entry))
    with pytest.raises(ValueError):
        EventRegistry([entry])
    with pytest.raises(ValueError):
        EventSchema("ad.hoc", None)
    with pytest.raises(ValueError):
        EventSchema(EventType.SESSION_CREATED, None)
    with pytest.raises(ValueError):
        EventSchema(EventType.AUDIO_RECEIVED, SessionCreatedPayload)
    with pytest.raises(ValueError):
        EventSchema(EventType.SESSION_CREATED, SessionCreatedPayload, "2.0")
    with pytest.raises(ValueError):
        EventSchema(EventType.SESSION_CREATED, SessionCreatedPayload, projection_version="2.0")
    with pytest.raises(FrozenInstanceError):
        EVENT_REGISTRY.entries = ()
    with pytest.raises(ValueError, match="unregistered"):
        EventRegistry(()).get(EventType.SESSION_CREATED)


def test_factory_emits_all_session_names_and_preserves_failure():
    current = session()
    names = {created().event_type}
    for index, target in enumerate(
        [
            SessionLifecycleState.INITIALISING,
            SessionLifecycleState.READY,
            SessionLifecycleState.RUNNING,
            SessionLifecycleState.PAUSED,
            SessionLifecycleState.RUNNING,
        ],
        2,
    ):
        result = transition_session(current, TransitionRequest(target, NOW))
        event = FACTORY.transitioned(result.fact, context(index))
        names.add(event.event_type)
        assert DomainEvent.model_validate_json(event.model_dump_json()) == event
        current = result.session
    for target in [
        SessionLifecycleState.COMPLETED,
        SessionLifecycleState.STOPPED,
        SessionLifecycleState.FAILED,
    ]:
        failure = (
            SessionFailure("adapter", "Unavailable")
            if target == SessionLifecycleState.FAILED
            else None
        )
        result = transition_session(current, TransitionRequest(target, NOW, failure=failure))
        event = FACTORY.transitioned(result.fact, context(7))
        names.add(event.event_type)
        assert event.payload.failure == failure
        assert DomainEvent.model_validate_json(event.model_dump_json()) == event
    assert names == {kind for kind in EventType if kind.value.startswith("session.")}


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": " "},
        {"session_id": ""},
        {"correlation_id": ""},
        {"causation_id": ""},
        {"event_type": "simulation.tick"},
        {"event_type": "ad.hoc"},
        {"schema_version": "2.0"},
        {"schema_version": "1.1"},
        {"schema_version": "garbage"},
        {"sequence": 0},
        {"sequence": True},
        {"sequence": "1"},
        {"sequence": 2},
        {"sim_time": -1},
        {"sim_time": 1},
        {"sim_time": True},
        {"sim_time": float("inf")},
        {"wall_time_utc": "2026-09-17T00:00:00"},
        {"actor": {"kind": "unknown"}},
        {"source": {"component": "", "version": "1"}},
        {"unexpected": 1},
        {"payload": {}},
    ],
)
def test_envelope_rejects_invalid_contract(changes):
    raw = json.loads(created().model_dump_json())
    raw.update(changes)
    with pytest.raises(ValidationError):
        DomainEvent.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "changes",
    [
        {"previous_state": "FAILED"},
        {"state": "RUNNING"},
        {"version": 4},
        {"previous_version": 2, "version": 3},
        {"outcome": "COMPLETED"},
        {"failure": {"category": "oops", "reason": "wrong event"}},
        {"version": True},
    ],
)
def test_transition_payload_validation(changes):
    raw = json.loads(initialising().model_dump_json())
    raw["payload"].update(changes)
    with pytest.raises(ValidationError):
        DomainEvent.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "changes", [{"event_type": "session.ready"}, {"sequence": 1}, {"sim_time": 1}]
)
def test_transition_envelope_cross_checks(changes):
    raw = json.loads(initialising().model_dump_json())
    raw.update(changes)
    with pytest.raises(ValidationError):
        DomainEvent.model_validate_json(json.dumps(raw))


def test_failure_payload_requires_nonblank_details():
    fact = transition_session(
        session(),
        TransitionRequest(
            SessionLifecycleState.FAILED, NOW, failure=SessionFailure("init", "missing")
        ),
    ).fact
    event = FACTORY.transitioned(fact, context(2))
    for failure in [None, {"category": "", "reason": "missing"}]:
        raw = json.loads(event.model_dump_json())
        raw["payload"]["failure"] = failure
        with pytest.raises(ValidationError):
            DomainEvent.model_validate_json(json.dumps(raw))


def test_nested_immutability_and_projection_copy():
    event = created()
    for obj, field, value in [
        (event, "sequence", 10),
        (event.actor, "kind", "instructor"),
        (event.source, "version", "changed"),
        (event.payload, "seed", 9),
    ]:
        with pytest.raises(ValidationError):
            setattr(obj, field, value)
    with pytest.raises(FrozenInstanceError):
        event.payload.versions.rule_version = "changed"
    projection = event.canonical_projection()
    projection["payload"]["seed"] = 9
    assert event.payload.seed == 42
    assert event.canonical_projection()["payload"]["seed"] == 42


def test_canonical_equality_ignores_identity_and_wall_time():
    first = created()
    raw = json.loads(first.model_dump_json())
    raw.update(
        event_id="another",
        session_id="other-session",
        correlation_id="other-correlation",
        causation_id="other-cause",
        wall_time_utc="2026-10-01T12:00:00+08:00",
    )
    raw["actor"]["identifier"] = "other-person"
    second = DomainEvent.model_validate_json(json.dumps(raw))
    assert second.wall_time_utc.hour == 4 and second.wall_time_utc.tzinfo is UTC
    assert first != second
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_projection()["projection_version"] == CANONICAL_PROJECTION_VERSION


@pytest.mark.parametrize("field,value", [("seed", 7), ("scenario_version", "2")])
def test_canonical_projection_retains_semantics(field, value):
    first = created()
    raw = json.loads(first.model_dump_json())
    raw["payload"][field] = value
    assert (
        first.canonical_json() != DomainEvent.model_validate_json(json.dumps(raw)).canonical_json()
    )


def test_sequence_preconditions_and_atomic_repository_batch():
    events = (created(), initialising())
    validate_append_batch("session-1", 0, events)
    validate_append_batch("session-1", 1, events[1:])
    for sequence, previous in [(1, 1), (3, 1), (0, -1), (True, 0), (1, False)]:
        with pytest.raises(ValueError):
            replace(context(), sequence=sequence, previous_sequence=previous)
    for sid, tail, batch in [
        ("other", 0, events),
        ("session-1", 1, events),
        ("session-1", 0, events[::-1]),
        ("session-1", 0, ()),
        ("session-1", -1, events),
        ("session-1", True, events),
        ("", 0, events),
        ("session-1", 0, list(events)),
    ]:
        with pytest.raises(ValueError):
            validate_append_batch(sid, tail, batch)
    second = initialising().model_dump()
    second["event_id"] = events[0].event_id
    with pytest.raises(ValueError, match="duplicate"):
        validate_append_batch("session-1", 0, (events[0], DomainEvent.model_validate(second)))


def test_factory_rejects_inconsistent_inputs():
    result = transition_session(
        session(), TransitionRequest(SessionLifecycleState.INITIALISING, NOW)
    )
    with pytest.raises(ValueError):
        FACTORY.created(result.session, context())
    with pytest.raises(ValueError):
        FACTORY.created(session(), context(2))
    with pytest.raises(ValueError):
        FACTORY.transitioned(result.fact, context())
    with pytest.raises(ValueError):
        FACTORY.transitioned(replace(result.fact, version=99), context(2))


def test_event_sequence_can_exceed_but_not_precede_session_version():
    raw = json.loads(initialising().model_dump_json())
    raw["sequence"] = 10
    event = DomainEvent.model_validate_json(json.dumps(raw))
    assert event.sequence == 10 and event.payload.version == 2
    raw["payload"].update(
        previous_state="INITIALISING", state="READY", previous_version=2, version=3
    )
    raw["event_type"] = "session.ready"
    raw["sequence"] = 2
    with pytest.raises(ValidationError, match="sequence cannot precede"):
        DomainEvent.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 3},
        {"actor": {"kind": "instructor"}},
        {"source": {"component": "other", "version": "1"}},
    ],
)
def test_projection_retains_order_actor_kind_and_source(changes):
    event = initialising()
    raw = json.loads(event.model_dump_json())
    raw.update(changes)
    assert (
        DomainEvent.model_validate_json(json.dumps(raw)).canonical_json() != event.canonical_json()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": True},
        {"version": True},
        {"versions": {}},
        {"scenario_id": " "},
        {"unknown": "extension"},
    ],
)
def test_creation_payload_validation(changes):
    raw = json.loads(created().model_dump_json())
    raw["payload"].update(changes)
    with pytest.raises(ValidationError):
        DomainEvent.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "name",
    [
        "created",
        "initialising",
        "ready",
        "started",
        "paused",
        "resumed",
        "completed",
        "stopped",
        "failed",
    ],
)
def test_stored_json_contract_round_trip(name):
    raw = (FIXTURES / f"session.{name}.json").read_text(encoding="utf-8")
    event = DomainEvent.model_validate_json(raw)
    assert event.event_type.value == f"session.{name}"
    assert json.loads(event.model_dump_json()) == json.loads(raw)
    assert DomainEvent.model_validate_json(event.model_dump_json()) == event


def test_published_schema_and_catalogue_are_current():
    schema = json.loads((FIXTURES / "domain-event.schema.json").read_text(encoding="utf-8"))
    assert schema == DomainEvent.model_json_schema()
    catalogue = json.loads((FIXTURES / "catalogue.json").read_text(encoding="utf-8"))
    assert catalogue == [
        {
            "event_type": entry.event_type.value,
            "schema_version": entry.schema_version,
            "projection_version": entry.projection_version,
            "status": "implemented" if entry.payload_type else "reserved",
        }
        for entry in EVENT_REGISTRY.entries
    ]
