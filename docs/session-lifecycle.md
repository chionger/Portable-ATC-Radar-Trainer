# Session domain and lifecycle (FP-003)

`packages/domain/session.py` defines immutable live sessions and a pure transition
policy. `packages/application/sessions.py` exposes the `SessionLifecycle` protocol
and a stateless implementation. Callers supply IDs, pinned versions, seed and
timezone-aware wall timestamps. Construction does not load scenarios, models or
configuration, generate IDs, read a clock, or perform I/O.

## Legal transitions

| Current state | Permitted next states |
| --- | --- |
| CREATED | INITIALISING, FAILED |
| INITIALISING | READY, FAILED |
| READY | RUNNING, FAILED |
| RUNNING | PAUSED, COMPLETED, STOPPED, FAILED |
| PAUSED | RUNNING, COMPLETED, STOPPED, FAILED |
| COMPLETED | None |
| STOPPED | None |
| FAILED | None |

The baseline has 14 legal transitions across 64 state pairs. All other pairs,
including self transitions and terminal resume, raise `SessionTransitionError`
with `ILLEGAL_TRANSITION`. Replay is not a live lifecycle state. The matrix test
enumerates all 64 pairs against an independent explicit table.

## State and time

Create with `create_session(CreateSessionRequest(...))`; transition with
`transition_session(session, TransitionRequest(...))`. Each successful transition
returns a new session and an immutable transition fact. The input is unchanged.
Versions begin at 1 and increment once per successful transition. Identity,
scenario version, seed and configuration/rule/schema/adapter/model pins survive
every transition. Pins are metadata only; configuration hashes are supplied by
the caller, validated as lowercase SHA-256 identifiers, and never recomputed here.

Wall timestamps normalize to UTC and cannot precede the last transition. Equal
timestamps are allowed. `created_at` stays fixed; `updated_at` records the latest
transition. The first READY-to-RUNNING transition sets `started_at`; resume keeps
it. A terminal transition sets `ended_at` equal to `updated_at`. Failure before
starting has no `started_at`.

Simulation time is explicit finite nonnegative seconds, starting at zero. It
cannot move backwards and can advance only on a transition out of RUNNING.
It stays frozen during pre-start states and pauses; elapsed wall time never
implicitly advances it. Simulation ticks and runtime orchestration are deferred.

## Outcomes and errors

Terminal outcomes are COMPLETED, STOPPED and FAILED. They describe termination,
not training scores. FAILED is available from every nonterminal state and requires
nonblank category and reason, retained exactly. Category vocabulary belongs to
the caller until the relevant adapter policy defines it. Failure details are
rejected for other destinations. Invalid transition timestamps, simulation time
and failure metadata have separate typed error codes. Invalid initial snapshots
or version metadata raise `ValueError`. Errors do not mutate existing sessions.

Transition facts contain identity, source/destination, old/new version, wall and
simulation time, outcome and failure. They are not persisted event envelopes and
do not allocate event sequences. Creation returns a session; event construction
and sequencing belong to FP-004. Persistence, idempotency, initialization and
durable orchestration remain deferred to their packets, including FP-008. This
packet adds no routes, database, configuration settings, replay or external adapters.
