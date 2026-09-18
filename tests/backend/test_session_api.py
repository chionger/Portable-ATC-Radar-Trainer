import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.factory import create_app
from apps.api.sessions import service
from packages.application.sessions import DurableSessionService
from packages.domain.session import SessionFailure, SessionVersions
from packages.domain.session import SessionLifecycleState as State
from packages.infrastructure.configuration import ConfigurationError, load_settings
from packages.infrastructure.persistence.sqlite import SQLiteEventStore, WriteConflict


def settings_for(tmp_path, **extra):
    return load_settings(
        environ={},
        overrides={
            "paths": {"data_root": str(tmp_path)},
            **extra,
        },
    )


def create(client, key=None, **body):
    return client.post(
        "/api/v1/sessions",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"scenario_id": "training", "scenario_version": "1.0", **body},
    )


def advance(settings, session_id, target, **kwargs):
    with SQLiteEventStore(settings.database_path()) as store:
        app = service(store, settings)
        return app.transition(
            session_id,
            target,
            expected_version=app.get(session_id).version,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
            **kwargs,
        )


def command(client, session_id, action, version, key=None):
    return client.post(
        f"/api/v1/sessions/{session_id}/{action}",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"expected_version": version},
    )


def test_rest_lifecycle_restart_retries_and_projection(tmp_path):
    settings = settings_for(tmp_path)
    key = uuid4()
    with TestClient(create_app(settings)) as client:
        response = create(client, key)
        assert response.status_code == 201
        initial = response.json()
        session_id = initial["session"]["session_id"]
        assert initial["session"]["lifecycle_state"] == "CREATED"
        assert initial["session"]["versions"]["configuration_hash"] == settings.configuration_hash()
        assert create(client, key).json() == initial
        assert command(client, session_id, "start", 1).status_code == 409
    advance(settings, session_id, State.INITIALISING)
    advance(settings, session_id, State.READY)
    start_key = uuid4()
    with TestClient(create_app(settings)) as client:
        assert command(client, session_id, "resume", 3).status_code == 409
        started = command(client, session_id, "start", 3, start_key)
        assert started.status_code == 200
        assert command(client, session_id, "pause", 4).status_code == 200
        assert command(client, session_id, "start", 5).status_code == 409
        assert command(client, session_id, "start", 3, start_key).json() == started.json()
        assert (
            client.get(f"/api/v1/sessions/{session_id}").json()["session"]["lifecycle_state"]
            == "PAUSED"
        )
        assert command(client, session_id, "resume", 5).status_code == 200
        assert command(client, session_id, "stop", 6).status_code == 200
        assert command(client, session_id, "start", 7).status_code == 409
    with TestClient(create_app(settings)) as client:
        final = client.get(f"/api/v1/sessions/{session_id}").json()["session"]
        assert final["lifecycle_state"] == "STOPPED" and final["version"] == 7
    with SQLiteEventStore(settings.database_path()) as store:
        events = store.read_after(session_id, 0)
        assert len(events) == 7 and len(store.pending(session_id)) == 7
        assert [event.sequence for event in events] == list(range(1, 8))
        assert store.get_session(session_id).session.lifecycle_state == State.STOPPED


def test_retry_keeps_original_configuration_and_default_seed(tmp_path):
    first = settings_for(tmp_path, sessions={"default_seed": 123})
    key = uuid4()
    with TestClient(create_app(first)) as client:
        original = create(client, key).json()
    second = settings_for(tmp_path, sessions={"default_seed": 456})
    with TestClient(create_app(second)) as client:
        assert create(client, key).json() == original
        assert create(client, key, seed=22).status_code == 409
    assert original["session"]["seed"] == 123


