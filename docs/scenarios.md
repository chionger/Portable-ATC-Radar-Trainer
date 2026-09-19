# FP-009: Versioned scenarios

## Scope

FP-009 provides strict, immutable YAML data, validation, catalogue metadata, a synthetic
reference skeleton and session hash capture. It does not execute schedules, movement,
objectives or error injection, load models, or certify aerodrome data. The reference file
is `tests/fixtures/scenarios/reference.yaml`; its coordinates are synthetic local metres.

## Authoring contract

Every file declares `schema_version: "1.0"`, an ID, an explicit version, a non-negative
integer default seed and presentation metadata. Quote version strings in YAML. All IDs
start with an ASCII letter/digit and contain at most 64 letters/digits, underscores, dots
or hyphens. IDs are globally unique inside a scenario; callsigns are unique too.
Unknown keys and implicit type coercion are rejected. Arrays become immutable tuples.

| Section | Fields / validation |
| --- | --- |
| geometry | local_metres; at least one runway; optional taxiways and holding points |
| runway | ID, distinct threshold/end points, width in metres greater than zero and at most 200 |
| taxiway | ID, 2–256 points; consecutive points must differ |
| holding point | ID, position, existing runway and taxiway IDs |
| point | finite x/y in metres, each between -1000000 and 1000000 |
| environment | wind direction degrees [0,360), speed knots [0,100], visibility metres (0,100000], frequency MHz [118,137] |
| entities | ID, callsign, position, initial state, route of existing geometry IDs |
| schedules | ID, time in seconds, existing entity ID, fixed action name |
| objectives | ID, description, entity ID, geometry target ID, fixed objective kind |
| error_injections | ID, entity ID, time, fixed kind, probability [0,1] |
| end_conditions | positive time limit up to 86400 seconds, non-empty success-objective references, failure_on_timeout boolean |
| presentation | title (1–128 characters), description (up to 2048 characters) |

Initial entity states: PARKED, TAXIING, HOLDING, INBOUND, FINAL. Schedule actions: activate,
request_taxi, report_inbound. Objective kinds: reach, hold, vacate. Injection kinds:
incorrect_readback, delayed_response. These are declarative contract names; execution and
full aircraft-state semantics belong to later packets. Schedules/injections may not lie
beyond the scenario time limit. Preserve array order; it remains part of content identity.
The schema validates structural geometry, not route connectivity or aircraft dynamics.

Machine-readable contracts are `tests/fixtures/scenarios/scenario.schema.json` and
`scenario-loaded.schema.json`. The latter defines only the future `scenario.loaded`
payload: ID, version, SHA-256 hash and scenario schema version. Its envelope remains
reserved; no such event is emitted or activated by this packet.

## Safe loading and diagnostics

Only direct `.yaml`/`.yml` regular files in the configured local directory are considered;
there is no recursive directory search or filename construction from an API ID. Symbolic
links and junction entries are rejected. The source directory is trusted local deployment
storage, not an adversarial concurrent filesystem sandbox.

Each document is limited to 1 MiB, 20001 scanned tokens and nesting depth 32. Directory
inspection stops at 513 entries and rejects more than 512. Schema collection limits add
bounds on geometry, entities and schedules. YAML tags (including Python tags), anchors,
aliases, duplicate/non-string keys and multiple documents are rejected. No expressions,
code, shell text or dynamic imports are interpreted. A failed file rejects the entire
catalogue, so invalid files are not silently hidden from the operator.

Errors contain a fixed code and a location such as `reference.yaml:entities.0.route.0`.
YAML syntax/duplicate-key errors use line and column. Raw exception text, supplied field
values and absolute filesystem paths are omitted. The invalid-fixture matrix is
`tests/fixtures/scenarios/invalid-matrix.json`; hostile YAML cases are in the regression suite.

## Catalogue and configuration

| Setting | Environment | Default |
| --- | --- | --- |
| scenarios.directory | ATC_SCENARIOS_DIRECTORY | null (empty catalogue) |
| scenarios.validation | ATC_SCENARIOS_VALIDATION | strict (only supported mode) |

The directory must be an absolute local path. Configuration validation is lexical and
redacts the directory in diagnostics; it does not inspect storage. Omit the environment
override and use YAML null to disable the directory. No scenario directory is created.
For the reference skeleton, point this setting at a local copy of the reference fixture
directory containing YAML files. JSON schema/matrix files there are ignored.

- `GET /api/v1/scenarios`: sorted metadata for every validated ID/version.
- `GET /api/v1/scenarios/{id}?version=1.0`: exact version metadata.
- Omitting version is allowed only when there is exactly one version for that ID.
- Unknown ID/version returns 404 SCENARIO_NOT_FOUND; ambiguity/invalid content returns
  422 INVALID_SCENARIO with structured locations.

Responses contain schema version, ID/version, content hash, title, description and seed.
They never return entity/schedule/geometry content. Catalogue reads do not open SQLite.
Each catalogue instance captures validated immutable values once, on first access. Edits
cannot mutate that capture; restart/reconstruct explicitly to capture a new version.
Publish a new scenario version when content changes; do not overwrite versions needed by
persisted sessions. A hash covers canonical typed JSON with sorted object keys, preserving
array order; YAML whitespace/comments/key order do not affect the hash.

## Sessions and readiness

With a scenario directory configured, new REST sessions resolve the exact requested
ID/version and pin its hash in the creation event and session projection. Omitted seed
uses the scenario default; explicit seed still wins. Idempotent create retries preserve
the original hash/seed even after restart or source-file loss. Reopening SQLite rebuilds
the same hash from retained events; no scenario content table or migration is introduced.

`DurableSessionService.prepare_scenario` is an internal initialisation hook. It first
records INITIALISING, validates the pinned scenario, and records FAILED with fixed
SCENARIO_VALIDATION_FAILED evidence if the scenario is missing, invalid or hash-mismatched.
On success it stays INITIALISING: later adapter wiring must complete readiness. A new
READY transition for a hash-pinned session revalidates the captured identity/hash before
its pure event builder runs. Rejection adds no readiness event. Existing successful retry
results still win before the builder, even if the source subsequently becomes unavailable.

With no scenario directory, FP-008 creation behaviour remains compatible and leaves the
hash null; that is not validation evidence. Existing hashless history still replays and
retains its original lifecycle rules. Running hashless history through the new preparation
hook fails closed. No public initialisation or arbitrary-state route is added.

## Compatibility and rollback

Scenario schema 1.0 is explicit; unknown versions fail closed. Keep published scenario
versions available; content with a different hash must never be silently substituted.
`session.created` gains an optional scenario_hash in the existing envelope. Historical
hashless creation payloads serialize unchanged. New readers recover both forms. Older
readers may reject new hash-bearing events: preserve history and use a compatible reader
or restore a verified pre-upgrade backup to a separate location. Never strip hashes/events
from an authoritative database. AB-04 failed-history replay remains open.
