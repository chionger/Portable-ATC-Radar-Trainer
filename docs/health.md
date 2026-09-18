# FP-007: Local health and structured logging

## Health response and readiness

`GET /health` remains HTTP 200 when the API responds. The existing `status: "ok"`
and `configuration_version: "1.0"` fields remain compatible liveness information.
New `readiness` and `components` fields describe the registered components:

| Readiness | Meaning |
| --- | --- |
| `healthy` | Every registered component is healthy |
| `degraded` | A component is degraded, or an optional component is unready |
| `unready` | A required component is unready, or the registry is empty |

Each component contains a fixed application-registered ID, required flag, status,
severity, reason code and UTC observation time. Severity is info/warning/error for
healthy/degraded/unready. Allowed reasons are operational, starting, failed, timeout
and not_configured. Providers must register stable component names, never names
containing user data. Arbitrary exception messages and configuration values are
not accepted as diagnostic reasons.

The API registers only `api` (required) and `logging` (optional). Healthy here means
these registered components are healthy; it does not certify unimplemented scenario,
model or simulation readiness. Later adapters must register their own requirements.
Health reads perform no network/cloud probes, model access or session writes.

Observations expire after the configured timeout. Snapshot reads derive timeout
readiness without producing events. Producers call `HealthRegistry.expire` explicitly
when durable session-scoped timeout transitions are required; there is no background
session supervisor in this packet. API request activity refreshes the API observation.
The browser polls every five seconds, times out requests after three seconds, displays
component reasons, and clears stale component details on connection failure. It also
accepts the earlier liveness-only response during a staged frontend/backend update.

## Producers, persistence and retry safety

`HealthRegistry.report` accepts typed status/reason and a UUID correlation ID. Global
observations remain in memory. For a session, supply `SessionHealthContext` containing
session ID, expected aggregate version and a UUID idempotency key, plus a durable
`HealthEventStore` implementation (the FP-006 SQLite adapter satisfies this port).
Preserve that context when retrying an uncertain write; use a new key for a new change.

The first session observation and subsequent changes to status/reason are material.
A material change produces `component.health_changed` with the prior status and full
new component observation. The existing SQLite unit of work commits the event,
projection, retry record and outbox intent together. Only then does the registry expose
the result. Write failures preserve prior live health and propagate the persistence
health failure. A retry reads the latest durable component state, so an old successful
request cannot overwrite a newer failure. Same-key/different-input conflicts remain
checked even when the requested state already matches current health.

Repeated observations with unchanged material fields refresh local freshness without
adding events. Retained history supplies deduplication after registry restart. Expiry
uses a distinct deterministic request key per component. Event sequences advance, but
health events do not advance lifecycle version or simulation time. Recovery can still
rebuild the session from mixed lifecycle and health history.

The new payload uses schema/projection version 1.0 for the previously reserved event
name; existing session contracts remain unchanged. Canonical health comparison excludes
observation wall time, and retains component ID, required flag, status, severity,
reason and previous status. Raw stored events retain the observation timestamp.

## Structured logs and metrics

The API assigns or validates `X-Correlation-ID` as a UUID, exposes it on the response,
and places it on `request.state.correlation_id` for downstream event producers.
Malformed identifiers are replaced, not echoed. CORS exposes the response header.
Request logs contain a timestamp, fixed event name, correlation ID, HTTP status and
finite request-duration metric. Request failures return a generic error with the same
correlation ID; exception text is omitted.

`StructuredLog.emit` drops every unrecognized field. It never serializes raw URLs,
queries, headers, request bodies, transcript/audio, arbitrary exceptions or credentials.
The supported launcher disables Uvicorn access logs to avoid duplicating raw query
strings. If starting Uvicorn directly, pass `--no-access-log`. Third-party log handlers
outside this application are not covered by this formatter.

`HealthRegistry.observe_metric` provides a bounded, immutable observation hook for
request duration and component latency in milliseconds. The latest 100 observations
are retained locally; there is no monitoring exporter or dashboard.

File logging is optional. JSON records go to a dedicated console handler by default;
configured files rotate by size and backup count. No directories are created. File
errors mark optional logging degraded on the next health response and do not expose
private file paths or block API health requests. Application shutdown closes handlers,
including Windows file handles. Reporting effective configuration also redacts the
log path. Log files remain separate from authoritative SQLite history.

## Configuration

| YAML field / environment variable | Default / limits |
| --- | --- |
| `logging.level` / `ATC_LOGGING_LEVEL` | INFO; existing supported levels |
| `logging.file_path` / `ATC_LOGGING_FILE_PATH` | null (console); absolute local file; environment `null` clears override |
| `logging.max_bytes` / `ATC_LOGGING_MAX_BYTES` | 1000000; integer 1024–100000000 |
| `logging.backup_count` / `ATC_LOGGING_BACKUP_COUNT` | 3; integer 1–10 |
| `health.timeout_seconds` / `ATC_HEALTH_TIMEOUT_SECONDS` | 30; finite number greater than 0 and at most 3600 |

Use a dedicated local log directory outside model storage. Configuration validation is
lexical, performs no filesystem probes, and does not open a database or log file.
The same YAML/environment/explicit-override precedence and configuration hash apply.

## Troubleshooting and rollback

- **Unavailable:** verify the local API is running and its configured address/port.
- **Starting/not configured:** initialize the named required provider before preflight.
- **Failed:** inspect the fixed reason and correlate the request ID with local logs;
  provider-specific diagnostics belong to later adapter packets.
- **Timeout:** verify the provider is still sending observations; health reads do not
  silently revive it. Recovery requires a fresh provider observation.
- **Logging degraded:** check the configured parent directory and file permissions,
  or clear `logging.file_path` and restart to use console logging.
- **Persistence failure:** stop state-changing processing and dependent publication;
  follow the FP-006 recovery runbook. Do not synthesize session failure into a broken DB.

To roll back optional file logging, clear its path. Preserve databases containing new
health events: older event readers reject this previously reserved payload. Use a
compatible reader or restore a verified pre-upgrade backup into a separate location;
never remove authoritative health events to make older code accept the history.

## Evidence

`tests/backend/test_structured_health.py` exercises aggregation, timeout/recovery,
redaction, bounded metrics, rotating-file cleanup, API failure/recovery and durable
session health, including stale retry protection. Browser tests cover healthy,
degraded, unready, malformed and unavailable responses plus recovery polling.
The published schema/catalogue and stored health example are in `tests/fixtures/events`.
No real model assets, cloud checks, external monitoring or session stream are introduced.
AB-04 failed-history replay remains open.