@pytest.mark.parametrize(
    "state", [State.CREATED, State.INITIALISING, State.READY, State.RUNNING, State.PAUSED]
)
def test_forced_failure_is_durable_from_each_live_state(tmp_path, state):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = create(client).json()["session"]["session_id"]
    for target in (State.INITIALISING, State.READY, State.RUNNING, State.PAUSED):
        with SQLiteEventStore(settings.database_path()) as store:
            if store.get_session(session_id).session.lifecycle_state == state:
                break
        advance(settings, session_id, target)
    failure = SessionFailure("infrastructure", "DEPENDENCY_UNAVAILABLE")
    result = advance(settings, session_id, State.FAILED, failure=failure)
    with SQLiteEventStore(settings.database_path()) as store:
        assert store.get_session(session_id).session == result
        assert store.read_after(session_id, 0)[-1].payload.failure == failure
        assert result.outcome.value == "FAILED"


def test_completion_and_simulation_time_are_internal(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = create(client).json()["session"]["session_id"]
    for target in (State.INITIALISING, State.READY, State.RUNNING):
        advance(settings, session_id, target)
    result = advance(settings, session_id, State.COMPLETED, simulation_time=12.5)
    assert result.outcome.value == "COMPLETED" and result.simulation_time == 12.5


@pytest.mark.parametrize(
    "body",
    [
        {"seed": -1},
        {"seed": True},
        {"seed": 2**63},
        {"seed": "1"},
        {"scenario_id": "../private"},
        {"scenario_version": ""},
        {"schema_version": "2.0"},
        {"extra": "PRIVATE_REQUEST_VALUE"},
    ],
)
def test_validation_is_stable_private_and_has_no_storage_effect(tmp_path, body):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = create(client, **body)
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message", "details", "correlation_id"}
    assert "PRIVATE_REQUEST_VALUE" not in response.text
    assert not (tmp_path / "sessions.sqlite3").exists()


def test_missing_and_malformed_ids_and_keys(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        assert client.get("/api/v1/sessions/not-a-uuid").status_code == 422
        assert client.get(f"/api/v1/sessions/{uuid4()}").status_code == 404
        assert command(client, uuid4(), "start", 1).status_code == 404
        assert client.post("/api/v1/sessions", json={}).status_code == 422
        assert client.post("/api/v1/sessions", content="{").status_code == 422


def test_actual_request_limit_and_correlation(tmp_path):
    correlation = str(uuid4())
    with TestClient(
        create_app(settings_for(tmp_path, sessions={"max_request_bytes": 256}))
    ) as client:
        response = client.post(
            "/api/v1/sessions",
            content=iter([b"x" * 200, b"x" * 100]),
            headers={"X-Correlation-ID": correlation},
        )
    assert response.status_code == 413
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"] == correlation
    assert not (tmp_path / "sessions.sqlite3").exists()


def test_storage_failure_and_cors(tmp_path):
    settings = settings_for(tmp_path / "missing-private-parent")
    with TestClient(create_app(settings)) as client:
        result = create(client)
        assert result.status_code == 503 and result.json()["code"] == "PERSISTENCE_UNAVAILABLE"
        assert "missing-private-parent" not in result.text
        preflight = client.options(
            "/api/v1/sessions",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Idempotency-Key,Content-Type",
            },
        )
        assert preflight.status_code == 200


def test_stale_version_key_conflict_and_no_event(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        session_id = create(client).json()["session"]["session_id"]
    for target in (State.INITIALISING, State.READY, State.RUNNING):
        advance(settings, session_id, target)
    key = uuid4()
    with TestClient(create_app(settings)) as client:
        assert command(client, session_id, "pause", 3).status_code == 409
        assert command(client, session_id, "pause", 4, key).status_code == 200
        assert command(client, session_id, "stop", 4, key).status_code == 409
    with SQLiteEventStore(settings.database_path()) as store:
        assert len(store.read_after(session_id, 0)) == 5


def test_application_retry_after_later_change_and_failed_write(tmp_path):
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:
        app = DurableSessionService(
            store,
            SessionVersions("1.0", "0" * 64, "1.0", "1.0"),
            clock=lambda: datetime(2026, 9, 18, tzinfo=UTC),
        )
        key = uuid4()
        first = app.create(
            scenario_id="s",
            scenario_version="1",
            seed=0,
            idempotency_key=key,
            correlation_id=uuid4(),
        )
        app.transition(
            first.session_id,
            State.INITIALISING,
            expected_version=1,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        assert (
            app.create(
                scenario_id="s",
                scenario_version="1",
                seed=0,
                idempotency_key=key,
                correlation_id=uuid4(),
            )
            == first
        )
        with pytest.raises(WriteConflict):
            app.create(
                scenario_id="different",
                scenario_version="1",
                seed=0,
                idempotency_key=key,
                correlation_id=uuid4(),
            )
        assert len(store.read_after(first.session_id, 0)) == 2


@pytest.mark.parametrize(
    "name,value",
    [
        ("default_seed", -1),
        ("default_seed", True),
        ("max_request_bytes", 0),
        ("max_request_bytes", 65537),
    ],
)
def test_session_settings_limits(name, value):
    with pytest.raises(ConfigurationError):
        load_settings(environ={}, overrides={"sessions": {name: value}})


def test_session_settings_environment():
    settings = load_settings(
        environ={"ATC_SESSIONS_DEFAULT_SEED": "42", "ATC_SESSIONS_MAX_REQUEST_BYTES": "512"}
    )
    assert settings.sessions.default_seed == 42 and settings.sessions.max_request_bytes == 512


def test_openapi_contract_snapshot():
    app = create_app(load_settings(environ={}))
    actual = app.openapi()
    expected = json.loads(
        (Path(__file__).parents[1] / "fixtures/session-api.openapi.json").read_text()
    )
    assert actual == expected


def test_failed_projection_write_rolls_back_entire_api_command(tmp_path, monkeypatch):
    import apps.api.sessions as routes

    settings = settings_for(tmp_path)
    original_open = routes.open_store

    def broken_store(settings):
        store = original_open(settings)
        store._connection.execute(
            "CREATE TEMP TRIGGER reject_session BEFORE INSERT ON sessions "
            "BEGIN SELECT RAISE(ABORT, 'private_failure'); END"
        )
        return store

    monkeypatch.setattr(routes, "open_store", broken_store)
    with TestClient(create_app(settings)) as client:
        result = create(client)
        assert result.status_code == 503
        assert "private_failure" not in result.text
    with SQLiteEventStore(settings.database_path()) as store:
        for table in ("events", "sessions", "requests", "outbox"):
            assert store._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_event_correlation_is_preserved_and_retry_does_not_rewrite_it(tmp_path):
    settings = settings_for(tmp_path)
    key, correlation, retry_correlation = uuid4(), uuid4(), uuid4()
    with TestClient(create_app(settings)) as client:
        body = {"scenario_id": "training", "scenario_version": "1.0"}
        response = client.post(
            "/api/v1/sessions",
            json=body,
            headers={
                "Idempotency-Key": str(key),
                "X-Correlation-ID": str(correlation),
            },
        )
        retry = client.post(
            "/api/v1/sessions",
            json=body,
            headers={
                "Idempotency-Key": str(key),
                "X-Correlation-ID": str(retry_correlation),
            },
        )
        assert response.json() == retry.json()
        assert retry.headers["X-Correlation-ID"] == str(retry_correlation)
    with SQLiteEventStore(settings.database_path()) as store:
        (event,) = store.read_after(response.json()["session"]["session_id"], 0)
        assert event.correlation_id == str(correlation)


def test_event_builders_do_not_read_storage(tmp_path):
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:

        class GuardedStore:
            building = False

            def get_session(self, session_id):
                assert not self.building, "Event builders must not perform storage I/O"
                return store.get_session(session_id)

            def commit(self, request, build):
                def guarded(sequence):
                    self.building = True
                    try:
                        return build(sequence)
                    finally:
                        self.building = False

                return store.commit(request, guarded)

        app = DurableSessionService(GuardedStore(), SessionVersions("1.0", "0" * 64, "1.0", "1.0"))
        session = app.create(
            scenario_id="s",
            scenario_version="1",
            seed=0,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        result = app.transition(
            session.session_id,
            State.INITIALISING,
            expected_version=1,
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )
        assert result.version == 2
