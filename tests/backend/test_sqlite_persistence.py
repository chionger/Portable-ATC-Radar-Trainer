"""Production persistence contracts; all storage is temporary synthetic data."""

import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from packages.application.persistence import WriteRequest, project_session
from packages.domain.events import DomainEvent
from packages.infrastructure.configuration import ConfigurationError, load_settings
from packages.infrastructure.persistence.sqlite import (
    IntegrityError,
    PersistenceError,
    SQLiteEventStore,
    StoreBusy,
    WriteConflict,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/events"


@pytest.fixture
def history() -> tuple[DomainEvent, ...]:
    return tuple(
        DomainEvent.model_validate_json((FIXTURES / f"session.{name}.json").read_text())
        for name in (
            "created",
            "initialising",
            "ready",
            "started",
            "paused",
            "resumed",
            "completed",
        )
    )


def request(version: int = 0, key: str = "request-1") -> WriteRequest:
    return WriteRequest(
        "session-fixture", key, "prepare-session", version, '{"scenario":"approach","seed":42}'
    )


def sql(path: Path, statement: str, args: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        result = connection.execute(statement, args).fetchall()
        connection.commit()
        return result
    finally:
        connection.close()


def test_batch_restart_projection_cursor_and_pragmas(tmp_path: Path, history) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:
        assert store.get_session("absent") is None
        store.append("session-fixture", 0, history[:3])
        store.append("session-fixture", 3, history[3:])
        assert store.get_session("session-fixture") == project_session(history)
        assert store.read_after("session-fixture", 4) == history[4:]
        assert store._connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert store._connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert store._connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with SQLiteEventStore(path, migration_mode="validate") as reopened:
        assert reopened.read_after("session-fixture", 0) == history
        assert reopened.get_session("session-fixture") == project_session(history)
    # Closed handles release the database on Windows.
    renamed = path.with_name("closed.sqlite3")
    path.rename(renamed)
    assert renamed.exists()


def test_retry_returns_original_multi_event_result_after_advance(tmp_path: Path, history) -> None:
    path = tmp_path / "events.sqlite3"
    calls = []

    def build(sequence):
        calls.append(sequence)
        return history[:3]

    with SQLiteEventStore(path) as store:
        original = store.commit(request(), build)
        store.append("session-fixture", 3, history[3:])
    with SQLiteEventStore(path) as store:
        assert store.commit(request(), build) == original
        assert calls == [1]
        assert store.get_session("session-fixture") == project_session(history)
        with pytest.raises(WriteConflict, match="different input"):
            store.commit(replace(request(), semantic_input_json='{"seed":43}'), build)
        with pytest.raises(WriteConflict, match="version"):
            store.commit(request(0, "new-key"), build)
        assert len(sql(path, "SELECT * FROM requests")) == 1


def test_append_duplicate_and_conflicting_ids(tmp_path: Path, history) -> None:
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        store.append("session-fixture", 0, history[:3])
        store.append("session-fixture", 0, history[:1])
        assert store.read_after("session-fixture", 0) == history[:3]
        with pytest.raises(WriteConflict):
            store.append(
                "session-fixture", 0, (history[0].model_copy(update={"event_id": "other"}),)
            )
        other = history[0].model_copy(update={"session_id": "another-session"})
        with pytest.raises(WriteConflict, match="identity"):
            store.append("another-session", 0, (other,))
        assert store.get_session("another-session") is None


@pytest.mark.parametrize("table", ["events", "sessions", "requests", "outbox"])
@pytest.mark.parametrize("prefix", [0, 1])
def test_injected_write_failure_rolls_back_every_table_and_gates_store(
    tmp_path: Path, history, table, prefix
) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:
        if prefix:
            store.commit(request(), lambda sequence: history[:prefix])
        candidate = request(prefix, "candidate")
        before = {
            target: sql(path, f"SELECT * FROM {target}")
            for target in ("events", "sessions", "requests", "outbox")
        }
        store._connection.execute(
            f"CREATE TEMP TRIGGER fail BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(PersistenceError, match="recovery"):
            store.commit(candidate, lambda sequence: history[prefix:3])
        for target in ("events", "sessions", "requests", "outbox"):
            assert sql(path, f"SELECT * FROM {target}") == before[target]
        for operation in (
            lambda: store.append("session-fixture", 0, history[:1]),
            lambda: store.pending("session-fixture"),
            lambda: store.mark_dispatched(history[0].event_id),
        ):
            with pytest.raises(PersistenceError, match="recovery"):
                operation()
        store._connection.execute("DROP TRIGGER fail")
        store.recover()
        assert (
            store.commit(candidate, lambda sequence: history[prefix:3]).projection.source_sequence
            == 3
        )


def test_commit_error_rolls_back_and_requires_recovery(tmp_path: Path, history) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:

        def authorize(action, name, *rest):
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and name == "COMMIT"
                else sqlite3.SQLITE_OK
            )

        store._connection.set_authorizer(authorize)
        with pytest.raises(PersistenceError):
            store.commit(request(), lambda sequence: history[:1])
        store._connection.set_authorizer(None)
        assert sql(path, "SELECT count(*) FROM events") == [(0,)]
        store.recover()
        store.commit(request(), lambda sequence: history[:1])


def test_busy_writer_and_wal_reader_see_only_committed_state(tmp_path: Path, history) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as first, SQLiteEventStore(path, busy_timeout_ms=10) as second:
        first.append("session-fixture", 0, history[:1])
        first._connection.execute("BEGIN IMMEDIATE")
        try:
            first._append("session-fixture", 1, history[1:3], history[:1])
            assert second.read_after("session-fixture", 0) == history[:1]
            assert second.get_session("session-fixture") == project_session(history[:1])
            with pytest.raises(StoreBusy):
                second.append("session-fixture", 1, history[1:3])
        finally:
            first._connection.execute("ROLLBACK")
        second.append("session-fixture", 1, history[1:3])
        with pytest.raises(WriteConflict):
            first.append(
                "session-fixture",
                1,
                history[1:2] + (history[2].model_copy(update={"event_id": "stale"}),),
            )


@pytest.mark.parametrize(
    "damage",
    [
        "DELETE FROM sessions",
        "UPDATE sessions SET document='broken'",
        "UPDATE sessions SET projection_version='old'",
        "UPDATE sessions SET source_sequence=999",
    ],
)
def test_recovery_rebuilds_derived_projection_only(tmp_path: Path, history, damage) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:
        store.commit(request(), lambda sequence: history)
    before = sql(path, "SELECT * FROM events")
    sql(path, damage)
    with SQLiteEventStore(path) as store:
        assert store.get_session("session-fixture") == project_session(history)
    assert sql(path, "SELECT * FROM events") == before


@pytest.mark.parametrize(
    "damage",
    [
        "UPDATE events SET document='broken' WHERE sequence=2",
        "UPDATE events SET event_id='wrong' WHERE sequence=2",
        "DELETE FROM events WHERE sequence=2",
        "DELETE FROM outbox WHERE event_id=(SELECT event_id FROM events WHERE sequence=2)",
        "UPDATE requests SET fingerprint='{}'",
    ],
)
def test_invalid_authority_blocks_recovery_without_rewriting_bytes(
    tmp_path: Path, history, damage
) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:
        store.commit(request(), lambda sequence: history[:3])
    sql(path, damage)
    before = sql(path, "SELECT * FROM events")
    with pytest.raises(IntegrityError):
        SQLiteEventStore(path)
    assert sql(path, "SELECT * FROM events") == before


def test_outbox_order_restart_and_duplicate_mark(tmp_path: Path, history) -> None:
    path = tmp_path / "events.sqlite3"
    with SQLiteEventStore(path) as store:
        store.append("session-fixture", 0, history[:3])
        with pytest.raises(WriteConflict):
            store.mark_dispatched(history[1].event_id)
        assert store.pending("session-fixture") == history[:3]
        store.mark_dispatched(history[0].event_id)
        store.mark_dispatched(history[0].event_id)
    with SQLiteEventStore(path) as store:
        assert store.pending("session-fixture") == history[1:3]
        # Reading/sending without marking leaves the same pending event after retry.
        assert store.pending("session-fixture") == history[1:3]


@pytest.mark.parametrize(
    "damage",
    [
        "UPDATE schema_migrations SET version=2",
        "UPDATE schema_migrations SET checksum='changed'",
        "DROP INDEX pending_outbox",
    ],
)
def test_incompatible_existing_migration_is_preserved(tmp_path: Path, damage) -> None:
    path = tmp_path / "events.sqlite3"
    SQLiteEventStore(path).close()
    sql(path, damage)
    before = path.read_bytes()
    with pytest.raises(IntegrityError):
        SQLiteEventStore(path)
    assert path.read_bytes() == before


def test_validate_mode_does_not_create_and_unknown_database_is_preserved(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteEventStore(missing, migration_mode="validate")
    assert not missing.exists()
    unknown = tmp_path / "unrelated.sqlite3"
    sql(unknown, "CREATE TABLE user_data (value TEXT)")
    before = unknown.read_bytes()
    with pytest.raises(IntegrityError):
        SQLiteEventStore(unknown)
    assert unknown.read_bytes() == before


@pytest.mark.parametrize("phase", ["before_commit", "after_commit", "after_send"])
def test_process_exit_recovery(tmp_path: Path, history, phase) -> None:
    path = tmp_path / "events.sqlite3"
    script = """
import os, sys
from pathlib import Path
from packages.domain.events import DomainEvent
from packages.application.persistence import WriteRequest
from packages.infrastructure.persistence.sqlite import SQLiteEventStore
store = SQLiteEventStore(Path(sys.argv[1]))
event = DomainEvent.model_validate_json(Path(sys.argv[2]).read_text())
if sys.argv[3] == "before_commit":
    def crash(action, name, *rest):
        if action == 22 and name == "COMMIT": os._exit(17)
        return 0
    store._connection.set_authorizer(crash)
store.commit(WriteRequest("session-fixture", "request-1", "prepare-session", 0,
    '{"scenario":"approach","seed":42}'), lambda sequence: (event,))
if sys.argv[3] == "after_send":
    assert store.pending("session-fixture") == (event,)
os._exit(17)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(path), str(FIXTURES / "session.created.json"), phase],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 17, child.stderr
    with SQLiteEventStore(path) as store:
        assert store.read_after("session-fixture", 0) == (
            history[:1] if phase != "before_commit" else ()
        )
        assert store.commit(request(), lambda sequence: history[:1]).events == history[:1]
        assert store.pending("session-fixture") == history[:1]


def test_candidate_validation_does_not_poison_healthy_store(tmp_path: Path, history) -> None:
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        with pytest.raises(ValueError):
            store.append(
                "session-fixture", 0, (history[0].model_copy(update={"schema_version": "bad"}),)
            )
        with pytest.raises(ValueError):
            store.append("session-fixture", 0, history[:1] + history[2:3])
        store.append("session-fixture", 0, history[:1])


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_path", "relative.sqlite3"),
        ("database_path", "//server/share/db"),
        ("migration_mode", "delete"),
        ("busy_timeout_ms", -1),
        ("busy_timeout_ms", True),
        ("busy_timeout_ms", 30001),
    ],
)
def test_persistence_configuration_rejects_invalid_settings(field, value) -> None:
    with pytest.raises(ConfigurationError):
        load_settings(environ={}, overrides={"persistence": {field: value}})


def test_persistence_configuration_environment_defaults_and_redaction(tmp_path: Path) -> None:
    default = load_settings(environ={})
    assert default.database_path() == Path(default.paths.data_root) / "sessions.sqlite3"
    private = tmp_path / "private.sqlite3"
    configured = load_settings(
        environ={
            "ATC_PERSISTENCE_DATABASE_PATH": str(private),
            "ATC_PERSISTENCE_MIGRATION_MODE": "validate",
            "ATC_PERSISTENCE_BUSY_TIMEOUT_MS": "50",
        }
    )
    assert configured.database_path() == private
    assert configured.persistence.busy_timeout_ms == 50
    assert "private.sqlite3" not in json.dumps(configured.redacted_report())
    assert configured.configuration_hash() != default.configuration_hash()
    assert not private.exists()


@pytest.mark.parametrize("semantic", ['{"x":1,"x":2}', '{"x":NaN}', "[]"])
def test_request_fingerprint_rejects_ambiguous_json(semantic) -> None:
    with pytest.raises(ValueError):
        replace(request(), semantic_input_json=semantic).fingerprint()


def test_request_fingerprint_is_order_independent() -> None:
    assert (
        replace(request(), semantic_input_json='{"seed":42, "scenario":"approach"}').fingerprint()
        == request().fingerprint()
    )


def test_uncertain_commit_reopens_and_resolves_durable_key(
    tmp_path: Path, history, monkeypatch
) -> None:
    class AmbiguousConnection(sqlite3.Connection):
        fail_commit = False

        def execute(self, statement, parameters=()):
            result = super().execute(statement, parameters)
            if statement == "COMMIT" and self.fail_commit:
                self.fail_commit = False
                raise sqlite3.OperationalError("simulated lost commit acknowledgement")
            return result

    original = sqlite3.connect

    def connect(*args, **kwargs):
        return original(*args, **kwargs, factory=AmbiguousConnection)

    path = tmp_path / "events.sqlite3"
    with monkeypatch.context() as context:
        context.setattr(sqlite3, "connect", connect)
        with SQLiteEventStore(path) as store:
            store._connection.fail_commit = True
            with pytest.raises(PersistenceError):
                store.commit(request(), lambda sequence: history[:3])
            with pytest.raises(PersistenceError, match="reopened"):
                store.recover()

    def forbidden(sequence):
        raise AssertionError("retry must use the durable result")

    with SQLiteEventStore(path) as reopened:
        assert reopened.commit(request(), forbidden).events == history[:3]


@pytest.mark.parametrize("terminal", ["completed", "stopped", "failed"])
def test_reducer_terminal_fields_and_history_consistency(history, terminal) -> None:
    event = DomainEvent.model_validate_json((FIXTURES / f"session.{terminal}.json").read_text())
    projection = project_session(history[:6] + (event,))
    assert projection.session.outcome.value == terminal.upper()
    assert projection.session.ended_at == event.wall_time_utc
    assert (projection.session.failure is not None) == (terminal == "failed")
    wrong = history[4].model_copy(
        update={
            "payload": history[4].payload.model_copy(update={"previous_version": 3, "version": 4})
        }
    )
    with pytest.raises(ValueError, match="committed aggregate"):
        project_session(history[:4] + (wrong,))


def test_migration_failure_is_atomic_and_retryable(tmp_path: Path, monkeypatch) -> None:
    original = sqlite3.connect

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        if args[0] != ":memory:":

            def deny(action, name, *rest):
                if action == sqlite3.SQLITE_CREATE_TABLE and name == "sessions":
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            connection.set_authorizer(deny)
        return connection

    path = tmp_path / "events.sqlite3"
    with monkeypatch.context() as context:
        context.setattr(sqlite3, "connect", connect)
        with pytest.raises(sqlite3.DatabaseError):
            SQLiteEventStore(path)
    assert sql(path, "SELECT name FROM sqlite_master WHERE type='table'") == []
    with SQLiteEventStore(path) as store:
        assert store.read_after("absent", 0) == ()


def test_sequence_builder_uses_current_tail_and_rollback_does_not_reserve(
    tmp_path: Path, history
) -> None:
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        calls = []

        def build(sequence):
            calls.append(sequence)
            return history[sequence - 1 : sequence]

        store.commit(request(), build)
        assert store.commit(request(1, "second"), build).events == history[1:2]
        assert calls == [1, 2]
        with pytest.raises(ValueError):
            store.commit(request(2, "bad"), lambda sequence: ())
        assert store.commit(request(2, "third"), build).events == history[2:3]
        assert calls == [1, 2, 3]
