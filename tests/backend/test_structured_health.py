import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.factory import create_app
from packages.application.health import HealthRegistry, SessionHealthContext
from packages.application.persistence import project_session
from packages.domain.events import DomainEvent
from packages.domain.health import (
    ComponentHealth,
    HealthReason,
    HealthSeverity,
    HealthStatus,
    MetricName,
    MetricObservation,
    readiness,
)
from packages.infrastructure.configuration import ConfigurationError, load_settings
from packages.infrastructure.persistence.sqlite import (
    PersistenceError,
    SQLiteEventStore,
    WriteConflict,
)
from packages.infrastructure.structured_logging import LogEvent, StructuredLog

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def healthy(component="database", required=True):
    return ComponentHealth(
        component=component,
        required=required,
        status=HealthStatus.HEALTHY,
        severity=HealthSeverity.INFO,
        reason=HealthReason.OPERATIONAL,
        observed_at=NOW,
    )


@pytest.mark.parametrize(
    "required,status,expected",
    [
        (True, HealthStatus.HEALTHY, HealthStatus.HEALTHY),
        (True, HealthStatus.DEGRADED, HealthStatus.DEGRADED),
        (True, HealthStatus.UNREADY, HealthStatus.UNREADY),
        (False, HealthStatus.UNREADY, HealthStatus.DEGRADED),
    ],
)
def test_health_aggregation(required, status, expected):
    component = healthy(required=required).model_copy(update={"status": status})
    assert readiness((component,)) == expected
    assert readiness(()) == HealthStatus.UNREADY


def test_registry_timeout_recovery_and_deduplication():
    current = [NOW]
    registry = HealthRegistry(10, clock=lambda: current[0])
    registry.register("database")
    correlation = uuid4()
    assert registry.report(
        "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
    )
    assert not registry.report(
        "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
    )
    current[0] += timedelta(seconds=10)
    assert registry.snapshot()[0] == HealthStatus.UNREADY
    assert registry.snapshot()[1][0].reason == HealthReason.TIMEOUT
    registry.expire(correlation_id=correlation)
    assert registry.report(
        "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
    )
    assert registry.snapshot()[0] == HealthStatus.HEALTHY
    current[0] = NOW
    with pytest.raises(ValueError, match="backwards"):
        registry.report(
            "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
        )
    with pytest.raises(ValueError, match="registered"):
        registry.register("database")


@pytest.mark.parametrize(
    "field,value",
    [
        ("component", "secret/path"),
        ("reason", "raw secret exception"),
        ("severity", "error"),
        ("observed_at", datetime(2026, 9, 18)),
    ],
)
def test_health_contract_rejects_unsafe_or_inconsistent_fields(field, value):
    values = dict(healthy())
    values[field] = value
    with pytest.raises(ValidationError):
        ComponentHealth(**values)


def test_api_fake_required_failure_optional_failure_and_recovery():
    registry = HealthRegistry()
    registry.register("database")
    registry.register("optional_adapter", required=False)
    correlation = uuid4()
    app = create_app(load_settings(environ={}), health_registry=registry)
    with TestClient(app) as client:
        assert client.get("/health").json()["readiness"] == "unready"
        registry.report(
            "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
        )
        assert client.get("/health").json()["readiness"] == "degraded"
        registry.report(
            "optional_adapter",
            HealthStatus.HEALTHY,
            HealthReason.OPERATIONAL,
            correlation_id=correlation,
        )
        assert client.get("/health").json()["readiness"] == "healthy"
        registry.report(
            "database", HealthStatus.UNREADY, HealthReason.FAILED, correlation_id=correlation
        )
        result = client.get("/health")
        assert result.status_code == 200 and result.json()["readiness"] == "unready"
        registry.report(
            "database", HealthStatus.HEALTHY, HealthReason.OPERATIONAL, correlation_id=correlation
        )
        assert client.get("/health").json()["readiness"] == "healthy"


def test_request_logs_and_errors_are_correlated_without_sensitive_text(tmp_path):
    path = tmp_path / "app.jsonl"
    logger = StructuredLog(path=path)
    app = create_app(load_settings(environ={}), structured_log=logger)

    @app.get("/synthetic-failure")
    def fail():
        raise RuntimeError("private-transcript-password")

    correlation = str(uuid4())
    with TestClient(app) as client:
        good = client.get(
            "/health?password=private-query",
            headers={"X-Correlation-ID": correlation, "Authorization": "secret-token"},
        )
        assert good.headers["X-Correlation-ID"] == correlation
        bad = client.get(
            "/synthetic-failure", headers={"X-Correlation-ID": "private-transcript-password"}
        )
        assert bad.status_code == 500
        assert UUID(bad.headers["X-Correlation-ID"])
        assert bad.json()["correlation_id"] == bad.headers["X-Correlation-ID"]
        assert "private" not in bad.text
    content = path.read_text()
    assert "private" not in content and "secret-token" not in content
    records = [json.loads(line) for line in content.splitlines()]
    assert records[0]["correlation_id"] == correlation
    assert records[-1]["event"] == "request.failed"
    assert records[-1]["correlation_id"] == bad.headers["X-Correlation-ID"]
    assert records[-1]["metric"]["name"] == "request_duration_ms"


