"""Neutral provider contracts, defensive application translation and durable effects."""

import ast
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from simulation_contract import A, S, SimulationProviderContract, command, traffic
from test_traffic import NOW, durable_hold, setup, table_snapshot

from packages.application.simulation import SimulationRejected, SimulationService, translate_effects
from packages.application.traffic_projection import project_traffic
from packages.domain.events import DomainEvent, EventType
from packages.domain.session import SessionLifecycleState
from packages.domain.simulation import (
    ApplyResult,
    ProviderEffect,
    RejectionCode,
    SimulationCommand,
    SimulationParameters,
)
from packages.domain.traffic import AircraftRouteAssignedPayload, TrafficConflict
from packages.infrastructure.persistence.sqlite import (
    PersistenceError,
    SQLiteEventStore,
    WriteConflict,
)
from packages.infrastructure.simulation.fake import DeterministicFake


class TestFakeContract(SimulationProviderContract):
    @pytest.fixture
    def provider(self):
        return DeterministicFake()


@pytest.mark.parametrize(
    "field,value",
    [
        ("command_id", ""),
        ("aircraft_id", "../bad"),
        ("action", "TELEPORT"),
        ("expected_entity_version", True),
        ("expected_entity_version", 0),
        ("issued_at_sim_time", -1),
        ("issued_at_sim_time", float("inf")),
        ("schema_version", "2.0"),
        ("sequence", 1),
        ("parameters", {"holding_point_id": "hold-a"}),
    ],
)
def test_command_rejects_invalid_contract(field, value):
    raw = command().model_dump(mode="json") | {field: value}
    with pytest.raises(ValueError):
        SimulationCommand.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "patch",
    [
        {"accepted": True},
        {"accepted": False},
        {"accepted": True, "rejection_code": "ILLEGAL_STATE"},
        {"accepted": 1, "rejection_code": "ILLEGAL_STATE"},
        {"accepted": False, "rejection_code": "UNKNOWN_CODE"},
    ],
)
def test_result_rejects_incoherent_contract(patch):
    with pytest.raises(ValueError):
        ApplyResult.model_validate_json(json.dumps(patch))


@pytest.mark.parametrize(
    "fault",
    [
        "entity",
        "target",
        "version",
        "result_version",
        "runway",
        "extra",
        "missing",
        "duplicate",
        "event_identity",
    ],
)
def test_translator_rejects_invalid_provider_effects_without_mutation(fault):
    state, request = traffic(), command()
    saved = state.model_dump_json()
    raw = DeterministicFake().apply(request, state).model_dump(mode="json")
    payload = raw["effects"][0]["structured_payload"]
    if fault == "entity":
        raw["effects"][0]["entity_id"] = "another"
    elif fault == "target":
        payload["target"] = "STOPPED"
    elif fault == "version":
        payload["expected_entity_version"] = 99
    elif fault == "result_version":
        raw["resulting_entity_version"] = 99
    elif fault == "runway":
        payload["runway_id"] = "missing"
    elif fault == "extra":
        raw["extra"] = True
    elif fault == "missing":
        raw["effects"] = []
    elif fault == "duplicate":
        raw["effects"] *= 2
    else:
        raw["effects"][0]["event_id"] = "provider-must-not-own-this"
    with pytest.raises(ValueError):
        translate_effects(state, request, ApplyResult.model_validate_json(json.dumps(raw)))
    assert state.model_dump_json() == saved


def test_effect_type_and_payload_must_match():
    raw = DeterministicFake().apply(command(), traffic()).effects[0].model_dump(mode="json")
    raw["effect_type"] = "ROUTE_ASSIGNED"
    with pytest.raises(ValueError):
        ProviderEffect.model_validate_json(json.dumps(raw))


def test_route_event_rejects_unrelated_mutation():
    request = command(parameters=SimulationParameters(route=("taxiway-a", "hold-a")))
    state = traffic()
    _, facts = translate_effects(state, request, DeterministicFake().apply(request, state))
    raw = facts[0].model_dump(mode="json")
    raw["after"]["heading_deg"] = 90
    with pytest.raises(ValueError, match="unrelated"):
        AircraftRouteAssignedPayload.model_validate_json(json.dumps(raw))


def test_duplicate_route_omits_route_fact():
    state = traffic()
    request = command(parameters=SimulationParameters(route=state.aircraft[0].route))
    result = DeterministicFake().apply(request, state)
    assert result.accepted and len(result.effects) == 1 and result.resulting_entity_version == 2


