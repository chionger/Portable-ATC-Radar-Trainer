import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.factory import create_app
from apps.api.sessions import service
from packages.application.scenarios import ScenarioInvalid, ScenarioMissing
from packages.domain.scenario import Scenario, ScenarioLoadedPayload
from packages.domain.session import SessionLifecycleState as State
from packages.infrastructure.configuration import ConfigurationError, load_settings
from packages.infrastructure.persistence.sqlite import SQLiteEventStore
from packages.infrastructure.scenarios import LocalScenarioCatalogue, load_scenario

FIXTURE = Path(__file__).parents[1] / "fixtures/scenarios/reference.yaml"


def data():
    return yaml.safe_load(FIXTURE.read_text())


def encoded(value):
    return yaml.safe_dump(value).encode()


def configured(tmp_path):
    directory = tmp_path / "scenarios"
    directory.mkdir()
    (directory / "reference.yaml").write_bytes(FIXTURE.read_bytes())
    return load_settings(
        environ={},
        overrides={
            "paths": {"data_root": str(tmp_path)},
            "scenarios": {"directory": str(directory)},
        },
    )


def post(client, key=None):
    return client.post(
        "/api/v1/sessions",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"scenario_id": "reference-tower", "scenario_version": "1.0"},
    )


def test_reference_is_deterministic_and_immutable():
    first = load_scenario(FIXTURE.read_bytes())
    second = load_scenario(encoded(data()))
    assert first == second and first.content_hash() == second.content_hash()
    with pytest.raises(ValidationError):
        first.version = "2"
    with pytest.raises(ValidationError):
        first.geometry.runways[0].width_m = 20
    assert isinstance(first.entities, tuple)
    changed = data()
    changed["default_seed"] += 1
    assert load_scenario(encoded(changed)).content_hash() != first.content_hash()


@pytest.mark.parametrize(
    "path,value,location",
    [
        (case["path"], case["value"], case["location"])
        for case in json.loads((FIXTURE.parent / "invalid-matrix.json").read_text())
    ],
)
def test_invalid_fixture_matrix_has_precise_locations(path, value, location):
    raw = data()
    cursor = raw
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    with pytest.raises(ScenarioInvalid) as error:
        load_scenario(encoded(raw))
    assert location in {issue.location for issue in error.value.issues}


@pytest.mark.parametrize(
    "content",
    [
        b'!!python/object/apply:os.system ["echo unsafe"]',
        b"x: &anchor [1]\ny: *anchor",
        b"x: !custom unsafe",
        b"x: 1\nx: 2",
        b"---\nx: 1\n---\ny: 2",
        b"\xff",
        b"x: " + b"[" * 40 + b"0" + b"]" * 40,
        pytest.param(b"x" * (1024 * 1024 + 1), id="oversized-document"),
    ],
)
def test_malicious_or_unbounded_yaml_is_rejected(content):
    with pytest.raises(ScenarioInvalid):
        load_scenario(content)


def test_duplicate_key_reports_line_and_column():
    with pytest.raises(ScenarioInvalid) as error:
        load_scenario(b"id: a\nid: b")
    assert error.value.issues[0].location == "line:2:column:1"


def test_duplicate_callsigns_and_degenerate_taxiway():
    raw = data()
    other = copy.deepcopy(raw["entities"][0])
    other["id"] = "aircraft-2"
    raw["entities"].append(other)
    with pytest.raises(ScenarioInvalid, match="validation"):
        load_scenario(encoded(raw))
    raw = data()
    raw["geometry"]["taxiways"][0]["points"] *= 0
    with pytest.raises(ScenarioInvalid):
        load_scenario(encoded(raw))