def test_structured_log_allowlist_rotation_level_and_close(tmp_path):
    path = tmp_path / "app.jsonl"
    logger = StructuredLog(path=path, max_bytes=300, backup_count=2)
    for _ in range(20):
        logger.emit(
            LogEvent.REQUEST_COMPLETED,
            correlation_id=uuid4(),
            transcript="private",
            audio=b"private",
            password="private",
            nested={"secret": "private"},
        )
    logger.close()
    files = sorted(tmp_path.iterdir())
    assert len(files) == 3
    for file in files:
        content = file.read_text()
        assert "private" not in content
        for line in content.splitlines():
            assert set(json.loads(line)) == {"timestamp", "event", "correlation_id"}
    path.rename(tmp_path / "closed.jsonl")
    muted = tmp_path / "muted.jsonl"
    logger = StructuredLog(level="ERROR", path=muted)
    logger.emit(LogEvent.REQUEST_COMPLETED, correlation_id=uuid4())
    logger.close()
    assert not muted.exists()


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_metric_values_must_be_finite_nonnegative(value):
    with pytest.raises(ValidationError):
        MetricObservation(name=MetricName.COMPONENT_LATENCY_MS, value=value)


def test_metric_hook_is_bounded():
    registry = HealthRegistry()
    for number in range(120):
        registry.observe_metric(
            MetricObservation(name=MetricName.COMPONENT_LATENCY_MS, value=float(number))
        )
    assert len(registry.metrics()) == 100
    assert registry.metrics()[0].value == 20


def created():
    return DomainEvent.model_validate_json(
        (Path(__file__).parents[1] / "fixtures/events/session.created.json").read_text()
    )


def test_session_health_persists_without_advancing_lifecycle_and_recovers(tmp_path):
    path = tmp_path / "db.sqlite3"
    event = created()
    correlation = uuid4()
    context = SessionHealthContext(event.session_id, 1, uuid4())
    with SQLiteEventStore(path) as store:
        store.append(event.session_id, 0, (event,))
        registry = HealthRegistry(clock=lambda: NOW, unit_of_work=store)
        registry.register("database")
        assert registry.report(
            "database",
            HealthStatus.HEALTHY,
            HealthReason.OPERATIONAL,
            correlation_id=correlation,
            session=context,
        )
        assert not registry.report(
            "database",
            HealthStatus.HEALTHY,
            HealthReason.OPERATIONAL,
            correlation_id=correlation,
            session=context,
        )
        events = store.read_after(event.session_id, 0)
        assert len(events) == 2 and events[-1].correlation_id == str(correlation)
        projection = store.get_session(event.session_id)
        assert projection.session == project_session((event,)).session
        assert projection.source_sequence == 2
        registry.report(
            "database",
            HealthStatus.UNREADY,
            HealthReason.FAILED,
            correlation_id=correlation,
            session=replace(context, idempotency_key=uuid4()),
        )
        assert store.get_session(event.session_id).session.version == 1
    with SQLiteEventStore(path) as reopened:
        assert len(reopened.read_after(event.session_id, 0)) == 3
        assert reopened.get_session(event.session_id).source_sequence == 3
        assert len(reopened.pending(event.session_id)) == 3


def test_session_health_failure_does_not_publish_candidate(tmp_path):
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:
        event = created()
        store.append(event.session_id, 0, (event,))
        registry = HealthRegistry(clock=lambda: NOW, unit_of_work=store)
        registry.register("database")
        before = registry.snapshot()
        store._connection.execute(
            "CREATE TEMP TRIGGER fail BEFORE INSERT ON events "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(PersistenceError):
            registry.report(
                "database",
                HealthStatus.HEALTHY,
                HealthReason.OPERATIONAL,
                correlation_id=uuid4(),
                session=SessionHealthContext(event.session_id, 1, uuid4()),
            )
        assert registry.snapshot() == before
        assert store._connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_durable_retry_after_restart(tmp_path):
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:
        event = created()
        store.append(event.session_id, 0, (event,))
        context = SessionHealthContext(event.session_id, 1, uuid4())
        for _ in range(2):
            registry = HealthRegistry(clock=lambda: NOW, unit_of_work=store)
            registry.register("database")
            registry.report(
                "database",
                HealthStatus.HEALTHY,
                HealthReason.OPERATIONAL,
                correlation_id=uuid4(),
                session=context,
            )
        assert len(store.read_after(event.session_id, 0)) == 2
        with pytest.raises(WriteConflict):
            registry.report(
                "database",
                HealthStatus.UNREADY,
                HealthReason.FAILED,
                correlation_id=uuid4(),
                session=context,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("logging", {"file_path": "relative.log"}),
        ("logging", {"backup_count": 0}),
        ("logging", {"max_bytes": 1}),
        ("health", {"timeout_seconds": 0}),
        ("health", {"timeout_seconds": float("inf")}),
    ],
)
def test_logging_health_configuration_validation(field, value):
    with pytest.raises(ConfigurationError):
        load_settings(environ={}, overrides={field: value})


