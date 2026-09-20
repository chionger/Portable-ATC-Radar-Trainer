"""FP-010 domain matrix and durable atomic traffic effects, using synthetic data."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.application.sessions import DurableSessionService
from packages.application.traffic import TrafficService
from packages.application.traffic_projection import initial_traffic, project_traffic
from packages.domain.events import DomainEvent, EventActor, EventSource, EventType
from packages.domain.scenario import Scenario
from packages.domain.session import SessionLifecycleState as Phase
from packages.domain.session import SessionVersions
from packages.domain.traffic import (
    TRANSITIONS,
    Aerodrome,
    Aircraft,
    AircraftSpawnedPayload,
    AircraftState,
    AircraftStateChangedPayload,
    RunwayOccupancyChangedPayload,
    RunwayState,
    TrafficConflict,
    change_aircraft,
    occupancy,
    transition_traffic,
)
from packages.infrastructure.persistence.sqlite import (
    PersistenceError,
    SQLiteEventStore,
    WriteConflict,
)
from packages.infrastructure.scenarios import load_scenario

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 9, 19, tzinfo=UTC)
S = AircraftState
# Independent acceptance matrix: changing production policy must update reviewed evidence.
ALLOWED = {
    "PARKED": {"READY_TO_TAXI", "STOPPED"},
    "READY_TO_TAXI": {"TAXIING", "STOPPED"},
    "TAXIING": {"HOLDING", "PARKED", "STOPPED"},
    "HOLDING": {"TAXIING", "LINED_UP", "STOPPED"},
    "LINED_UP": {"TAKEOFF_ROLL", "VACATING", "STOPPED"},
    "TAKEOFF_ROLL": {"AIRBORNE", "STOPPED"},
    "AIRBORNE": {"INBOUND"},
    "INBOUND": {"FINAL", "AIRBORNE"},
    "FINAL": {"LANDING_ROLL", "AIRBORNE"},
    "LANDING_ROLL": {"VACATING", "STOPPED"},
    "VACATING": {"TAXIING", "STOPPED"},
    "STOPPED": set(),
}


def scenario():
    return load_scenario((FIXTURES / "scenarios/reference.yaml").read_bytes())


def aircraft(state):
    base = initial_traffic(scenario()).aircraft[0]
    return Aircraft.model_validate(
        base.model_dump()
        | {
            "state": state,
            "holding_point_id": "hold-a" if state == S.HOLDING else None,
            "occupied_runway_id": "runway-09"
            if state in {S.LINED_UP, S.TAKEOFF_ROLL, S.LANDING_ROLL, S.VACATING}
            else None,
        }
    )


@pytest.mark.parametrize("before", list(S))
@pytest.mark.parametrize("target", list(S))
def test_complete_transition_matrix(before, target):
    original = aircraft(before)
    saved = original.model_dump_json()
    if target.value in ALLOWED[before.value]:
        updated = change_aircraft(
            original,
            target,
            expected_version=1,
            holding_point_id="hold-a" if target == S.HOLDING else None,
        )
        assert updated.version == 2 and updated.state == target
        assert updated.position == original.position and updated.route == original.route
    else:
        with pytest.raises(TrafficConflict, match="illegal"):
            change_aircraft(original, target, expected_version=1)
    assert original.model_dump_json() == saved


def test_policy_and_nested_state_are_immutable():
    with pytest.raises(TypeError):
        TRANSITIONS[S.STOPPED] = frozenset({S.TAXIING})
    traffic = initial_traffic(scenario())
    with pytest.raises(ValidationError):
        traffic.aircraft[0].state = S.STOPPED
    with pytest.raises(ValidationError):
        traffic.aerodrome.geometry.runways[0].width_m = 12.0


def test_reference_mapping_preserves_geometry_and_identity():
    source = scenario()
    traffic = initial_traffic(source)
    item = traffic.aircraft[0]
    assert traffic.aerodrome.geometry == source.geometry
    assert item.aircraft_id == source.entities[0].id
    assert item.callsign == source.entities[0].callsign
    assert item.route == source.entities[0].route and item.position == source.entities[0].position
    assert item.state == S.PARKED and item.version == 1
    assert item.assigned_runway_id == "runway-09"
    assert item.clearance_state == "NONE" and item.response_state == "IDLE"
    assert item.ground_speed_kt == item.altitude_ft == item.heading_deg == 0
    assert traffic.aerodrome.runways[0].version == 1
    assert not traffic.aerodrome.runways[0].occupied


@pytest.mark.parametrize("state", ["TAXIING", "HOLDING", "INBOUND", "FINAL"])
def test_initial_states_remain_distinct(state):
    raw = scenario().model_dump(mode="json")
    raw["entities"][0]["state"] = state
    if state == "HOLDING":
        raw["entities"][0]["position"] = raw["geometry"]["holding_points"][0]["position"]
    traffic = initial_traffic(Scenario.model_validate_json(json.dumps(raw)))
    assert traffic.aircraft[0].state.value == state
    assert traffic.aircraft[0].holding_point_id == ("hold-a" if state == "HOLDING" else None)


def test_holding_mapping_requires_unique_matching_geometry():
    raw = scenario().model_dump(mode="json")
    raw["entities"][0]["state"] = "HOLDING"
    with pytest.raises(ValueError, match="matching holding"):
        initial_traffic(Scenario.model_validate_json(json.dumps(raw)))
    raw["entities"][0]["position"] = raw["geometry"]["holding_points"][0]["position"]
    raw["geometry"]["holding_points"].append(
        raw["geometry"]["holding_points"][0] | {"id": "hold-b"}
    )
    raw["entities"][0]["route"].append("hold-b")
    with pytest.raises(ValueError, match="matching holding"):
        initial_traffic(Scenario.model_validate_json(json.dumps(raw)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("heading_deg", 360.0),
        ("ground_speed_kt", -1.0),
        ("altitude_ft", float("nan")),
        ("version", True),
        ("route_progress", 4),
        ("holding_point_id", "hold-a"),
        ("clearance_state", "ACTIVE"),
        ("clearance_id", "clearance-1"),
        ("occupied_runway_id", "runway-09"),
    ],
)
def test_aircraft_contract_rejects_incoherent_values(field, value):
    with pytest.raises(ValueError):
        Aircraft.model_validate(aircraft(S.PARKED).model_dump() | {field: value})


@pytest.mark.parametrize("fault", ["duplicate", "hold_reference", "runway_geometry"])
def test_aerodrome_rejects_invalid_geometry(fault):
    raw = initial_traffic(scenario()).aerodrome.model_dump(mode="json")
    if fault == "duplicate":
        raw["geometry"]["runways"].append(raw["geometry"]["runways"][0])
    elif fault == "hold_reference":
        raw["geometry"]["holding_points"][0]["taxiway_id"] = "missing"
    else:
        raw["runways"][0]["geometry"]["width_m"] = 40
    with pytest.raises(ValueError):
        Aerodrome.model_validate_json(json.dumps(raw))


def test_membership_is_idempotent_versioned_and_preserves_other_aircraft():
    empty = initial_traffic(scenario()).aerodrome.runways[0]
    first = occupancy(empty, "b", True, 1)
    assert occupancy(first, "b", True, 2) is first
    both = occupancy(first, "a", True, 2)
    assert both.occupants == ("a", "b") and both.version == 3
    removed = occupancy(both, "b", False, 3)
    assert removed.occupants == ("a",) and removed.version == 4
    assert occupancy(removed, "b", False, 4) is removed
    with pytest.raises(TrafficConflict):
        occupancy(removed, "a", True, 3)
    assert empty.occupants == () and empty.version == 1


def test_closed_runway_blocks_entry_but_allows_removal():
    runway = initial_traffic(scenario()).aerodrome.runways[0]
    closed = RunwayState.model_validate(runway.model_dump() | {"operational_status": "CLOSED"})
    with pytest.raises(TrafficConflict, match="closed"):
        occupancy(closed, "a", True, 1)
    occupied = RunwayState.model_validate(closed.model_dump() | {"occupants": ("a",)})
    assert not occupancy(occupied, "a", False, 1).occupied


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expected_version": 0},
        {"expected_version": True},
        {"expected_version": 1, "expected_runway_version": True},
        {"expected_version": 1, "expected_runway_version": 9},
        {"expected_version": 1, "runway_id": "missing"},
    ],
)
def test_transition_conflicts_leave_input_unchanged(kwargs):
    traffic = initial_traffic(scenario())
    saved = traffic.model_dump_json()
    with pytest.raises(ValueError):
        transition_traffic(traffic, "aircraft-1", S.READY_TO_TAXI, **kwargs)
    assert traffic.model_dump_json() == saved


def step(traffic, target, **kwargs):
    return transition_traffic(
        traffic, "aircraft-1", target, expected_version=traffic.aircraft[0].version, **kwargs
    )


def at_hold():
    traffic = initial_traffic(scenario())
    for state in (S.READY_TO_TAXI, S.TAXIING):
        traffic, _ = step(traffic, state)
    return step(traffic, S.HOLDING, holding_point_id="hold-a")[0]


def test_departure_arrival_and_vacating_occupancy_sequence():
    traffic = at_hold()
    for state, members, count in [
        (S.LINED_UP, ("aircraft-1",), 2),
        (S.TAKEOFF_ROLL, ("aircraft-1",), 1),
        (S.AIRBORNE, (), 2),
        (S.INBOUND, (), 1),
        (S.FINAL, (), 1),
        (S.AIRBORNE, (), 1),
        (S.INBOUND, (), 1),
        (S.FINAL, (), 1),
        (S.LANDING_ROLL, ("aircraft-1",), 2),
        (S.VACATING, ("aircraft-1",), 1),
        (S.TAXIING, (), 2),
        (S.PARKED, (), 1),
    ]:
        traffic, facts = step(
            traffic, state, expected_runway_version=traffic.aerodrome.runways[0].version
        )
        assert traffic.aerodrome.runways[0].occupants == members
        assert len(facts) == count
    assert traffic.aerodrome.runways[0].version == 5


def test_holding_and_runway_guards_and_stopped_occupancy():
    hold = at_hold()
    with pytest.raises(TrafficConflict, match="version required"):
        step(hold, S.LINED_UP)
    lined, _ = step(hold, S.LINED_UP, expected_runway_version=1)
    stopped, facts = step(lined, S.STOPPED)
    assert stopped.aerodrome.runways[0].occupants == ("aircraft-1",)
    assert len(facts) == 1
    with pytest.raises(TrafficConflict, match="reassign"):
        step(lined, S.TAKEOFF_ROLL, runway_id="another")
    taxi, _ = step(hold, S.TAXIING)
    for holding_id in (None, "missing"):
        with pytest.raises(ValueError):
            step(taxi, S.HOLDING, holding_point_id=holding_id)


def event(payload, sequence=3):
    kind = (
        EventType.AIRCRAFT_SPAWNED
        if isinstance(payload, AircraftSpawnedPayload)
        else EventType.AIRCRAFT_STATE_CHANGED
        if isinstance(payload, AircraftStateChangedPayload)
        else EventType.RUNWAY_OCCUPANCY_CHANGED
    )
    return DomainEvent(
        event_id=f"traffic-{sequence}",
        session_id="traffic-session",
        sequence=sequence,
        event_type=kind,
        sim_time=0.0,
        wall_time_utc=NOW,
        actor=EventActor(kind="system"),
        source=EventSource(component="traffic", version="1.0"),
        correlation_id="traffic-command",
        payload=payload,
    )


def test_fact_contracts_and_event_round_trips():
    hold = at_hold()
    _, facts = step(hold, S.LINED_UP, expected_runway_version=1)
    spawned = AircraftSpawnedPayload(aircraft=aircraft(S.PARKED), aerodrome=hold.aerodrome)
    for payload in (spawned, *facts):
        fact = event(payload)
        assert DomainEvent.model_validate_json(fact.model_dump_json()) == fact
        with pytest.raises(ValueError):
            event(payload, sequence=1)
    raw = facts[0].model_dump(mode="json")
    raw["after"]["heading_deg"] = 90
    with pytest.raises(ValueError, match="unrelated"):
        AircraftStateChangedPayload.model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError, match="material"):
        RunwayOccupancyChangedPayload(
            before=facts[1].after, after=facts[1].after, aircraft_id="aircraft-1", present=True
        )


class Catalogue:
    def get(self, *args):
        return scenario()


def setup(store, *, running=True):
    source = scenario()
    sessions = DurableSessionService(
        store,
        SessionVersions("1", "a" * 64, "1", "1"),
        scenario_catalogue=Catalogue(),
        clock=lambda: NOW,
    )
    session = sessions.create(
        scenario_id=source.id,
        scenario_version=source.version,
        seed=None,
        idempotency_key=uuid4(),
        correlation_id=uuid4(),
        resolve_scenario=lambda: source,
    )
    sid = session.session_id
    sessions.transition(
        sid, Phase.INITIALISING, expected_version=1, idempotency_key=uuid4(), correlation_id=uuid4()
    )
    traffic = TrafficService(store, clock=lambda: NOW)
    key = uuid4()
    result = traffic.initialise(
        sid, source, expected_session_version=2, idempotency_key=key, correlation_id=uuid4()
    )
    if running:
        for version, phase in ((2, Phase.READY), (3, Phase.RUNNING)):
            sessions.transition(
                sid,
                phase,
                expected_version=version,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
    return sid, sessions, traffic, key, result


def durable_step(service, sid, target, **kwargs):
    current = service.get(sid)
    return service.transition(
        sid,
        "aircraft-1",
        target,
        expected_session_version=4,
        expected_version=current.aircraft[0].version,
        idempotency_key=uuid4(),
        correlation_id=uuid4(),
        **kwargs,
    )


def durable_hold(service, sid):
    for target in (S.READY_TO_TAXI, S.TAXIING):
        durable_step(service, sid, target)
    durable_step(service, sid, S.HOLDING, holding_point_id="hold-a")


def test_durable_batch_restart_replay_and_original_retry(tmp_path):
    path = tmp_path / "traffic.sqlite3"
    with SQLiteEventStore(path) as store:
        sid, sessions, service, key, original = setup(store)
        durable_hold(service, sid)
        command = dict(
            expected_session_version=4,
            expected_version=4,
            expected_runway_version=1,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        result = service.transition(sid, "aircraft-1", S.LINED_UP, **command)
        assert [e.event_type for e in result.events] == [
            EventType.AIRCRAFT_STATE_CHANGED,
            EventType.RUNWAY_OCCUPANCY_CHANGED,
        ]
        assert result.events[1].sequence == result.events[0].sequence + 1
        assert result.events[0].correlation_id == result.events[1].correlation_id
        durable_step(service, sid, S.TAKEOFF_ROLL)
        history = store.read_after(sid, 0)
        expected = service.get(sid)
        assert sessions.get(sid).version == 4
        assert service.transition(sid, "aircraft-1", S.LINED_UP, **command) == result
        assert (
            service.initialise(
                sid,
                scenario(),
                expected_session_version=2,
                idempotency_key=key,
                correlation_id=uuid4(),
            )
            == original
        )
        assert store.read_after(sid, 0) == history
        assert len(store.pending(sid)) == len(history)
        with pytest.raises(WriteConflict, match="different input"):
            service.transition(sid, "aircraft-1", S.STOPPED, **command)
    with SQLiteEventStore(path, migration_mode="validate") as store:
        assert TrafficService(store).get(sid) == expected
        assert project_traffic(store.read_after(sid, 0)) == expected


def table_snapshot(store):
    return {
        name: store._connection.execute(f"SELECT * FROM {name}").fetchall()
        for name in ("events", "sessions", "requests", "outbox")
    }


def test_failed_second_effect_rolls_back_all_tables(tmp_path):
    with SQLiteEventStore(tmp_path / "traffic.sqlite3") as store:
        sid, _, service, _, _ = setup(store)
        durable_hold(service, sid)
        before = table_snapshot(store)
        store._connection.execute(
            "CREATE TEMP TRIGGER fail BEFORE INSERT ON events "
            "WHEN json_extract(NEW.document, '$.event_type') = 'runway.occupancy_changed' "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(PersistenceError):
            durable_step(service, sid, S.LINED_UP, expected_runway_version=1)
        assert table_snapshot(store) == before
        store._connection.execute("DROP TRIGGER fail")
        store.recover()
        assert service.get(sid).aircraft[0].state == S.HOLDING
        durable_step(service, sid, S.LINED_UP, expected_runway_version=1)


def test_replay_and_store_reject_incomplete_or_orphan_occupancy(tmp_path):
    with SQLiteEventStore(tmp_path / "traffic.sqlite3") as store:
        sid, _, service, _, _ = setup(store)
        durable_hold(service, sid)
        prefix = store.read_after(sid, 0)
        result = durable_step(service, sid, S.LINED_UP, expected_runway_version=1)
        for history in (prefix + result.events[:1], prefix + result.events[1:]):
            with pytest.raises(ValueError):
                project_traffic(history)
        with SQLiteEventStore(tmp_path / "other.sqlite3") as other:
            other.append(sid, 0, prefix)
            before = table_snapshot(other)
            with pytest.raises(ValueError):
                other.append(sid, len(prefix), result.events[:1])
            assert table_snapshot(other) == before


def test_phase_reinitialisation_and_versions_block_without_writes(tmp_path):
    with SQLiteEventStore(tmp_path / "traffic.sqlite3") as store:
        sid, _, service, _, _ = setup(store, running=False)
        before = table_snapshot(store)
        with pytest.raises(TrafficConflict, match="lifecycle"):
            service.transition(
                sid,
                "aircraft-1",
                S.READY_TO_TAXI,
                expected_session_version=2,
                expected_version=1,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
        with pytest.raises(TrafficConflict, match="already initialised"):
            service.initialise(
                sid,
                scenario(),
                expected_session_version=2,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
        assert table_snapshot(store) == before


def test_stale_history_and_builder_io_guard(tmp_path, monkeypatch):
    with SQLiteEventStore(tmp_path / "traffic.sqlite3") as store:
        sid, _, service, _, _ = setup(store)
        original_commit = store.commit
        building = False
        original_read = store.read_after
        original_get = store.get_session

        def read(*args):
            assert not building
            return original_read(*args)

        def get(*args):
            assert not building
            return original_get(*args)

        def commit(request, builder):
            def guarded(sequence):
                nonlocal building
                building = True
                try:
                    return builder(sequence)
                finally:
                    building = False

            return original_commit(request, guarded)

        monkeypatch.setattr(store, "read_after", read)
        monkeypatch.setattr(store, "get_session", get)
        monkeypatch.setattr(store, "commit", commit)
        durable_step(service, sid, S.READY_TO_TAXI)

        def stale(request, builder):
            return original_commit(request, lambda sequence: builder(sequence + 1))

        monkeypatch.setattr(store, "commit", stale)
        before = table_snapshot(store)
        with pytest.raises(TrafficConflict, match="history changed"):
            durable_step(service, sid, S.TAXIING)
        assert table_snapshot(store) == before


def test_initialisation_rejects_changed_scenario_without_writes(tmp_path):
    with SQLiteEventStore(tmp_path / "traffic.sqlite3") as store:
        sid, _, _, _, _ = setup(store, running=False)
        prefix = store.read_after(sid, 0)[:2]
    with SQLiteEventStore(tmp_path / "unpinned.sqlite3") as store:
        store.append(sid, 0, prefix)
        raw = scenario().model_dump(mode="json")
        raw["default_seed"] += 1
        changed = Scenario.model_validate_json(json.dumps(raw))
        before = table_snapshot(store)
        with pytest.raises(TrafficConflict, match="pinned"):
            TrafficService(store, clock=lambda: NOW).initialise(
                sid,
                changed,
                expected_session_version=2,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
        assert table_snapshot(store) == before


def test_concurrent_traffic_commit_prevents_stale_command(tmp_path, monkeypatch):
    path = tmp_path / "traffic.sqlite3"
    with SQLiteEventStore(path) as first, SQLiteEventStore(path) as second:
        sid, _, service, _, _ = setup(first)
        competing = TrafficService(second, clock=lambda: NOW)
        original_commit = first.commit

        def interleaved(request, build):
            durable_step(competing, sid, S.READY_TO_TAXI)
            return original_commit(request, build)

        monkeypatch.setattr(first, "commit", interleaved)
        with pytest.raises(TrafficConflict, match="history changed"):
            durable_step(service, sid, S.STOPPED)
        assert service.get(sid).aircraft[0].state == S.READY_TO_TAXI
        assert service.get(sid).aircraft[0].version == 2
        assert first.get_session(sid).session.version == 4


def test_multiple_spawns_capture_geometry_once():
    source = scenario()
    raw = source.model_dump(mode="json")
    raw["entities"].append(raw["entities"][0] | {"id": "aircraft-2", "callsign": "TRAINER 2"})
    mapped = initial_traffic(Scenario.model_validate_json(json.dumps(raw)))
    facts = tuple(
        event(
            AircraftSpawnedPayload(aircraft=a, aerodrome=mapped.aerodrome if index == 0 else None),
            sequence=index + 3,
        )
        for index, a in enumerate(mapped.aircraft)
    )
    assert project_traffic(facts) == mapped
    with pytest.raises(ValueError, match="missing geometry"):
        project_traffic(facts[1:])
    with pytest.raises(ValueError, match="already initialised"):
        project_traffic(facts + facts[:1])
