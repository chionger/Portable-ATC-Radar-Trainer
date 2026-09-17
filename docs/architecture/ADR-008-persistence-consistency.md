# ADR-008: SQLite consistency, projections, snapshots and replay integrity

## Status and approval

**Consistency approved — FP-005, 2026-09-17. AB-01 resolved.**
AB-04 (failed-history replay
integrity policy) remains open and is not resolved by this decision proof.

| Role | Decision | Date / evidence |
| --- | --- | --- |
| Product owner | Approved by repository owner (chionger) | 2026-09-17; explicit approval in the FP-005 review conversation |
| Architecture owner | Approved by repository owner (chionger) | 2026-09-17; same explicit approval covering both roles |

Approval scope: the AB-01 consistency/recovery rules below and their use by FP-006.
The owner explicitly replied "approve" to the request for product/architecture
approval of the transaction-and-outbox decision. This approval does not close AB-04.

## Context

Architecture baseline v1.0 sections 16.4, 19, 22, 28.4 and 31 require SQLite
authoritative event history and publication after durability, but leave the atomic
relationship between domain state, events and projections unspecified. FP-003
provides immutable candidate state; FP-004 provides event contracts and a repository
port. Neither supplies a transaction coordinator. A failed append must prevent
dependent state publication and action continuation.

## Decision

Use one local application writer and a SQLite unit of work. Commit authoritative
events, required synchronous projections, optional checkpoint snapshots, request
idempotency records and durable publication/action intent in **one transaction**.
Treat live memory as a disposable cache. Swap candidate state into that cache only
after commit succeeds. A commit with an uncertain outcome requires recovery before
any further mutation, success response, dependent action or publication.