def test_log_configuration_is_lexical_redacted_and_environment_driven(tmp_path):
    path = tmp_path / "private.jsonl"
    settings = load_settings(
        environ={
            "ATC_LOGGING_FILE_PATH": str(path),
            "ATC_LOGGING_BACKUP_COUNT": "2",
            "ATC_HEALTH_TIMEOUT_SECONDS": "5",
        }
    )
    assert settings.logging.backup_count == 2 and settings.health.timeout_seconds == 5
    assert "private.jsonl" not in json.dumps(settings.redacted_report())
    assert not path.exists()
    assert load_settings(environ={"ATC_LOGGING_FILE_PATH": "null"}).logging.file_path is None


def test_file_log_failure_degrades_health_without_leaking_path(tmp_path, capsys):
    logger = StructuredLog(path=tmp_path / "private-directory" / "app.jsonl")
    app = create_app(load_settings(environ={}), structured_log=logger)
    with TestClient(app) as client:
        client.get("/health")
        result = client.get("/health")
    assert result.status_code == 200
    assert result.json()["readiness"] == "degraded"
    assert "private-directory" not in result.text + capsys.readouterr().err


def test_session_timeout_events_use_distinct_keys_for_components(tmp_path):
    now = [NOW]
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:
        event = created()
        store.append(event.session_id, 0, (event,))
        registry = HealthRegistry(5, clock=lambda: now[0], unit_of_work=store)
        for component in ("database", "simulation"):
            registry.register(component)
        now[0] += timedelta(seconds=5)
        registry.expire(
            correlation_id=uuid4(), session=SessionHealthContext(event.session_id, 1, uuid4())
        )
        assert len(store.read_after(event.session_id, 0)) == 3
        assert all(
            event.payload.health.reason == HealthReason.TIMEOUT
            for event in store.read_after(event.session_id, 1)
        )


def test_health_canonical_projection_excludes_observation_wall_time():
    from packages.domain.events import ComponentHealthChangedPayload

    payload = ComponentHealthChangedPayload(previous_status=None, health=healthy())
    changed = ComponentHealthChangedPayload(
        previous_status=None,
        health=healthy().model_copy(update={"observed_at": NOW + timedelta(seconds=1)}),
    )
    assert payload.canonical_fields() == changed.canonical_fields()


def test_old_health_retry_cannot_restore_stale_state(tmp_path):
    with SQLiteEventStore(tmp_path / "db.sqlite3") as store:
        event = created()
        store.append(event.session_id, 0, (event,))
        original = SessionHealthContext(event.session_id, 1, uuid4())
        registry = HealthRegistry(clock=lambda: NOW, unit_of_work=store)
        registry.register("database")
        registry.report(
            "database",
            HealthStatus.HEALTHY,
            HealthReason.OPERATIONAL,
            correlation_id=uuid4(),
            session=original,
        )
        registry.report(
            "database",
            HealthStatus.UNREADY,
            HealthReason.FAILED,
            correlation_id=uuid4(),
            session=replace(original, idempotency_key=uuid4()),
        )
        for active_registry in (registry, HealthRegistry(clock=lambda: NOW, unit_of_work=store)):
            if not active_registry.snapshot()[1]:
                active_registry.register("database")
            assert not active_registry.report(
                "database",
                HealthStatus.HEALTHY,
                HealthReason.OPERATIONAL,
                correlation_id=uuid4(),
                session=original,
            )
            assert active_registry.snapshot()[1][0].reason == HealthReason.FAILED
        assert len(store.read_after(event.session_id, 0)) == 3
        with pytest.raises(WriteConflict):
            registry.report(
                "database",
                HealthStatus.UNREADY,
                HealthReason.FAILED,
                correlation_id=uuid4(),
                session=original,
            )


def test_published_health_example_round_trips():
    path = Path(__file__).parents[1] / "fixtures/events/component.health_changed.json"
    event = DomainEvent.model_validate_json(path.read_text())
    assert event.event_type.value == "component.health_changed"
    assert json.loads(event.model_dump_json()) == json.loads(path.read_text())
