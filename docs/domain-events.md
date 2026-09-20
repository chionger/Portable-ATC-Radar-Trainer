# Domain event contracts (FP-004)

`packages/domain/events.py` owns the immutable `DomainEvent`, typed actor/source,
payloads and central `EVENT_REGISTRY`. `packages/application/events.py` exposes
`EventFactory`, its pure `SessionEventFactory` implementation, explicit sequence
context and the `EventRepository` port. No IDs, clocks or storage are allocated.

## Catalogue

The machine-readable catalogue is `tests/fixtures/events/catalogue.json`. It
contains all 47 names from architecture baseline section 15.2; a contract test
compares the two. Duplicate names, unknown names and routine clock ticks are
rejected. The thirteen implemented names (including FP-007 health and FP-010 traffic) are:

| Event | Fact |
| --- | --- |
| session.created | CREATED session, version 1, sequence 1, simulation time zero |
| session.initialising | CREATED to INITIALISING |
| session.ready | INITIALISING to READY |
| session.started | READY to RUNNING |
| session.paused | RUNNING to PAUSED |
| session.resumed | PAUSED to RUNNING |
| session.completed | RUNNING or PAUSED to COMPLETED |
| session.stopped | RUNNING or PAUSED to STOPPED |
| session.failed | Any nonterminal state to FAILED, with category and reason |
| component.health_changed | Material component health change for an existing session (FP-007) |
| aircraft.spawned | Initial aircraft; first spawn also captures shared aerodrome geometry (FP-010) |
| aircraft.state_changed | Legal versioned aircraft transition (FP-010) |
| runway.occupancy_changed | Versioned membership change paired with its aircraft effect (FP-010) |

Other catalogue entries reserve names and version metadata for later producers;
their payload type is absent and emission/deserialization is rejected. Reserving
a name does not promise a usable payload schema. Instructor override remains
conditional on its future feature policy.

## Payloads and envelope

Creation pins scenario ID/version, seed and configuration/rule/schema/adapter/model
metadata. Transitions record previous/current state and session version, terminal
outcome and failure details. Session version advances exactly once; it is distinct
from event sequence, which will also count non-session events.

The envelope requires event/session IDs, registered event type, schema version,
positive integer sequence, finite nonnegative simulation seconds, aware wall time
(normalized to UTC), actor, source and correlation ID. Causation ID is optional.
Actor kind is system/controller/instructor/adapter, with optional diagnostic identity;
source records component and version. These conventions are the initial FP-004
contract and can evolve only through versioned schema changes.

Contracts are frozen, including nested payload metadata. Parse external records
with `DomainEvent.model_validate_json`; serialize with `model_dump_json`. Pydantic
validation errors report malformed records. Treat `model_construct`/`model_copy`
as trusted internal bypasses, never as an external ingestion path.

## Compatibility and published contracts

Event schema version and canonical projection version are separate constants,
both initially `1.0`. Unknown major versions fail. Unregistered minor versions
also fail until a compatible schema is explicitly implemented and contract-tested.
Optional additive fields may be introduced under a registered compatible minor
version; this packet does not silently discard unknown fields. Migration must
retain the original record and must not rewrite historical semantic meaning.

`tests/fixtures/events/domain-event.schema.json` publishes the structural JSON
schema, with nine stored session JSON examples alongside it. Runtime validators
add semantic checks (legal edges, name/payload agreement, outcomes, sequence and
pre-start time); structural JSON-schema validation alone is insufficient.
Fixture tests parse and round-trip stored files; they do not regenerate them.
Terminal fixtures represent alternative endings, not one concatenated stream.

## Canonical comparison

Projection version `1.0` retains event type, sequence, simulation time, actor kind,
source component/version and every typed payload field. Creation therefore retains
scenario/seed and all version pins; transitions retain state/version/outcome/failure.
It excludes generated event/session/correlation/causation IDs, actor identity and
wall time. Raw schema version is replaced by separately versioned projection
metadata. Actor identity is diagnostic; actor kind remains semantic. Session IDs
are excluded to permit comparison of separate runs of the same scenario.

`canonical_projection()` returns a fresh JSON-compatible document;
`canonical_json()` sorts keys for stable comparison. Changes to retained values
must change equality. Future payload schemas must explicitly define their own
semantic fields before moving a reserved entry to implemented status. This is
comparison metadata, not a replay reducer or a substitute for original history.

## Ordering and persistence boundary

`EventContext` supplies a sequence exactly one greater than an observed last
sequence (zero before creation). It is a precondition, not an allocator or lock.
The caller remains responsible for authorized actor/source/correlation context.

`validate_append_batch` checks a nonempty immutable batch, one session, contiguous
sequences and distinct event IDs. The repository implementation must also check
its actual tail atomically, enforce globally unique event IDs and unique
`(session_id, sequence)`, and append the entire batch or nothing. Reads return
ascending records strictly after the requested cursor. Local validation cannot
prevent races or detect duplicates against existing history.

The required order is assign identity/sequence, durably append, project consistently,
then publish. No database or publication is implemented here. Atomic state/event/
projection consistency and recovery remain gated by FP-005 (ADR-008), followed
by the persistence implementation in FP-006. This packet adds no application
settings, routes, WebSocket behavior or business-rule consumers.

## FP-007 extension

The health payload contains previous status and a typed component observation. Canonical comparison excludes its observation wall time. Session projection consumes this event without changing lifecycle state/version or simulation time. See [health and logging](health.md) for the producer, durability, deduplication and correlation contracts. FP-006 implements the approved persistence boundary described above.

## FP-010 extension

Traffic payloads and their canonical projections retain all aircraft and aerodrome state
fields. The application traffic service produces them through the existing unit of work.
Session projection validates traffic lifecycle/time constraints and traffic replay checks
paired occupancy effects. See [traffic state](traffic-state.md) for the canonical matrix,
scenario mapping, atomicity, replay and compatibility limits.