def test_fake_has_no_api_database_event_or_clock_dependencies():
    path = Path(__file__).parents[2] / "packages/infrastructure/simulation/fake.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in {"packages.domain.simulation", "packages.domain.traffic"}
        assert not isinstance(node, ast.Import)


def apply(service, sid, request, key=None):
    return service.apply(
        sid,
        request,
        expected_session_version=4,
        idempotency_key=key or uuid4(),
        correlation_id=uuid4(),
    )


def test_command_commits_occupancy_before_notification_and_replays(tmp_path):
    path = tmp_path / "simulation.sqlite3"
    with SQLiteEventStore(path) as store:
        sid, _, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)
        notifications = []

        def notify(result):
            # A separate connection sees the commit and the durable outbox first.
            with SQLiteEventStore(path) as reader:
                history = reader.read_after(sid, 0)
                assert history[-2:] == result.events
                assert project_traffic(history).aerodrome.runways[0].occupants == ("aircraft-1",)
                assert set(e.event_id for e in result.events) <= set(
                    e.event_id for e in reader.pending(sid)
                )
            notifications.append(result)

        service = SimulationService(
            store, DeterministicFake(), clock=lambda: NOW, on_committed=notify
        )
        result = apply(service, sid, command(A.LINE_UP, expected_entity_version=4))
        assert [e.event_type for e in result.events] == [
            EventType.AIRCRAFT_STATE_CHANGED,
            EventType.RUNWAY_OCCUPANCY_CHANGED,
        ]
        assert all(e.causation_id == "command-1" for e in result.events)
        assert all(DomainEvent.model_validate_json(e.model_dump_json()) == e for e in result.events)
        assert notifications == [result] and result.projection.session.version == 4
        expected = service.get(sid)
    with SQLiteEventStore(path) as reopened:
        assert project_traffic(reopened.read_after(sid, 0)) == expected


