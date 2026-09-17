"""FP-005 executable decision proof, deliberately not a production repository."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from packages.domain.events import DomainEvent, SessionCreatedPayload

FIXTURES = Path(__file__).parents[1] / "fixtures/events"
TABLES = ("events", "projections", "snapshots", "requests", "outbox")


def event(name):
    return DomainEvent.model_validate_json(
        (FIXTURES / f"session.{name}.json").read_text(encoding="utf-8")
    )


class ProofStore:
    """Small synthetic unit of work; only session events and one-event requests."""

    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, timeout=0.1)
        assert self.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, session TEXT NOT NULL, sequence INTEGER NOT NULL,
                body TEXT NOT NULL, UNIQUE(session, sequence));
            CREATE TABLE IF NOT EXISTS projections (
                session TEXT PRIMARY KEY, sequence INTEGER NOT NULL,
                version TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (
                session TEXT PRIMARY KEY, sequence INTEGER NOT NULL,
                version TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (
                session TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                event_id TEXT NOT NULL REFERENCES events(id), PRIMARY KEY(session, key));
            CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY REFERENCES events(id), sent INTEGER NOT NULL DEFAULT 0);
        """)
        self.cache = {}
        self.healthy = False
        self.recover()

    def derive(self):
        states = {}
        for identity, sid, sequence, body in self.db.execute(
            "SELECT id, session, sequence, body FROM events ORDER BY session, sequence"
        ):
            item = DomainEvent.model_validate_json(body)
            if (identity, sid, sequence) != (item.event_id, item.session_id, item.sequence):
                raise ValueError("envelope/index mismatch")
            prior = states.get(sid)
            if sequence != (prior[0] + 1 if prior else 1):
                raise ValueError("history gap")
            payload = item.payload
            if isinstance(payload, SessionCreatedPayload):
                if prior:
                    raise ValueError("duplicate creation")
            elif prior is None or (payload.previous_state.value, payload.previous_version) != (
                prior[1]["state"],
                prior[1]["version"],
            ):
                raise ValueError("history transition mismatch")
            if prior and item.sim_time < prior[1]["sim_time"]:
                raise ValueError("simulation time regressed")
            states[sid] = (
                sequence,
                {
                    "state": payload.state.value,
                    "version": payload.version,
                    "sim_time": item.sim_time,
                },
            )
        return states

    def write_projection(self, sid, sequence, state):
        body = json.dumps(state, sort_keys=True)
        for table in ("projections", "snapshots"):
            self.db.execute(
                f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?)",
                (sid, sequence, "proof-1", body),
            )

    def recover(self):
        self.healthy = False
        self.db.execute("BEGIN IMMEDIATE")
        try:
            states = self.derive()
            # Rebuild disposable proof projections; event history is never rewritten.
            self.db.execute("DELETE FROM projections")
            self.db.execute("DELETE FROM snapshots")
            for sid, (sequence, state) in states.items():
                self.write_projection(sid, sequence, state)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.cache = states
        self.healthy = True

    def apply(self, item, key, crash=None):
        if not self.healthy:
            raise RuntimeError("persistence paused; recovery required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                "SELECT fingerprint, event_id FROM requests WHERE session=? AND key=?",
                (item.session_id, key),
            ).fetchone()
            if prior:
                if prior[0] != item.canonical_json():
                    raise ValueError("idempotency key reused for different input")
                self.db.execute("ROLLBACK")
                return prior[1]
            tail = self.db.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM events WHERE session=?", (item.session_id,)
            ).fetchone()[0]
            if item.sequence != tail + 1:
                raise ValueError("stale sequence")
            self.db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (item.event_id, item.session_id, item.sequence, item.model_dump_json()),
            )
            states = self.derive()
            self.write_projection(item.session_id, *states[item.session_id])
            self.db.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?)",
                (item.session_id, key, item.canonical_json(), item.event_id),
            )
            self.db.execute("INSERT INTO outbox(event_id) VALUES (?)", (item.event_id,))
            if crash == "before_commit":
                os._exit(71)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self.healthy = False
            raise
        if crash == "after_commit":
            os._exit(72)
        self.cache = states
        return item.event_id

    def publish(self, send, crash=None):
        if not self.healthy:
            raise RuntimeError("publication blocked until recovery")
        rows = self.db.execute("""
            SELECT e.id, e.body FROM outbox o JOIN events e ON e.id=o.event_id
            WHERE o.sent=0 ORDER BY e.session, e.sequence
        """).fetchall()
        for identity, body in rows:
            send(DomainEvent.model_validate_json(body))
            if crash == "after_send":
                os._exit(73)
            self.db.execute("UPDATE outbox SET sent=1 WHERE event_id=?", (identity,))


