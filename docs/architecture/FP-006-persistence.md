# FP-006: SQLite event store and session projection

Implements the consistency decision in [ADR-008](ADR-008-persistence-consistency.md).
The store is explicitly opened by an application caller; importing modules or loading
configuration does not open a database. No REST/WebSocket routes change in this packet.

## Configuration and ownership

| Setting / environment variable | Default | Meaning |
| --- | --- | --- |
| `persistence.database_path` / `ATC_PERSISTENCE_DATABASE_PATH` | `null` | Use `paths.data_root/sessions.sqlite3`; an override must be an absolute local file path |
| `persistence.migration_mode` / `ATC_PERSISTENCE_MIGRATION_MODE` | `apply` | Apply the initial schema to an empty database, or `validate` an existing compatible schema |
| `persistence.busy_timeout_ms` / `ATC_PERSISTENCE_BUSY_TIMEOUT_MS` | `1000` | SQLite lock wait, bounded to 0–30000 ms; no application retry loop |

Database paths are redacted from configuration reports. Effective settings, including
persistence settings, contribute to the configuration hash. `null` can reset the
environment path override. Parent directories must already exist; the store does not
create directories or select a model-storage location. Use a dedicated local data
directory, not a model asset directory or network/mapped share. Lexical path checks
reject UNC paths but cannot establish the physical storage behind a mapped drive.

```python
from packages.infrastructure.configuration import load_settings
from packages.infrastructure.persistence.sqlite import SQLiteEventStore

settings = load_settings()
with SQLiteEventStore(
    settings.database_path(),
    migration_mode=settings.persistence.migration_mode,
    busy_timeout_ms=settings.persistence.busy_timeout_ms,
) as store:
    current = store.get_session("session-id")
```

One connection belongs to one thread. Use one application writer; separate instances
may query committed state while that writer holds a transaction. Opening an instance
also performs recovery and briefly takes a write lock. Close all instances before
moving a database on Windows. There is no mutable live-state cache in this adapter.

## Atomic application boundary

`SessionUnitOfWork.commit(WriteRequest, build)` acquires `BEGIN IMMEDIATE`, checks the
durable retry key before the expected aggregate version, then supplies the next event
sequence to `build`. The builder must be pure and return a nonempty immutable batch:
no publication, adapters, filesystem I/O or live-state mutation. A caller supplies all
semantic command input to `WriteRequest.semantic_input_json`; transport retry metadata
and generated event IDs do not belong there. The canonical fingerprint includes command
type, session ID, expected aggregate version and the semantic JSON object.

The batch, full session projection, request event range and outbox rows commit together.
Only a successful return permits the caller to install state or acknowledge success.
The returned result contains the original events and session state at the request's
last sequence, including when a retry follows later session changes. Sequence numbers
and aggregate versions remain separate concepts. Event JSON retains all FP-004 fields;
serialization normalizes JSON formatting, without removing envelope metadata.

The FP-004 `append` port supports externally prepared batches: compare the actual tail
under the same lock and atomically append with projection and outbox intent. An exact
retry of an already committed range is a no-op. Changed payloads/IDs, partial overlaps,
stale tails and globally reused event IDs conflict. Use `commit` for command-level
idempotency. No independent authoritative session-write API exists.

`pending(session_id)` returns committed publication intent in sequence order. A future
dispatcher must stop on the first send failure and call `mark_dispatched` only after
successful delivery. Marking cannot skip an earlier pending event. A crash after send
but before marking leaves the intent pending: consumers must deduplicate event IDs and
sequences. An outbox flag does not prove every client received an event. Actual sockets,
adapter actions and their idempotency protocols remain outside FP-006.

## Schema and migration

The packaged migration is `packages/infrastructure/persistence/migrations/001_initial.sql`.
[The generated schema dump](FP-006-schema.sql) records its SQLite schema.