def test_catalogue_capture_version_selection_and_duplicate_identity(tmp_path):
    settings = configured(tmp_path)
    directory = Path(settings.scenarios.directory)
    catalogue = LocalScenarioCatalogue(directory)
    captured = catalogue.get("reference-tower")
    raw = data()
    raw["default_seed"] = 99
    (directory / "reference.yaml").write_bytes(encoded(raw))
    assert catalogue.get("reference-tower") == captured
    assert (
        LocalScenarioCatalogue(directory).get("reference-tower").content_hash()
        != captured.content_hash()
    )
    raw["version"] = "2.0"
    (directory / "v2.yaml").write_bytes(encoded(raw))
    two = LocalScenarioCatalogue(directory)
    assert [item.version for item in two.list()] == ["1.0", "2.0"]
    assert two.get("reference-tower", "2.0").default_seed == 99
    with pytest.raises(ScenarioInvalid):
        two.get("reference-tower")
    with pytest.raises(ScenarioMissing):
        two.get("../private")
    (directory / "duplicate.yaml").write_bytes(encoded(raw))
    with pytest.raises(ScenarioInvalid):
        LocalScenarioCatalogue(directory).list()


def test_catalogue_api_is_metadata_only_and_has_no_db_side_effect(tmp_path):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/scenarios")
        assert response.status_code == 200 and len(response.json()) == 1
        detail = client.get("/api/v1/scenarios/reference-tower?version=1.0")
        assert detail.json() == response.json()[0]
        assert set(detail.json()) == {
            "schema_version",
            "id",
            "version",
            "content_hash",
            "title",
            "description",
            "default_seed",
        }
        assert "geometry" not in detail.json() and str(tmp_path) not in detail.text
        assert client.get("/api/v1/scenarios/missing").status_code == 404
        assert client.get("/api/v1/scenarios/reference-tower?version=../private").status_code == 422
    assert not settings.database_path().exists()


