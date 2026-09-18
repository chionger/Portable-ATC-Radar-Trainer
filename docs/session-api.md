# FP-008: Durable session REST API

## Scope and readiness

Session commands use the FP-006 SQLite unit of work. Creation pins the effective
configuration hash, configuration/schema/rule versions and seed in the creation event.
The existing `paths.data_root` is the session data root; `persistence.database_path`
overrides its default `sessions.sqlite3` file. Prepare that local parent directory
before using session routes. Configuration loading and `/health` do not open storage.
Each session request opens, validates/recovers and closes its own SQLite connection in
the request thread. No model storage is inspected and no directories are created.

Creation returns `CREATED`. Scenario loading and initialisation are explicitly outside
FP-008. The internal service supports `INITIALISING` and `READY` transitions for later
scenario wiring; it does not manufacture readiness. Until that wiring is available,
starting a newly created session correctly returns `409 ILLEGAL_TRANSITION`.
Scenario IDs/versions are caller-supplied references, not proof of a loaded scenario.
Rule/schema version `1.0` denotes the current lifecycle contract, not a loaded scoring
rule set. Internal events use a system actor; this packet adds no authentication policy.

## HTTP contract and examples

All mutations require a UUID `Idempotency-Key`. Clients may send UUID
`X-Correlation-ID`; otherwise the server generates one and echoes it in the response.
The same correlation identifier is written to newly committed lifecycle events.
The full OpenAPI snapshot is `tests/fixtures/session-api.openapi.json`; runtime examples
and schemas are available from `/docs` and `/openapi.json`.

Create: `POST /api/v1/sessions` (201)

```json
{"schema_version":"1.0","scenario_id":"training","scenario_version":"1.0","seed":42}
```

Response shape (session fields abbreviated):

```json
{"schema_version":"1.0","session":{"session_id":"<uuid>","lifecycle_state":"CREATED","version":1}}
```

Read: `GET /api/v1/sessions/{session_id}` (200). Returns the current committed summary,
including pinned versions, timestamps, simulation time, outcome and failure evidence.

Commands: `POST /api/v1/sessions/{session_id}/{start|pause|resume|stop}` (200)

```json
{"schema_version":"1.0","expected_version":3}
```

| Command | Required current state | Result |
| --- | --- | --- |
| start | READY | RUNNING |
| pause | RUNNING | PAUSED |
| resume | PAUSED | RUNNING |
| stop | RUNNING or PAUSED | STOPPED |

Lifecycle version is distinct from event sequence: health events advance sequence only.
REST clients cannot set simulation time, pinned configuration, failure details or target
states. Internal `DurableSessionService.transition` supports every domain transition,
including completion and forced failure with retained category/reason evidence. Failure
and completion are not new public routes. There is no WebSocket or model/scenario adapter.

## Retry and error behaviour

Keep the same key and request fields for a retry. Session identity is derived from the
creation key, so retrying create after restart finds the original durable result.
Omitted seed is resolved once at the first successful commit (default 0, configurable).
Retries keep the original seed/configuration even if configuration subsequently changes.
Reuse of a key with different semantic input returns 409. Retry lookup precedes current
version/state checks, so a successful start retry after pause returns its original
RUNNING response without changing the current PAUSED session. Use GET for current state.

Each new lifecycle command checks expected version and builds its event under the write
transaction. Event, session projection, request result and outbox intent commit together.
Illegal transitions, stale versions and rejected writes append no lifecycle event.
Persistence failures return 503 and do not expose a successful state change. An uncertain
commit must be retried with the same key; do not assume a 503 proves nothing committed.
No adapter delivery is performed by these routes.

Errors share a stable envelope; input values, exception text and filesystem paths are
omitted. `details` is currently an empty object reserved for safe structured diagnostics.

```json
{"code":"ILLEGAL_TRANSITION","message":"Lifecycle transition rejected","details":{},"correlation_id":"00000000-0000-0000-0000-000000000001"}
```

| Status | Code |
| --- | --- |
| 404 | SESSION_NOT_FOUND |
| 409 | ILLEGAL_TRANSITION, other domain transition code, or WRITE_CONFLICT |
| 413 | REQUEST_TOO_LARGE |
| 422 | INVALID_REQUEST |
| 503 | PERSISTENCE_UNAVAILABLE |
| 500 | INTERNAL_ERROR |

Missing/malformed keys, invalid UUID paths, extra fields, unsupported request version and
invalid types are rejected. The body limit counts actual bytes before JSON parsing,
including chunked bodies. CORS supports POST and the idempotency/correlation headers for
the configured loopback origins. No credentials or request bodies are logged.

## Configuration

| Field | Environment | Default / bound |
| --- | --- | --- |
| sessions.default_seed | ATC_SESSIONS_DEFAULT_SEED | 0; integer 0..9223372036854775807 |
| sessions.max_request_bytes | ATC_SESSIONS_MAX_REQUEST_BYTES | 4096; integer 256..65536 |

Session data root and SQLite timeout/migration settings reuse FP-002/FP-006 configuration.
These additions participate in the effective configuration hash. The seed policy is
explicit deterministic defaulting, with per-create seed override; no implicit randomness.

## Recovery and rollback

On storage failure check the configured parent directory, permissions and database
compatibility. Follow the FP-006 backup/recovery runbook; never rewrite or remove history.
Reopening validates retained history and rebuilds projections. Rolling back these routes
to FP-007 leaves compatible lifecycle events in place; retain the database and pending
outbox records. An older API without these routes cannot operate existing sessions.
AB-04 failed-history replay remains open. A live failed session is terminal.