Use WAL, foreign keys and `synchronous=FULL` on every writing connection, verifying
the settings at startup. SQLite permits one writer at a time; `BEGIN IMMEDIATE`
acquires that write transaction before tail allocation. WAL permits readers while
the writer operates. FULL adds the commit synchronization needed for WAL durability,
subject to the filesystem/device honoring synchronization. See the official
[transaction rules](https://www.sqlite.org/lang_transaction.html),
[WAL documentation](https://www.sqlite.org/wal.html), and
[synchronous setting](https://www.sqlite.org/pragma.html#pragma_synchronous).

The local database and its WAL/SHM companions stay together on supported local
storage. Do not copy only the live database file for backup. Backup, migration,
checkpoint management and device-specific durability qualification belong to FP-006
and later operational work; this proof does not certify power-loss behavior.

### Happy path and sequence allocation

1. Validate the command and its idempotency key. Load a committed aggregate and
   prepare an immutable candidate; perform no external side effects.
2. Enter `BEGIN IMMEDIATE`. Look up `(session_id, idempotency_key)` **before** checking
   expected aggregate version or allocating sequence. A matching prior request
   returns its original durable result; changed input with the same key conflicts.
3. Recheck the committed aggregate version and event tail inside the transaction.
   Allocate contiguous event sequences from that tail, starting at 1. Event sequence
   and aggregate version are distinct. Enforce unique event IDs and unique
   `(session_id, sequence)` in SQLite. Concurrent/stale candidates must be discarded
   or recomputed from committed state; never publish them.
4. Append the validated event batch, update required projections and their source
   sequence/projection version, write any checkpoint snapshot, record the durable
   result and enqueue outbox intent in the same transaction.
5. Commit. On success install the candidate cache, then make the successful response
   and committed outbox eligible for publication/action dispatch. A cache-install
   failure gates processing until reconstruction completes.

No reservation of a sequence survives rollback; a retry allocates from the durable
tail again. Busy writers get a bounded retry/backoff policy and no acknowledgement
of success. Production timeout values will be selected in FP-006.

### Idempotency

Persist request key, canonical request fingerprint and original response/event
references atomically. The production fingerprint includes command type, session,
expected aggregate version and all semantic input; it excludes transport retry
metadata. Same key plus same input returns the stored result even after the session
advances. Same key plus different input is a conflict. Retain keys for the session's
retained history; do not silently expire them while retries remain possible.

The proof models one-event requests and uses the FP-004 canonical event document
as the synthetic request fingerprint. This is deliberately not the production
command-fingerprinting algorithm. Multi-event responses and actual command schemas
remain FP-006/application work.

### Failure matrix

| Failure point | Required result |
| --- | --- |
| Validation/stale version | Reject candidate; no writes or external effects |
| Writer busy | No sequence allocated; bounded retry or explicit busy result |
| Event insert | Roll back entire transaction; preserve previous cache; pause mutations and dependent publication |
| Projection/snapshot/idempotency/outbox write | Same rollback; never retain an event without required dependent records |
| Commit error | Explicit rollback when transaction is active; if outcome is uncertain close/reopen and resolve by durable key/history |
| Crash before commit | SQLite recovery leaves no partial request; original sequence remains reusable |
| Crash after commit before cache swap/response | Reconstruct cache from committed history; retry returns original durable result |
| Publish/adapter failure | Preserve committed history and pending intent; retry according to idempotency policy |
| Crash after send before marking dispatched | Delivery may repeat; use event ID/sequence or action idempotency key to deduplicate |
| Invalid authoritative history | Block mutation and dependent dispatch; preserve original bytes; report integrity failure |

Do not attempt to append a session.failed event as the only response to unavailable
persistence. Raise an out-of-band fatal persistence health alert and stop/pause
state-changing processing; record any subsequent durable recovery event only after
the store is healthy. A failed command may not silently advance simulation time.

### Publication and external actions

The outbox is committed with the event, not populated after commit. Dispatch reads
committed rows in session sequence order; a failed send leaves that row pending and
blocks later dependent sends for that session. Mark dispatched only after the send
returns successfully. This provides **at-least-once attempted delivery**, not
exactly-once client receipt. Browser reconnect uses its last processed sequence to
read authoritative history or resynchronize a snapshot; a sent flag is not proof
that every browser received the event.

External actions also require committed intent and an idempotent action key at the
adapter boundary. An irreversible adapter action without deduplication support must
not be blindly retried after an ambiguous send; surface it for reconciliation.
The proof exercises publication only, not a production adapter/action protocol.

### Recovery and projection/snapshot boundaries

Before making a recovered session writable or dispatching pending intent, validate
event schemas, indexed identity/session/sequence agreement, contiguous order and
aggregate transition consistency. Reconstruct the aggregate and compare/rebuild
derived projections. Projections carry source sequence and projection version;
they never override event truth. Required projections and checkpoint snapshots
share the append transaction. Optional expensive reports may lag, but must expose
their source sequence and cannot drive authoritative decisions while stale.

Snapshots carry session, source sequence, schema/projection versions and a validated
canonical document. A missing, incompatible or corrupt snapshot is discardable when
the retained authoritative prefix permits full replay. A checkpoint cannot bridge
an unexplained history gap. Production snapshot integrity metadata and efficient
reducer/checkpoint selection must be contract-tested in FP-006.

The proof always rebuilds its tiny projection and snapshot from full retained
history; it never overwrites events. Malformed authoritative history blocks recovery.
Read-only salvage of a valid prefix, invalid suffix display, failed-session replay
thresholds and evidence presentation remain **AB-04**, requiring separate approval.
Do not interpret this conservative live-recovery rule as approval of partial replay.

## Alternatives considered

| Alternative | Reason not selected |
| --- | --- |
| Mutate live memory, then append | Append failure exposes unrecorded state and requires fragile compensation |
| Commit events, then required projections separately | Opens a consistency gap for live decisions; adds recovery states unnecessarily |
| Commit events then directly publish without outbox | Crash after commit loses dispatch intent; reconnect alone does not cover adapter effects |
| Distributed broker/transactions | Outside the single-process offline Phase 1 scope |

The selected approach adds transactional write work and an outbox dispatcher, but
keeps authoritative consistency local and recovery explicit. Analytical projections
may be asynchronous under the stale-state restrictions above.

## Executable evidence and limits

Run `python -m pytest tests/backend/test_persistence_consistency.py -q`.
The self-contained proof fixture uses only temporary SQLite files and existing
synthetic FP-004 JSON. It tests an actual CREATED-to-INITIALISING event, SQLite
trigger failures at all five write boundaries, denied COMMIT, lock contention,
stale writers, matching/conflicting retries, projection rebuild and invalid history.
Child processes terminate with `os._exit` before commit, after commit, and after
send-before-mark; a new connection then reconstructs the committed result.

The tests do not simulate power interruption, media failure, real SQLITE_IOERR,
production migrations, multi-event commands, all reducers or actual sockets/adapters.
Denied COMMIT is a deterministic database error, not an uncertain disk-commit proof.
No production persistence implementation or runtime configuration is introduced.

## Baseline amendment

Amendment FP-005, approved 2026-09-17: baseline v1.0 section 28.4 now marks
AB-01 resolved by this consistency decision; section 31 records ADR-008 as
**Consistency approved (FP-005); AB-04 open**. Sections 16.4, 19 and 22 retain
their requirements, supplemented by the transaction and recovery rules here.

The proof passed 18 targeted tests; the complete backend suite passed 405 tests
and repository-wide mypy passed all 21 source files after the acquisition typing
fix. FP-006 may implement this approved consistency model. AB-04 remains a separate
approval gate for failed-history replay. Supersede this decision through a new ADR
rather than silently editing its historical meaning.