@pytest.fixture
def store(tmp_path):
    proof = ProofStore(tmp_path / "proof.sqlite")
    yield proof
    proof.db.close()


def counts(store):
    return tuple(
        store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES
    )


def test_happy_path_is_durable_before_cache_and_publication(store):
    store.apply(event("created"), "create")
    store.apply(event("initialising"), "initialize")
    assert counts(store) == (2, 1, 1, 2, 2)
    delivered = []

    def send(item):
        with sqlite3.connect(store.path) as observer:
            assert observer.execute("SELECT id FROM events WHERE id=?", (item.event_id,)).fetchone()
        assert store.cache[item.session_id][0] == 2
        delivered.append(item.sequence)

    store.publish(send)
    assert delivered == [1, 2]
    store.publish(send)
    assert delivered == [1, 2]


@pytest.mark.parametrize("table", TABLES)
def test_sql_write_failure_rolls_back_every_dependent_record(store, table):
    store.apply(event("created"), "create")
    before = counts(store)
    cache = dict(store.cache)
    store.db.execute(f"""CREATE TEMP TRIGGER fail_write BEFORE INSERT ON {table}
                       BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        store.apply(event("initialising"), "initialize")
    assert counts(store) == before
    assert store.cache == cache
    with pytest.raises(RuntimeError, match="blocked"):
        store.publish(lambda _: pytest.fail("must not publish"))
    store.db.execute("DROP TRIGGER fail_write")
    store.recover()
    store.apply(event("initialising"), "initialize")
    assert counts(store) == (2, 1, 1, 2, 2)


def test_commit_failure_rolls_back_and_pauses(store):
    store.apply(event("created"), "create")

    def deny_commit(action, first, second, database, source):
        if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    store.db.set_authorizer(deny_commit)
    with pytest.raises(sqlite3.DatabaseError):
        store.apply(event("initialising"), "initialize")
    store.db.set_authorizer(None)
    assert counts(store) == (1, 1, 1, 1, 1)
    assert not store.healthy
    store.recover()
    assert store.cache[event("created").session_id][0] == 1


def test_retry_returns_original_result_and_changed_input_conflicts(store):
    original = event("created")
    store.apply(original, "create")
    raw = json.loads(original.model_dump_json())
    raw.update(event_id="retry-id", wall_time_utc="2026-09-18T00:00:00Z")
    assert (
        store.apply(DomainEvent.model_validate_json(json.dumps(raw)), "create") == original.event_id
    )
    assert counts(store) == (1, 1, 1, 1, 1)
    raw["payload"]["seed"] = 99
    with pytest.raises(ValueError, match="idempotency"):
        store.apply(DomainEvent.model_validate_json(json.dumps(raw)), "create")
    assert counts(store) == (1, 1, 1, 1, 1)


def test_stale_writer_cannot_reuse_sequence(store):
    other = ProofStore(store.path)
    try:
        store.apply(event("created"), "one")
        with pytest.raises(ValueError, match="stale"):
            other.apply(event("created"), "two")
        assert counts(store) == (1, 1, 1, 1, 1)
    finally:
        other.db.close()


def test_writer_lock_prevents_parallel_allocation(store):
    other = sqlite3.connect(store.path, isolation_level=None)
    try:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.apply(event("created"), "create")
        assert counts(store) == (0, 0, 0, 0, 0)
    finally:
        other.execute("ROLLBACK")
        other.close()


def test_recovery_rebuilds_corrupt_projection_without_changing_history(store):
    store.apply(event("created"), "create")
    store.apply(event("initialising"), "initialize")
    original = store.db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
    store.db.execute("UPDATE projections SET body='invalid', sequence=100, version='obsolete'")
    store.db.execute("DELETE FROM snapshots")
    store.recover()
    assert store.cache[event("created").session_id][1]["state"] == "INITIALISING"
    assert store.db.execute("SELECT sequence, version FROM projections").fetchone() == (
        2,
        "proof-1",
    )
    assert store.db.execute("SELECT * FROM events ORDER BY sequence").fetchall() == original


def test_invalid_history_blocks_recovery_and_publication(store):
    store.apply(event("created"), "create")
    store.db.execute("UPDATE events SET body='{}'")
    with pytest.raises(ValueError):
        store.recover()
    with pytest.raises(RuntimeError):
        store.publish(lambda _: pytest.fail("invalid history published"))


def test_send_failure_preserves_pending_order_and_durable_state(store):
    store.apply(event("created"), "create")
    store.apply(event("initialising"), "initialize")
    attempted = []

    def fail(item):
        attempted.append(item.sequence)
        raise OSError("disconnected")

    with pytest.raises(OSError):
        store.publish(fail)
    assert attempted == [1]
    assert store.db.execute("SELECT SUM(sent) FROM outbox").fetchone()[0] == 0
    assert store.cache[event("created").session_id][0] == 2
    delivered = []
    store.publish(lambda item: delivered.append(item.sequence))
    assert delivered == [1, 2]


def test_retry_after_later_commit_does_not_rewind_session(store):
    store.apply(event("created"), "create")
    store.apply(event("initialising"), "initialize")
    assert store.apply(event("created"), "create") == event("created").event_id
    assert store.cache[event("created").session_id][0] == 2
    assert counts(store) == (2, 1, 1, 2, 2)


def test_unique_identity_and_foreign_keys_are_enforced(store):
    store.apply(event("created"), "create")
    raw = json.loads(event("initialising").model_dump_json())
    raw["event_id"] = event("created").event_id
    with pytest.raises(sqlite3.IntegrityError):
        store.apply(DomainEvent.model_validate_json(json.dumps(raw)), "initialize")
    assert counts(store) == (1, 1, 1, 1, 1)
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("INSERT INTO outbox(event_id) VALUES ('missing')")


def crash_worker(path, stage, delivery):
    proof = ProofStore(Path(path))
    if stage == "after_send":

        def send(item):
            with open(delivery, "a", encoding="utf-8") as output:
                output.write(item.event_id + "\n")
                output.flush()
                os.fsync(output.fileno())

        proof.publish(send, crash=stage)
    else:
        proof.apply(event("initialising"), "initialize", crash=stage)
    raise AssertionError("crash point not reached")


@pytest.mark.parametrize(
    "stage,exit_code,tail",
    [
        ("before_commit", 71, 1),
        ("after_commit", 72, 2),
        ("after_send", 73, 1),
    ],
)
def test_real_process_crash_recovery(store, tmp_path, stage, exit_code, tail):
    store.apply(event("created"), "create")
    delivery = tmp_path / "delivery.txt"
    store.db.close()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy,sys; runpy.run_path(sys.argv[1])['crash_worker'](*sys.argv[2:])",
            str(Path(__file__).resolve()),
            str(store.path),
            stage,
            str(delivery),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    restored = ProofStore(store.path)
    store.db = restored.db
    store.cache = restored.cache
    store.healthy = restored.healthy
    assert child.returncode == exit_code, child.stdout + child.stderr
    store.recover()
    assert store.cache[event("created").session_id][0] == tail
    assert counts(store) == (tail, 1, 1, tail, tail)
    delivered = []
    store.publish(lambda item: delivered.append(item.event_id))
    if stage == "after_send":
        assert delivery.read_text(encoding="utf-8").splitlines() == delivered
    if stage == "after_commit":
        assert store.apply(event("initialising"), "initialize") == event("initialising").event_id
        assert counts(store) == (2, 1, 1, 2, 2)