| Table | Authority / purpose |
| --- | --- |
| `events` | Immutable event JSON, global event ID and unique `(session_id, sequence)` |
| `sessions` | Rebuildable full session document, source sequence and projection version |
| `requests` | Durable retry fingerprint and original event range; retained with history |
| `outbox` | Durable publication intent and delivery state, referencing event IDs |
| `schema_migrations` | Applied version and shipped SQL checksum |

WAL, foreign keys and `synchronous=FULL` are verified before migration/recovery writes.
Migration DDL and version metadata use one explicit transaction. A failed initial
migration leaves an empty, retryable database. Existing table/index definitions and
migration checksums must match the shipped schema; unrelated, modified and newer schemas
are rejected. `validate` never creates a missing database, but still rebuilds derived
projections and configures WAL: it is not a forensic read-only mode.

There is no automatic retention, event pruning, downgrade or deletion of history.
SQLite's default automatic WAL checkpoint remains enabled. Keep transactions short;
long-lived readers can postpone checkpoints and grow the WAL. See the official
[WAL guidance](https://www.sqlite.org/wal.html).

## Recovery and failures

Opening the store validates SQLite integrity, durable foreign-key references, event
schemas, indexed IDs/session/sequences, contiguous history, legal aggregate transitions,
request fingerprints/ranges and presence of outbox intent. Only after those checks does
one transaction rebuild the derived `sessions` table. Missing or corrupt derived rows
are repairable; authoritative event, request and outbox records are never rewritten
by recovery. `read_after` validates a session's retained history before returning a
cursor slice. This initial implementation reconstructs full history, prioritizing
correctness over large-session query performance; snapshots and replay are non-goals.

Validation/conflict errors reject candidates without degrading the store. `StoreBusy`
means no success acknowledgement; the caller may retry later. Database write/commit
errors raise `PersistenceError`, roll back when possible and gate further mutation
and publication. Recover explicitly after resolving a known rolled-back write failure.
If a commit error leaves no active transaction, the adapter closes the uncertain
connection: reopen and retry the same request key to resolve its durable outcome.
Surface these exceptions as an out-of-band health failure; do not attempt a dependent
`session.failed` write while persistence is unavailable.

Invalid authoritative history blocks recovery and preserves its rows. Stop the writer
and dispatcher, preserve the database and companions for investigation, and restore a
verified compatible backup into a **new** location if recovery is required. AB-04 remains
open: this packet does not authorize replay or salvage of a valid prefix.

## Backup and rollback runbook

1. Stop new commands and dispatch. Record the application/schema version and data path.
2. Use SQLite's online backup API to a new destination, or stop all processes, close
   every connection and take a consistent offline copy. Never copy only the live main
   database while leaving behind its `-wal`/`-shm` companions. Never manually delete WAL.
3. Verify the backup in an isolated directory using the matching application version:
   schema validation, integrity check, event counts, full recovery and projection
   comparison. Keep the original backup unchanged; validation/recovery may write to
   the verification copy. Python's [backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)
   produces a coherent destination database while the source is in use.
4. Before a future migration, retain that verified backup. FP-006 introduces schema 1;
   it has no destructive downgrade. To roll back the application, preserve newer data
   and point the compatible application at a restored backup in a new directory.
   Explicitly reconcile any events newer than the backup; do not overwrite them.

## Evidence and limits

`tests/backend/test_sqlite_persistence.py` covers migration on empty/existing databases,
DDL rollback, multi-event commits, exact/conflicting retries, global IDs, tail/version
conflicts, reducer consistency and all terminal outcomes, four injected write failures,
denied and uncertain commit acknowledgement, corruption gates, projection reconstruction,
WAL readers, lock timeout, outbox ordering, configuration and Windows handle release.
Child processes exit before commit, after commit and after simulated send-before-mark.
Restart checks resolve the original request and compare rebuilt state with live state.

These deterministic tests do not certify physical power-loss durability, disk/media
failures, real sockets or model adapters. No real model assets are used. The FP-005
decision proof remains a separate historical test suite.