def test_route_and_state_commit_and_round_trip(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, traffic_service, _, _ = setup(store)
        traffic_service.transition(
            sid,
            "aircraft-1",
            S.READY_TO_TAXI,
            expected_session_version=4,
            expected_version=1,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        service = SimulationService(store, DeterministicFake(), clock=lambda: NOW)
        request = command(
            expected_entity_version=2,
            parameters=SimulationParameters(route=("taxiway-a", "hold-a")),
        )
        result = apply(service, sid, request)
        assert [e.event_type for e in result.events] == [
            EventType.AIRCRAFT_ROUTE_ASSIGNED,
            EventType.AIRCRAFT_STATE_CHANGED,
        ]
        assert service.get(sid).aircraft[0].version == 4
        assert service.get(sid).aircraft[0].route == request.parameters.route
        assert (
            DomainEvent.model_validate_json(result.events[0].model_dump_json()) == result.events[0]
        )


def test_rejected_command_writes_and_publishes_nothing(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, _, _, _ = setup(store)
        notifications = []
        service = SimulationService(
            store, DeterministicFake(), clock=lambda: NOW, on_committed=notifications.append
        )
        before = table_snapshot(store)
        with pytest.raises(SimulationRejected) as error:
            apply(service, sid, command())  # PARKED cannot directly TAXI.
        assert error.value.code == RejectionCode.ILLEGAL_STATE
        assert table_snapshot(store) == before and notifications == []


def test_second_effect_failure_never_publishes_or_partially_commits(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)
        notifications = []
        service = SimulationService(
            store, DeterministicFake(), clock=lambda: NOW, on_committed=notifications.append
        )
        before = table_snapshot(store)
        store._connection.execute(
            "CREATE TEMP TRIGGER fail BEFORE INSERT ON events "
            "WHEN json_extract(NEW.document, '$.event_type') = 'runway.occupancy_changed' "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(PersistenceError):
            apply(service, sid, command(A.LINE_UP, expected_entity_version=4))
        assert table_snapshot(store) == before and notifications == []


def test_retry_survives_provider_and_notification_failures(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)

        def unavailable(*args):
            raise RuntimeError("unavailable")

        service = SimulationService(
            store, DeterministicFake(), clock=lambda: NOW, on_committed=unavailable
        )
        request, key = command(A.LINE_UP, expected_entity_version=4), uuid4()
        with pytest.raises(RuntimeError, match="unavailable"):
            apply(service, sid, request, key)
        before = table_snapshot(store)

        class Broken:
            apply = staticmethod(unavailable)

        service.provider = Broken()
        service.on_committed = None
        result = apply(service, sid, request, key)
        assert len(result.events) == 2 and table_snapshot(store) == before
        with pytest.raises(WriteConflict):
            apply(service, sid, command(A.TAKE_OFF, expected_entity_version=5), key)


def test_provider_race_rejected_and_never_called_under_write_lock(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)

        class Interleaving:
            def apply(self, request, state):
                assert not store._connection.in_transaction
                result = DeterministicFake().apply(request, state)
                traffic_service.transition(
                    sid,
                    "aircraft-1",
                    S.TAXIING,
                    expected_session_version=4,
                    expected_version=4,
                    idempotency_key=uuid4(),
                    correlation_id=uuid4(),
                )
                return result

        notifications = []
        service = SimulationService(
            store, Interleaving(), clock=lambda: NOW, on_committed=notifications.append
        )
        with pytest.raises(TrafficConflict, match="history changed"):
            apply(service, sid, command(A.LINE_UP, expected_entity_version=4))
        assert service.get(sid).aircraft[0].state == S.TAXIING
        assert not service.get(sid).aerodrome.runways[0].occupied and not notifications


def test_time_and_phase_guards(tmp_path):
    with SQLiteEventStore(tmp_path / "simulation.sqlite3") as store:
        sid, _, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)
        service = SimulationService(store, DeterministicFake(), clock=lambda: NOW)
        before = table_snapshot(store)
        with pytest.raises(TrafficConflict, match="simulation time"):
            apply(
                service, sid, command(A.LINE_UP, expected_entity_version=4, issued_at_sim_time=1.0)
            )
        assert table_snapshot(store) == before


def test_models_are_frozen_and_reject_provider_bypass():
    request = command()
    with pytest.raises(ValidationError):
        request.expected_entity_version = 2
    with pytest.raises(ValidationError):
        request.parameters.runway_id = "other"
    state = traffic()
    result = DeterministicFake().apply(request, state)
    forged = result.model_copy(update={"resulting_entity_version": True})
    with pytest.raises(ValueError):
        translate_effects(state, request, forged)


@pytest.mark.parametrize(
    "filename,model",
    [
        ("command.schema.json", SimulationCommand),
        ("result.schema.json", ApplyResult),
        ("effect.schema.json", ProviderEffect),
    ],
)
def test_published_port_schemas_match(filename, model):
    path = Path(__file__).parents[1] / "fixtures/simulation" / filename
    assert json.loads(path.read_text()) == model.model_json_schema()


def test_paused_session_rejects_and_retry_after_restart_preserves_original(tmp_path):
    path = tmp_path / "simulation.sqlite3"
    with SQLiteEventStore(path) as store:
        sid, sessions, traffic_service, _, _ = setup(store)
        durable_hold(traffic_service, sid)
        service = SimulationService(store, DeterministicFake(), clock=lambda: NOW)
        key, request = uuid4(), command(A.LINE_UP, expected_entity_version=4)
        original = apply(service, sid, request, key)
        apply(service, sid, command(A.TAKE_OFF, expected_entity_version=5, command_id="takeoff"))
        sessions.transition(
            sid,
            SessionLifecycleState.PAUSED,
            expected_version=4,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        before = table_snapshot(store)
        with pytest.raises(TrafficConflict, match="lifecycle"):
            service.apply(
                sid,
                command(A.VACATE, expected_entity_version=6),
                expected_session_version=5,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
        assert table_snapshot(store) == before
    with SQLiteEventStore(path) as reopened:
        service = SimulationService(reopened, DeterministicFake(), clock=lambda: NOW)
        assert apply(service, sid, request, key) == original
        assert service.get(sid).aircraft[0].state == S.TAKEOFF_ROLL
        assert table_snapshot(reopened) == before


def test_fake_rejects_route_with_unknown_geometry_without_partial_effects():
    request = command(parameters=SimulationParameters(route=("missing",)))
    state = traffic()
    original = state.model_dump_json()
    result = DeterministicFake().apply(request, state)
    assert not result.accepted and result.rejection_code == RejectionCode.INVALID_PARAMETERS
    assert not result.effects and state.model_dump_json() == original


def test_route_output_cannot_substitute_another_valid_route():
    state = traffic()
    request = command(parameters=SimulationParameters(route=("taxiway-a", "hold-a")))
    raw = DeterministicFake().apply(request, state).model_dump(mode="json")
    raw["effects"][0]["structured_payload"]["route"] = ["hold-a"]
    with pytest.raises(ValueError, match="requested route"):
        translate_effects(state, request, ApplyResult.model_validate_json(json.dumps(raw)))
