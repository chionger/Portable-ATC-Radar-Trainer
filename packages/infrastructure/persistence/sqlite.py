"""Single-writer SQLite event repository and session unit of work.

No connection or filesystem access occurs until explicitly constructed. Each store
is confined to its owning thread; separate instances may read concurrently in WAL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import Literal

from pydantic import TypeAdapter

from packages.application.events import validate_append_batch
from packages.application.persistence import (
    PROJECTION_VERSION,
    CommitResult,
    EventBuilder,
    SessionProjection,
    WriteRequest,
    project_session,
)
from packages.domain.events import DomainEvent
from packages.domain.session import Session
from packages.infrastructure.configuration.settings import absolute_local_path

SESSION_ADAPTER = TypeAdapter(Session)


class PersistenceError(RuntimeError):
    """Persistence unavailable: pause mutations and dependent publication."""


class IntegrityError(PersistenceError):
    """Authoritative history or database structure cannot be trusted."""


class StoreBusy(PersistenceError):
    """Bounded lock timeout; caller may retry without acknowledging success."""


class WriteConflict(ValueError):
    """Stale candidate or reuse of an identity with different input."""


def _document(event: DomainEvent) -> str:
    validated = DomainEvent.model_validate_json(event.model_dump_json())
    return json.dumps(
        validated.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


class SQLiteEventStore:
    def __init__(
        self,
        database_path: Path,
        *,
        migration_mode: Literal["apply", "validate"] = "apply",
        busy_timeout_ms: int = 1000,
    ) -> None:
        absolute_local_path(str(database_path))
        if not database_path.is_absolute():
            raise ValueError("database path must be native and absolute")
        if migration_mode not in {"apply", "validate"}:
            raise ValueError("unsupported migration mode")
        if type(busy_timeout_ms) is not int or not 0 <= busy_timeout_ms <= 30000:
            raise ValueError("busy timeout must be 0..30000 milliseconds")
        self._healthy = False
        self._closed = False
        # No implicit directory creation. Validate never creates a missing database.
        uri = database_path.as_uri() + ("?mode=rwc" if migration_mode == "apply" else "?mode=rw")
        self._connection = sqlite3.connect(
            uri, uri=True, timeout=busy_timeout_ms / 1000, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        try:
            self._check_migration(migration_mode)
            self.recover()
        except BaseException:
            self.close()
            raise

    def _check_migration(self, mode: str) -> None:
        script = (
            files(__package__).joinpath("migrations/001_initial.sql").read_text(encoding="utf-8")
        )
        checksum = hashlib.sha256(script.encode()).hexdigest()
        statements = [part.strip() for part in script.split(";") if part.strip()]
        # Compare actual schema with the shipped migration, including constraints.
        with closing(sqlite3.connect(":memory:")) as reference:
            for statement in statements:
                reference.execute(statement)
            expected = reference.execute(
                "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()

        def existing_schema() -> bool:
            actual = self._connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()
            if not actual and mode == "apply":
                return False
            if [tuple(row) for row in actual] != expected:
                raise IntegrityError(
                    "unknown or incompatible database schema; restore compatible backup"
                )
            versions = self._connection.execute(
                "SELECT version, checksum FROM schema_migrations"
            ).fetchall()
            if [tuple(row) for row in versions] != [(1, checksum)]:
                raise IntegrityError("unsupported or altered migration history")
            return True

        # Reject unrelated/newer databases before changing their journal mode.
        existing_schema()
        if self._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise PersistenceError("WAL unavailable")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA synchronous=FULL")
        if (
            self._connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1
            or self._connection.execute("PRAGMA synchronous").fetchone()[0] != 2
        ):
            raise PersistenceError("required SQLite durability settings unavailable")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            # Recheck after taking the lock; a competing first opener may have migrated.
            if not existing_schema():
                for statement in statements:
                    self._connection.execute(statement)
                self._connection.execute("INSERT INTO schema_migrations VALUES (1, ?)", (checksum,))
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _ready(self) -> None:
        if self._closed or not self._healthy:
            raise PersistenceError("store requires successful recovery before use")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            if error.sqlite_errorcode & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise StoreBusy("writer busy; request was not committed") from error
            self._healthy = False
            raise PersistenceError("cannot begin transaction") from error
        committing = False
        try:
            yield
            committing = True
            self._connection.execute("COMMIT")
        except BaseException as error:
            if isinstance(error, sqlite3.Error | IntegrityError):
                self._healthy = False
            try:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                elif committing and isinstance(error, sqlite3.Error):
                    # COMMIT may have reached disk. Resolve the durable key using
                    # a fresh connection before allowing any further work.
                    self.close()
            except sqlite3.Error:
                self.close()
            if isinstance(error, sqlite3.Error):
                raise PersistenceError("transaction failed; recovery required") from error
            raise

    def _history(self, session_id: str | None = None) -> tuple[DomainEvent, ...]:
        sql = "SELECT event_id, session_id, sequence, document FROM events"
        arguments: tuple[str, ...] = ()
        if session_id is not None:
            sql += " WHERE session_id=?"
            arguments = (session_id,)
        rows = self._connection.execute(sql + " ORDER BY session_id, sequence", arguments)
        result = []
        try:
            for row in rows:
                event = DomainEvent.model_validate_json(row["document"])
                if (event.event_id, event.session_id, event.sequence) != tuple(row)[:3]:
                    raise ValueError("indexed event metadata differs from document")
                result.append(event)
        except (ValueError, TypeError) as error:
            self._healthy = False
            raise IntegrityError("invalid authoritative event; original bytes preserved") from error
        return tuple(result)

    def _project(self, events: tuple[DomainEvent, ...]) -> SessionProjection:
        try:
            return project_session(events)
        except ValueError as error:
            self._healthy = False
            raise IntegrityError("invalid authoritative session history") from error

    def _save_projection(self, projection: SessionProjection) -> None:
        document = SESSION_ADAPTER.dump_json(projection.session).decode()
        self._connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "source_sequence=excluded.source_sequence, "
            "projection_version=excluded.projection_version, "
            "document=excluded.document",
            (
                projection.session.session_id,
                projection.source_sequence,
                PROJECTION_VERSION,
                document,
            ),
        )

    def recover(self) -> None:
        """Validate complete retained history, then atomically rebuild derived sessions."""
        if self._closed:
            raise PersistenceError("closed store must be reopened")
        self._healthy = False
        with self._transaction():
            if self._connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise IntegrityError("SQLite integrity check failed")
            if any(
                row[0] != "sessions" for row in self._connection.execute("PRAGMA foreign_key_check")
            ):
                raise IntegrityError("broken durable record references")
            histories: dict[str, list[DomainEvent]] = {}
            for event in self._history():
                histories.setdefault(event.session_id, []).append(event)
            projections = [self._project(tuple(history)) for history in histories.values()]
            if self._connection.execute(
                "SELECT 1 FROM events LEFT JOIN outbox USING(event_id) "
                "WHERE outbox.event_id IS NULL LIMIT 1"
            ).fetchone():
                raise IntegrityError("missing durable publication intent")
            for row in self._connection.execute("SELECT * FROM requests"):
                try:
                    fingerprint = json.loads(row["fingerprint"])
                    request = WriteRequest(
                        row["session_id"],
                        row["idempotency_key"],
                        fingerprint[0],
                        fingerprint[2],
                        json.dumps(fingerprint[3]),
                    )
                    if (
                        request.fingerprint() != row["fingerprint"]
                        or fingerprint[1] != row["session_id"]
                        or row["first_sequence"] > row["last_sequence"]
                    ):
                        raise ValueError("invalid request")
                    prefix = tuple(histories[row["session_id"]][: row["first_sequence"] - 1])
                    version = self._project(prefix).session.version if prefix else 0
                    if version != request.expected_version:
                        raise ValueError("request version differs from source history")
                except (ValueError, TypeError, IndexError, KeyError) as error:
                    raise IntegrityError("invalid durable request record") from error
            # Only derived rows are replaced. Event, request and outbox bytes stay intact.
            self._connection.execute("DELETE FROM sessions")
            for projection in projections:
                self._save_projection(projection)
        self._healthy = True

    def read_after(self, session_id: str, sequence: int) -> tuple[DomainEvent, ...]:
        self._ready()
        if type(sequence) is not int or sequence < 0:
            raise ValueError("cursor must be a non-negative integer")
        history = self._history(session_id)
        if history:
            self._project(history)
        return tuple(event for event in history if event.sequence > sequence)

    def get_session(self, session_id: str) -> SessionProjection | None:
        self._ready()
        row = self._connection.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            if row["projection_version"] != PROJECTION_VERSION:
                raise ValueError("incompatible projection")
            return SessionProjection(
                SESSION_ADAPTER.validate_json(row["document"]), row["source_sequence"]
            )
        except ValueError as error:
            self._healthy = False
            raise IntegrityError("projection requires recovery") from error

    def _append(
        self,
        session_id: str,
        tail: int,
        events: tuple[DomainEvent, ...],
        history: tuple[DomainEvent, ...],
    ) -> CommitResult:
        validate_append_batch(session_id, tail, events)
        documents = tuple(_document(event) for event in events)
        # Candidate errors reject without degrading the committed store.
        projection = project_session(history + events)
        for event, document in zip(events, documents, strict=True):
            if self._connection.execute(
                "SELECT 1 FROM events WHERE event_id=?", (event.event_id,)
            ).fetchone():
                raise WriteConflict("event identity already exists")
            self._connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (event.event_id, session_id, event.sequence, document),
            )
            self._connection.execute("INSERT INTO outbox(event_id) VALUES (?)", (event.event_id,))
        self._save_projection(projection)
        return CommitResult(events, projection)

    def append(
        self, session_id: str, expected_last_sequence: int, events: tuple[DomainEvent, ...]
    ) -> None:
        self._ready()
        validate_append_batch(session_id, expected_last_sequence, events)
        documents = tuple(_document(event) for event in events)
        with self._transaction():
            history = self._history(session_id)
            if history:
                self._project(history)
            prior = history[expected_last_sequence : expected_last_sequence + len(events)]
            if (
                len(prior) == len(events)
                and tuple(_document(event) for event in prior) == documents
            ):
                return
            if len(history) != expected_last_sequence:
                raise WriteConflict("session tail changed")
            self._append(session_id, expected_last_sequence, events, history)

    def commit(self, request: WriteRequest, build: EventBuilder) -> CommitResult:
        self._ready()
        fingerprint = request.fingerprint()
        with self._transaction():
            prior = self._connection.execute(
                "SELECT * FROM requests WHERE session_id=? AND idempotency_key=?",
                (request.session_id, request.idempotency_key),
            ).fetchone()
            history = self._history(request.session_id)
            if prior is not None:
                if prior["fingerprint"] != fingerprint:
                    raise WriteConflict("idempotency key has different input")
                prefix = history[: prior["last_sequence"]]
                return CommitResult(prefix[prior["first_sequence"] - 1 :], self._project(prefix))
            version = self._project(history).session.version if history else 0
            if version != request.expected_version:
                raise WriteConflict("aggregate version changed")
            events = build(len(history) + 1)
            result = self._append(request.session_id, len(history), events, history)
            self._connection.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?, ?)",
                (
                    request.session_id,
                    request.idempotency_key,
                    fingerprint,
                    len(history) + 1,
                    result.projection.source_sequence,
                ),
            )
        return result

    def pending(self, session_id: str) -> tuple[DomainEvent, ...]:
        """Committed intent in order. Caller stops on the first failed delivery."""
        self._ready()
        # One SELECT gives a consistent WAL snapshot of payload and delivery state.
        rows = self._connection.execute(
            "SELECT e.document FROM events e JOIN outbox o USING(event_id) "
            "WHERE e.session_id=? AND o.dispatched=0 ORDER BY e.sequence",
            (session_id,),
        ).fetchall()
        return tuple(DomainEvent.model_validate_json(row[0]) for row in rows)

    def mark_dispatched(self, event_id: str) -> None:
        self._ready()
        with self._transaction():
            row = self._connection.execute(
                "SELECT session_id, sequence FROM events WHERE event_id=?", (event_id,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown event")
            if self._connection.execute(
                "SELECT 1 FROM events e JOIN outbox o USING(event_id) WHERE e.session_id=? "
                "AND e.sequence<? AND o.dispatched=0 LIMIT 1",
                tuple(row),
            ).fetchone():
                raise WriteConflict("earlier publication intent is still pending")
            self._connection.execute("UPDATE outbox SET dispatched=1 WHERE event_id=?", (event_id,))

    def close(self) -> None:
        if not self._closed:
            self._healthy = False
            self._connection.close()
            self._closed = True

    def __enter__(self) -> SQLiteEventStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