def test_session_pins_scenario_hash_and_seed_and_recovers(tmp_path):
    settings = configured(tmp_path)
    key = uuid4()
    with TestClient(create_app(settings)) as client:
        created = post(client, key)
        assert created.status_code == 201
        session = created.json()["session"]
        assert session["scenario_hash"] == load_scenario(FIXTURE.read_bytes()).content_hash()
        assert session["seed"] == 42
    (Path(settings.scenarios.directory) / "reference.yaml").write_text("invalid: content")
    with TestClient(create_app(settings)) as client:
        assert post(client, key).json() == created.json()
    with SQLiteEventStore(settings.database_path()) as store:
        recovered = store.get_session(session["session_id"]).session
        assert recovered.scenario_hash == session["scenario_hash"]
        result = service(store, settings).prepare_scenario(
            recovered.session_id,
            LocalScenarioCatalogue(Path(settings.scenarios.directory)),
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        assert result.lifecycle_state == State.FAILED
        assert result.failure.reason == "SCENARIO_VALIDATION_FAILED"
        assert [event.event_type.value for event in store.read_after(result.session_id, 0)] == [
            "session.created",
            "session.initialising",
            "session.failed",
        ]


def test_changed_hash_cannot_pass_initialisation(tmp_path):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = post(client).json()["session"]["session_id"]
    raw = data()
    raw["default_seed"] = 99
    (Path(settings.scenarios.directory) / "reference.yaml").write_bytes(encoded(raw))
    with SQLiteEventStore(settings.database_path()) as store:
        result = service(store, settings).prepare_scenario(
            session_id,
            LocalScenarioCatalogue(Path(settings.scenarios.directory)),
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        assert result.lifecycle_state == State.FAILED


def test_valid_preparation_does_not_claim_readiness_or_emit_loaded(tmp_path):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = post(client).json()["session"]["session_id"]
    with SQLiteEventStore(settings.database_path()) as store:
        app = service(store, settings)
        key = uuid4()
        for _ in range(2):
            result = app.prepare_scenario(
                session_id,
                LocalScenarioCatalogue(Path(settings.scenarios.directory)),
                idempotency_key=key,
                correlation_id=uuid4(),
            )
            assert result.lifecycle_state == State.INITIALISING
        assert len(store.read_after(session_id, 0)) == 2


def test_invalid_catalogue_create_has_no_session_event(tmp_path):
    settings = configured(tmp_path)
    (Path(settings.scenarios.directory) / "reference.yaml").write_text("id: broken")
    with TestClient(create_app(settings)) as client:
        response = post(client)
        assert response.status_code == 422 and response.json()["code"] == "INVALID_SCENARIO"
        assert response.json()["details"]["issues"]
    with SQLiteEventStore(settings.database_path()) as store:
        assert store._connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0


@pytest.mark.parametrize("configuration", [{"directory": "relative"}, {"validation": "permissive"}])
def test_configuration_rejects_unsafe_or_permissive_settings(configuration):
    with pytest.raises(ConfigurationError):
        load_settings(environ={}, overrides={"scenarios": configuration})


def test_configuration_redaction_and_empty_default_catalogue(tmp_path):
    settings = load_settings(environ={"ATC_SCENARIOS_DIRECTORY": str(tmp_path)})
    assert str(tmp_path) not in json.dumps(settings.redacted_report())
    with TestClient(create_app(load_settings(environ={}))) as client:
        assert client.get("/api/v1/scenarios").json() == []


def test_published_scenario_schemas():
    fixture_root = FIXTURE.parent
    assert Scenario.model_json_schema() == json.loads(
        (fixture_root / "scenario.schema.json").read_text()
    )
    assert ScenarioLoadedPayload.model_json_schema() == json.loads(
        (fixture_root / "scenario-loaded.schema.json").read_text()
    )


def test_ready_checks_hash_and_retry_survives_missing_scenario(tmp_path):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = post(client).json()["session"]["session_id"]
    with SQLiteEventStore(settings.database_path()) as store:
        app = service(store, settings)
        app.prepare_scenario(
            session_id,
            LocalScenarioCatalogue(Path(settings.scenarios.directory)),
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        key = uuid4()
        ready = app.transition(
            session_id, State.READY, expected_version=2, idempotency_key=key, correlation_id=uuid4()
        )
        assert ready.lifecycle_state == State.READY
    (Path(settings.scenarios.directory) / "reference.yaml").write_text("bad: data")
    with SQLiteEventStore(settings.database_path()) as store:
        assert (
            service(store, settings).transition(
                session_id,
                State.READY,
                expected_version=2,
                idempotency_key=key,
                correlation_id=uuid4(),
            )
            == ready
        )


def test_ready_rejects_changed_scenario_without_event(tmp_path):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = post(client).json()["session"]["session_id"]
    with SQLiteEventStore(settings.database_path()) as store:
        app = service(store, settings)
        app.transition(
            session_id,
            State.INITIALISING,
            expected_version=1,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
    raw = data()
    raw["default_seed"] += 1
    (Path(settings.scenarios.directory) / "reference.yaml").write_bytes(encoded(raw))
    with SQLiteEventStore(settings.database_path()) as store:
        with pytest.raises(ScenarioInvalid):
            service(store, settings).transition(
                session_id,
                State.READY,
                expected_version=2,
                idempotency_key=uuid4(),
                correlation_id=uuid4(),
            )
        assert len(store.read_after(session_id, 0)) == 2
        assert store.get_session(session_id).session.lifecycle_state == State.INITIALISING


def test_inaccessible_directory_fails_preparation_durably(tmp_path, monkeypatch):
    settings = configured(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = post(client).json()["session"]["session_id"]
    original = Path.iterdir

    def denied(path):
        if path == Path(settings.scenarios.directory):
            raise PermissionError("private-path")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    with SQLiteEventStore(settings.database_path()) as store:
        result = service(store, settings).prepare_scenario(
            session_id,
            LocalScenarioCatalogue(Path(settings.scenarios.directory)),
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        assert result.lifecycle_state == State.FAILED


def test_catalogue_rejects_links_without_opening_them(tmp_path, monkeypatch):
    settings = configured(tmp_path)
    linked = Path(settings.scenarios.directory) / "reference.yaml"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == linked or original(path))
    with pytest.raises(ScenarioInvalid) as error:
        LocalScenarioCatalogue(Path(settings.scenarios.directory)).list()
    assert error.value.issues[0].code == "not_regular_file"


@pytest.mark.parametrize("value", [123, "", "A" * 64, "0" * 63])
def test_invalid_session_scenario_hash(value):
    from dataclasses import replace

    from packages.application.persistence import project_session
    from packages.domain.events import DomainEvent

    event = DomainEvent.model_validate_json(
        (FIXTURE.parent.parent / "events/session.created.json").read_text()
    )
    session = project_session((event,)).session

    with pytest.raises(ValueError):
        replace(session, scenario_hash=value)
