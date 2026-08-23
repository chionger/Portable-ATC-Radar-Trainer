# ATC Portable Trainer
## Phase 1 Ordered Feature Packets

**Source authority:** ATC Portable Trainer — Phase 1 Architecture Baseline v1.0  
**Packet set version:** 1.2
**Date:** 2026-08-07  
**Purpose:** GitHub issue planning and implementation sequencing  
**Constraint:** No packet requires Unity, BlueSky, cloud services, or distributed deployment

---

# 1. Packet Conventions

- Each numbered packet is sized for one focused GitHub issue unless marked **EPIC**.
- Architecture decision packets close baseline blockers and produce an approved ADR; they do not implement speculative behaviour.
- Every implementation packet must leave the default branch runnable and all existing tests passing.
- Deterministic fakes and contract tests precede local ASR, LLM, and TTS integration.
- Events are authoritative. Projections, replay, scoring, and debrief consume the established event model.
- “None” under an interface category means the packet must not change that boundary.
- Baseline references use section numbers from Architecture Baseline v1.0.

# 2. Dependency Sequence

```text
FP-001 Repository foundation
  -> FP-001A Local model zoo foundation
  -> FP-001B Model zoo acquisition tooling
  -> FP-002 Typed configuration
  -> FP-003 Session/domain primitives
  -> FP-004 Event schemas
  -> FP-005 Persistence consistency ADR [AB-01]
  -> FP-006 SQLite event store
  -> FP-007 Health and observability
  -> FP-008 Session lifecycle API
  -> FP-009 Scenario schema/loader
  -> FP-010 Aerodrome and aircraft domain
  -> FP-011 Simulation port and fake
  -> FP-012 Simple deterministic simulation
  -> FP-013 Canonical snapshots
  -> FP-014 Session WebSocket stream
  -> FP-015 Browser operational display
  -> FP-016 Structured command validation
  -> FP-017 Clearance/readback/correction gate
  -> FP-018 Deterministic virtual pilot
  -> FP-019 Deterministic error injection
  -> FP-020 Radio audibility ADR [AB-02]
  -> FP-021 Radio engine
  -> FP-022 Reference scenario vertical slice
  -> FP-023 Browser PTT capture
  -> FP-024 ASR port and fake
  -> FP-025 Deterministic command extractor
  -> FP-026 LLM port, fake, and routing
  -> FP-027 Local ASR benchmark/integration
  -> FP-028 Local LLM benchmark/integration
  -> FP-029 TTS port and fake
  -> FP-030 Local TTS benchmark/integration
  -> FP-031 Competency observations
  -> FP-032 Scoring and debrief
  -> FP-033 Instructor markers
  -> FP-034 Instructor override decision [AB-03]
  -> FP-035 Instructor override implementation [conditional]
  -> FP-036 Failed-history replay ADR [AB-04]
  -> FP-037 Replay engine and API
  -> FP-038 Replay browser UI
  -> FP-039 Offline export bundle
  -> FP-040 Privacy and retention controls
  -> FP-041 Offline packaging and startup
  -> FP-042 Failure recovery and performance hardening
  -> FP-043 Release acceptance campaign
```

Dependencies shown above are the critical ordering spine. Section 5 identifies safe parallel work.

# 3. Feature Packets

## FP-001 — Repository and Runnable Application Foundation

**Objective:** Create the smallest runnable backend/frontend repository with pinned toolchains, automated tests, and enforced architectural boundaries.

**User or system value:** Establishes a reproducible base that every later packet can extend without breaking startup.

**Architecture baseline references:** §§1, 8, 9, 24, 25, 29; ADR-003.

**Dependencies:** None.

**Affected modules:** Root project files; `apps/api`; `apps/web`; initial `packages/domain`, `packages/application`, `packages/infrastructure`; `tests`; scripts.

**Inputs:** Baseline technology stack and dependency rules.

**Outputs:** FastAPI process with `/health`; React/Vite page; backend/frontend test commands; architecture-boundary check; Windows development start script.

**Domain models:** None beyond empty package boundaries.

**Events produced and consumed:** None.

**REST or WebSocket changes:** Add `GET /health` returning process status; no WebSocket.

**Persistence changes:** None.

**Configuration changes:** Minimal development defaults for API host/port and web API URL; no secrets.

**Implementation constraints:** Backend binds to loopback; domain packages must not import apps or infrastructure; no cloud SDKs; all committed commands work on Windows.

**Explicit non-goals:** Session lifecycle, database, scenarios, aircraft, WebSocket, models, production packaging.

**Acceptance criteria:** Backend and browser start; browser displays backend health; backend/frontend unit-test commands pass; dependency check fails on a deliberately invalid import fixture; repository contains operating instructions.

**Unit tests:** Health response model; frontend health-state component; dependency-rule test.

**Integration tests:** Start backend test application and fetch `/health`; build frontend production bundle.

**Documentation updates:** Root README with prerequisites, install, run, test, architecture boundaries, and Windows commands.

**Completion evidence:** CI/local transcript showing backend tests, frontend tests, lint/type checks, production build, and health request passing.

**Rollback considerations:** Revert as a single foundation commit; no user data or migrations exist.

## FP-001A — Local Model Zoo Foundation

**Objective:** Establish an offline-capable local model catalogue, provenance record, storage convention, and integrity-verification mechanism for candidate AI model assets without integrating those models into the ATC application runtime.

**User or system value:** Preserves candidate model assets and the information required to identify, verify, restore, licence-review, and later benchmark them even when upstream availability changes.

**Architecture baseline references:** §§6, 8, 24, 29; local-first and offline deployment constraints. Architecture Baseline v1.0 amendment for local model asset preservation.

**Dependencies:** FP-001.

**Affected modules:** `model-zoo`; model manifest/schema; checksum-verification tooling; tests; `.gitignore`; model-zoo documentation.

**Inputs:** Locally acquired candidate model files and associated identity, revision, source, licence, format, quantisation, runtime-compatibility, acquisition, and checksum metadata.

**Outputs:** Versioned model manifest; documented external-storage convention; model metadata schema; SHA-256 verification workflow; model-zoo operating instructions; test fixtures.

**Domain models:** Model-asset metadata only. This packet must not introduce ATC operational domain models.

**Events produced and consumed:** None.

**REST or WebSocket changes:** None.

**Persistence changes:** None to the application database. Actual model binaries remain external deployment assets and are not stored in application persistence.

**Configuration changes:** None to application runtime configuration. FP-002 remains responsible for typed application configuration and later model-path configuration.

**Implementation constraints:**

- Actual large model binaries must not be committed to Git.
- The Git repository stores model metadata, schema, checksums, provenance, licence references, and verification tooling.
- Local model assets must remain usable without cloud connectivity after acquisition.
- Verification must be deterministic and use cryptographic file hashes such as SHA-256.
- Model identity must include sufficient information to distinguish revision/version and quantisation/format.
- A model listed in the zoo is a candidate asset only; listing does not imply approval for runtime use.
- Verification tooling must not automatically download model files.
- The repository must remain runnable after this packet merges.

**Explicit non-goals:**

- ASR inference or Whisper integration.
- LLM inference or llama.cpp integration.
- TTS inference or Piper/Kokoro integration.
- Model benchmarking or provider selection.
- Fine-tuning or training.
- Automatic runtime model discovery or switching.
- Cloud model services.
- Committing multi-gigabyte weights to GitHub.
- Replacing FP-027, FP-028, or FP-030 benchmark/integration responsibilities.

**Acceptance criteria:**

- A documented `model-zoo` structure exists.
- A machine-readable manifest format exists and validates required metadata.
- Model records distinguish category, identity, revision, format, quantisation, source, licence, checksum, intended role, and verification status.
- Model binaries are excluded from Git by design and documentation.
- A checksum-verification command reports at minimum `VERIFIED`, `MISSING`, and `HASH_MISMATCH`.
- Verification works without network access.
- Deterministic test fixtures cover successful verification, missing files, invalid metadata, and checksum mismatch.
- Documentation clearly distinguishes `available`, `verified`, `benchmarked`, and `approved for runtime`.
- No ASR, LLM, or TTS runtime integration is introduced.

**Unit tests:** Manifest/schema validation; SHA-256 calculation; missing-file handling; checksum mismatch; deterministic output; safe path handling.

**Integration tests:** Verify a small local fixture through the same manifest and verification workflow intended for real model assets.

**Documentation updates:** Add model-zoo operating guide covering storage separation, acquisition metadata, verification, backup, restore, licence recording, and relationship to later benchmark packets.

**Completion evidence:** Passing tests; sample manifest; sample verification output showing verified/missing/mismatch cases; repository diff proving no model weight binaries were committed.

**Rollback considerations:** Remove model-zoo metadata/tooling without affecting FP-001 runtime application behaviour. External model assets remain independent of Git history.

## FP-001B — Model Zoo Acquisition Tooling

**Objective:** Automate the repetitive, error-prone mechanics of acquiring an explicitly selected model snapshot into the external model zoo while preserving the architectural separation between acquisition, verification, benchmarking, and runtime approval.

**User or system value:** Reduces manual acquisition errors, ensures exact revisions and provenance are captured consistently, and makes repeated regional model preservation practical without introducing model-selection or runtime behaviour.

**Architecture baseline references:** §§4.7, 6.8, 6.9, 7.2; FP-001A model-zoo architecture.

**Dependencies:** FP-001A.

**Affected modules:** Model-zoo acquisition tooling under `scripts`; model-zoo operating documentation; deterministic acquisition tests and fixtures; packaging/tool configuration only where required.

**Inputs:** Explicit upstream repository identifier; exact or resolvable immutable revision; external model-zoo asset root; optional human-supplied catalogue metadata.

**Outputs:** Externally preserved upstream snapshot; acquisition/provenance record; preserved-asset inventory; deterministic SHA-256 metadata; FP-001A-compatible candidate catalogue data; acquisition-size and verification report.

**Domain models:** Acquisition metadata and candidate model-asset metadata only. No ATC operational domain models.

**Events produced and consumed:** None.

**REST or WebSocket changes:** None.

**Persistence changes:** None to application persistence. Model assets remain external deployment assets.

**Configuration changes:** None to application runtime configuration. External acquisition parameters are supplied to the acquisition tooling and shall not introduce FP-002 application configuration.

**Implementation constraints:**

- Acquisition begins only after a human explicitly specifies the upstream model/repository.
- The tool must require an external asset root and reject locations inside the application Git repository.
- The tool shall use an immutable upstream revision where supported.
- Existing preserved revisions must not be silently overwritten.
- Upstream model snapshot files must be distinguished from downloader cache, temporary files, and locally generated preservation metadata.
- Preserved files must receive deterministic path, byte-size, and SHA-256 metadata.
- Generated catalogue data must remain compatible with the FP-001A manifest contract.
- Existing FP-001A verification tooling shall be reused rather than duplicated.
- Model acquisition may use network access; verification of acquired assets must remain offline-capable.
- The tool shall report storage consumption and available free space where practical.
- Model files shall never be committed to Git.
- The repository must remain runnable after this packet merges.

**Explicit non-goals:**

- Automatic model discovery or recommendation.
- Automatic selection of models by geography, popularity, benchmark, or provider.
- Commercial-use approval.
- Licence legal determination.
- ASR, LLM, TTS, embedding, or VLM inference.
- Model benchmarking.
- Fine-tuning, training, or reinforcement learning.
- Quantisation or model-format conversion.
- Automatic deletion of old model revisions.
- Automatic Git commits, pushes, pull requests, or merges.
- Runtime model selection.
- Application model-path configuration.
- Replacing FP-027, FP-028, or FP-030 responsibilities.

**Acceptance criteria:**

- An acquisition command accepts an explicitly selected supported repository/model.
- Acquisition requires an external asset root outside Git.
- An immutable upstream revision is recorded.
- The acquired snapshot is stored outside Git.
- Upstream preserved files are separated from cache and locally generated preservation metadata.
- A deterministic asset inventory is produced.
- SHA-256 and exact byte size are recorded for preserved files.
- An FP-001A-compatible candidate manifest entry can be generated without automatically marking it benchmarked or approved for runtime.
- An existing preserved revision is not silently overwritten.
- Unsafe destination paths are rejected.
- Storage use/free-space information is reported where supported.
- FP-001A verification successfully validates a synthetic acquired snapshot.
- Normal automated tests do not download any real models.
- No model weights enter Git.
- No FP-002 or later runtime functionality is introduced.

**Unit tests:** Revision handling; destination validation; repository-inside-Git rejection; existing-revision collision; deterministic inventory generation; cache exclusion; preservation metadata separation; SHA-256 generation; free-space reporting; manifest-candidate generation; safe path handling.

**Integration tests:** Acquire a tiny synthetic or local fixture through the same workflow intended for real model repositories, then validate it using the existing FP-001A verifier.

**Documentation updates:** Extend the model-zoo operating guide with model-acquisition workflow, external storage boundary, exact-revision requirements, cache separation, interruption/retry behaviour, generated metadata review, storage budgeting, and post-acquisition verification.

**Completion evidence:** Passing acquisition tests; synthetic acquisition transcript; generated asset inventory; generated candidate manifest; successful FP-001A verification; proof that no model weights were committed; proof that runtime/application behaviour remains unchanged.

**Rollback considerations:** Acquisition tooling may be removed without affecting FP-001A catalogue integrity or existing externally preserved model assets.

## FP-002 — Typed Configuration and Effective Settings

**Objective:** Introduce validated typed settings, precedence rules, packaged defaults, and safe effective-configuration reporting.

**User or system value:** Prevents hard-coded operational values and makes sessions reproducible.

**Architecture baseline references:** §§1.3, 6, 11.3, 24, 28.1, 30; ADR-013.

**Dependencies:** FP-001, FP-001A, FP-001B.

**Affected modules:** Configuration package, API dependency container, development scripts, tests.

**Inputs:** Environment, optional local YAML, packaged defaults, command-line overrides where supported.

**Outputs:** Validated settings object and redacted effective-settings view.

**Domain models:** `AppSettings`, component setting groups, configuration version/hash.

**Events produced and consumed:** None; event integration occurs after FP-004.

**REST or WebSocket changes:** Extend `/health` with non-sensitive configuration version only.

**Persistence changes:** None.

**Configuration changes:** Define precedence, API ports, data/model paths, logging level, feature flags, and schema version.

**Implementation constraints:** Reject unknown/invalid required settings; paths must be explicit and safe; secrets never returned or logged.

**Explicit non-goals:** Model-specific tuning, scoring profiles, session persistence.

**Acceptance criteria:** Defaults start the app; environment override works; invalid configuration prevents startup with field-specific error; effective hash is stable for identical settings.

**Unit tests:** Precedence, validation, redaction, deterministic hash, Windows path handling.

**Integration tests:** Application startup with default and test override profiles.

**Documentation updates:** Configuration reference and local override example.

**Completion evidence:** Test results plus sample redacted effective configuration/hash.

**Rollback considerations:** Preserve compatibility with FP-001 default startup; removal requires restoring explicit safe defaults.

## FP-003 — Session Domain Model and Lifecycle Policy

**Objective:** Implement the canonical session model and legal live lifecycle transitions without persistence or external adapters.

**User or system value:** Gives all later workflows one consistent session state authority.

**Architecture baseline references:** §§10, 11.3, 12.1, 22; ADR-005.

**Dependencies:** FP-001, FP-002.

**Affected modules:** Domain session package, application session interfaces, tests.

**Inputs:** Create/start/pause/resume/stop/fail transition requests.

**Outputs:** New immutable session state and typed transition result/error.

**Domain models:** `Session`, `SessionLifecycleState`, `SessionOutcome`, transition policy.

**Events produced and consumed:** Defines transition facts for later event creation; does not persist events yet.

**REST or WebSocket changes:** None.

**Persistence changes:** None.

**Configuration changes:** None.

**Implementation constraints:** Only legal baseline transitions; source session never transitions to replay; failures retain reason/category.

**Explicit non-goals:** API routes, scenario/model initialisation, replay, database.

**Acceptance criteria:** Every legal transition succeeds; illegal transitions leave state unchanged; terminal sessions cannot resume; failure is permitted from all baseline nonterminal states.

**Unit tests:** Complete transition-table coverage, illegal transitions, timestamps/outcomes, immutability/version increments.

**Integration tests:** None beyond package-level application test.

**Documentation updates:** Lifecycle table and failure semantics.

**Completion evidence:** Transition matrix test report.

**Rollback considerations:** No persistent data; later packets must not merge before lifecycle API stabilises.

## FP-004 — Versioned Domain Event Envelope and Catalogue

**Objective:** Establish immutable event envelopes, Phase 1 event names, payload schema registry, sequencing interfaces, and canonical-projection metadata.

**User or system value:** Creates the authoritative history contract required by persistence, scoring, replay, and debrief.

**Architecture baseline references:** §§4.4, 6.4, 15, 16.4, 29; ADR-007.

**Dependencies:** FP-003.

**Affected modules:** Domain events, schemas, event factory interfaces, contract tests.

**Inputs:** Typed domain facts, session/correlation/causation context.

**Outputs:** Immutable versioned `DomainEvent`; canonical semantic projection.

**Domain models:** Event envelope, actor/source, typed payload protocols, projection definition.

**Events produced and consumed:** Define the complete minimum catalogue in baseline §15.2; implement payloads for session events now and reserve validated registry entries for later producers.

**REST or WebSocket changes:** None.

**Persistence changes:** Define repository port and ordering requirements; no SQLite implementation.

**Configuration changes:** Event schema/projection versions.

**Implementation constraints:** No persisted routine clock ticks; generated IDs/wall time excluded from canonical equality; event names cannot be ad hoc strings outside registry.

**Explicit non-goals:** Database append, WebSocket publication, business-rule consumers.

**Acceptance criteria:** Session events serialize/validate; unknown incompatible major version is rejected; canonical projection ignores documented noncanonical fields; registry prevents duplicate names.

**Unit tests:** Envelope immutability, validation, serialization, projection, registry, sequence preconditions.

**Integration tests:** Schema round trip using stored JSON fixtures.

**Documentation updates:** Event catalogue, compatibility policy, canonical-field rules.

**Completion evidence:** Published schema fixtures and passing contract tests.

**Rollback considerations:** Event schemas become compatibility-sensitive after FP-006; before then revert with fixture updates.

## FP-005 — ADR-008 Persistence Consistency Resolution

**Packet type:** Architecture decision gate.

**Objective:** Resolve architecture blocker AB-01 by selecting the consistency and recovery model for state mutation, SQLite append, projections, snapshots, and client publication.

**User or system value:** Prevents unrecorded state, divergent projections, and replay corruption.

**Architecture baseline references:** §§16.4, 19, 22, 28.4 AB-01, 31 ADR-008.

**Dependencies:** FP-003, FP-004.

**Affected modules:** ADR documentation and executable proof fixture only.

**Inputs:** Event repository port, lifecycle/state mutation semantics, SQLite capabilities, failure cases.

**Outputs:** Approved ADR-008 consistency section; sequence/transaction/recovery rules; minimal proof-of-concept results.

**Domain models:** Unit-of-work/result contract if selected.

**Events produced and consumed:** Demonstrate one state-changing event; no production event producer.

**REST or WebSocket changes:** Define publication-after-durability rule; no endpoint implementation.

**Persistence changes:** Select transaction/unit-of-work/outbox or equivalent and define projection/snapshot boundaries.

**Configuration changes:** None.

**Implementation constraints:** SQLite, one local process, events authoritative, append failure prevents dependent publication/action.

**Explicit non-goals:** Production repository, distributed transactions, external broker.

**Acceptance criteria:** ADR covers happy path, append failure, projection failure, process crash, idempotent retry, sequence allocation, recovery, and client publication order; product/architecture approval recorded.

**Unit tests:** Proof fixture demonstrates rollback/recovery invariant.

**Integration tests:** SQLite failure-injection proof using temporary database.

**Documentation updates:** ADR-008 status changed from open to approved; baseline amendment reference recorded.

**Completion evidence:** Approved ADR plus reproducible proof output.

**Rollback considerations:** Decision is superseded only by a new ADR; no production migration yet.

## FP-006 — SQLite Event Store and Session Projection

**Objective:** Implement the approved durable event repository, sequence allocation, session projection, migrations, and recovery behaviour.

**User or system value:** Makes authoritative session history durable from the beginning.

**Architecture baseline references:** §§15, 16.4, 19, 22; ADR-007 and approved ADR-008.

**Dependencies:** FP-004, FP-005.

**Affected modules:** Infrastructure persistence, migrations, application unit of work, session projection, tests.

**Inputs:** Ordered session events.

**Outputs:** Durable event rows, current session projection, query results.

**Domain models:** Event repository port implementation, projection checkpoint/version.

**Events produced and consumed:** Consume session events from FP-004; store without semantic mutation.

**REST or WebSocket changes:** None.

**Persistence changes:** Add `sessions`, `events`, migration/projection metadata; WAL, foreign keys, indexes, unique session sequence.

**Configuration changes:** Database path, migration mode, retention-independent storage settings.

**Implementation constraints:** No independent authoritative session writes; idempotent append; safe concurrent reads; Windows file handling.

**Explicit non-goals:** Command/radio/competency projections, snapshots, replay.

**Acceptance criteria:** Events survive restart; duplicate event/idempotency is safe; sequence is monotonic; projection rebuild matches live projection; injected append/projection failures follow ADR-008.

**Unit tests:** Repository mapping, projection reducer, duplicate handling, sequence validation.

**Integration tests:** Migration on empty/existing DB, restart recovery, failure injection, WAL reads.

**Documentation updates:** Database schema, migration and recovery runbook.

**Completion evidence:** Migration files, schema dump, restart/rebuild test report.

**Rollback considerations:** Migrations require downgrade or backup/restore plan; never delete authoritative event rows.

## FP-007 — Structured Logging, Health, and Component Status

**Objective:** Add correlated structured logs, health registry, metrics hooks, and component status events.

**User or system value:** Makes local failures diagnosable and supports preflight readiness.

**Architecture baseline references:** §§6.2, 11, 22, 24, 29.

**Dependencies:** FP-002, FP-004, FP-006.

**Affected modules:** Logging, health service, API health response, event producer, browser health display.

**Inputs:** Component status/latency/error updates.

**Outputs:** Structured local logs, health snapshot, health-change events.

**Domain models:** `ComponentHealth`, status/severity/reason, metric observation.

**Events produced and consumed:** Produce `component.health_changed`; later adapters consume health interface.

**REST or WebSocket changes:** Expand `GET /health` with readiness and components; no session stream yet.

**Persistence changes:** Persist material health-change events when session-scoped; logs remain separate files.

**Configuration changes:** Log level/path/rotation, health timeout; redact transcript/audio/secrets.

**Implementation constraints:** Health checks must not invoke cloud/network; no sensitive configuration in responses.

**Explicit non-goals:** External monitoring service, dashboards, model-specific checks.

**Acceptance criteria:** Readiness distinguishes healthy/degraded/unready; correlation IDs appear in request logs/events; sensitive values are redacted; browser shows status.

**Unit tests:** Health aggregation, redaction, transition deduplication.

**Integration tests:** API status changes when fake component fails/recovers; persisted session-scoped health event.

**Documentation updates:** Health/status definitions and troubleshooting guide skeleton.

**Completion evidence:** Sample redacted logs and failure/recovery test.

**Rollback considerations:** Health extensions remain backward compatible; disable optional file logging if needed.

## FP-008 — Session Lifecycle Application Service and REST API

**Objective:** Implement durable create/start/pause/resume/stop/fail session workflows and REST boundaries.

**User or system value:** Enables controlled, auditable session operation.

**Architecture baseline references:** §§11.2–11.3, 12.1, 17, 22; ADR-005, ADR-009.

**Dependencies:** FP-003, FP-004, FP-006, FP-007.

**Affected modules:** Application session service, API routes/DTOs, unit of work, session projection.

**Inputs:** Versioned session lifecycle requests and idempotency keys.

**Outputs:** Session summaries and lifecycle events.

**Domain models:** Session creation request/result, lifecycle error, failure reason.

**Events produced and consumed:** Produce all session lifecycle events; consume persisted current session state.

**REST or WebSocket changes:** Add session create/get/start/pause/resume/stop endpoints from baseline §17.

**Persistence changes:** Populate/rebuild session projection; pin effective configuration hash.

**Configuration changes:** Session data root, default seed policy, lifecycle request limits.

**Implementation constraints:** Invalid transitions return conflict with no event; idempotent retries do not duplicate lifecycle changes.

**Explicit non-goals:** Scenario initialisation, WebSocket, models, debrief/replay.

**Acceptance criteria:** Full legal lifecycle persists/restarts; invalid transitions are rejected; forced failure retains evidence; API errors use stable envelope.

**Unit tests:** Use-case transitions, idempotency, error mapping.

**Integration tests:** REST lifecycle against SQLite including restart and duplicate requests.

**Documentation updates:** OpenAPI examples and lifecycle operating notes.

**Completion evidence:** API contract snapshot and lifecycle integration report.

**Rollback considerations:** Maintain event/schema compatibility; route rollback must not orphan existing sessions.

## FP-009 — Versioned Scenario Schema and Loader

**Objective:** Implement YAML scenario schema, validation, catalogue, immutable version capture, and reference-scenario skeleton.

**User or system value:** Makes exercises reproducible and rejects invalid scenarios before readiness.

**Architecture baseline references:** §§5.1, 11.4, 12.8, 24, 29; ADR-015.

**Dependencies:** FP-002, FP-004, FP-008.

**Affected modules:** Scenario domain/schema/loader/catalogue, API scenario routes, fixtures.

**Inputs:** Local YAML files.

**Outputs:** Validated typed scenario and catalogue metadata/hash.

**Domain models:** Scenario metadata, geometry definitions, entities, schedules, objectives, error injections, end conditions.

**Events produced and consumed:** Produce `scenario.loaded` only during session initialisation in later wiring; schema defined now.

**REST or WebSocket changes:** Add scenario list/get routes.

**Persistence changes:** Pin scenario ID/version/hash in session projection; no scenario content table required.

**Configuration changes:** Scenario directory and validation strictness.

**Implementation constraints:** No arbitrary expressions/code in YAML; references/IDs validated; invalid scenario cannot reach `READY`.

**Explicit non-goals:** Simulation movement, scheduler execution, full reference scenario behaviour.

**Acceptance criteria:** Valid scenario loads deterministically; invalid geometry/reference/duplicate ID fails with precise location; catalogue exposes metadata only.

**Unit tests:** Schema fields, reference resolution, version/hash, malicious/unknown constructs.

**Integration tests:** Scenario API and session initialisation failure path.

**Documentation updates:** Scenario authoring guide and schema reference.

**Completion evidence:** Valid reference fixture plus invalid-fixture matrix.

**Rollback considerations:** Scenario schema versions remain available for persisted sessions; do not silently reinterpret old files.

## FP-010 — Aerodrome, Aircraft, and Runway Domain State

**Objective:** Implement canonical aircraft states, aerodrome geometry, explicit transition policy, entity versions, and single-authority runway occupancy.

**User or system value:** Establishes safe deterministic traffic state before movement or AI.

**Architecture baseline references:** §§10, 12.2–12.3, 29; ADR-003, ADR-005.

**Dependencies:** FP-004, FP-009.

**Affected modules:** Domain aircraft/runway/geometry/state policy, scenario mapping, tests.

**Inputs:** Validated initial scenario entities and requested domain transitions.

**Outputs:** Versioned entity state and typed state/occupancy facts.

**Domain models:** Aircraft, position, route, operational state, runway, holding point, occupancy.

**Events produced and consumed:** Define/produce via application wiring `aircraft.spawned`, `aircraft.state_changed`, `runway.occupancy_changed`.

**REST or WebSocket changes:** None.

**Persistence changes:** No new table; state derived from events until snapshot packet.

**Configuration changes:** None.

**Implementation constraints:** Only explicit legal transitions; `HOLDING` includes holding-point ID; occupancy mutation atomic with effect batch; no browser/provider DTO leakage.

**Explicit non-goals:** Kinematic movement, command extraction, radio.

**Acceptance criteria:** Reference entities map correctly; illegal transitions reject without mutation; duplicate occupancy is idempotent; state/entity versions advance consistently.

**Unit tests:** Transition matrix, terminal/phase states, geometry, occupancy add/remove, entity-version conflict.

**Integration tests:** Scenario-to-domain initialisation and authoritative event creation.

**Documentation updates:** Canonical state table and transition diagram.

**Completion evidence:** State/occupancy test matrix.

**Rollback considerations:** State names are event/schema compatible; changes require migration/ADR.

## FP-011 — Neutral Simulation Port and Deterministic Fake

**Objective:** Define and contract-test the neutral simulation command/effect interface with a deterministic fake provider.

**User or system value:** Protects the core from simulation-provider lock-in and enables tests before movement implementation.

**Architecture baseline references:** §§4.3, 11.5, 14, 29; ADR-006.

**Dependencies:** FP-004, FP-010.

**Affected modules:** Simulation port types, fake adapter, application effect translator, contract tests.

**Inputs:** `SimulationCommand` with expected entity version.

**Outputs:** `ApplyResult` and neutral `ProviderEffect` list.

**Domain models:** SimulationCommand, ApplyResult, ProviderEffect, rejection codes.

**Events produced and consumed:** Application translator produces aircraft/route/occupancy events; provider produces none.

**REST or WebSocket changes:** None.

**Persistence changes:** Effects translated/persisted through existing event unit of work.

**Configuration changes:** Provider selector defaults to fake only in tests.

**Implementation constraints:** Provider cannot allocate event identity/sequence or access API/database; expected-version conflict must reject.

**Explicit non-goals:** Real movement, external providers, Unity/BlueSky.

**Acceptance criteria:** Fake returns repeatable effects; all provider contract tests pass; translated events persist before publication hook.

**Unit tests:** Type validation, rejection codes, expected version, effect translation.

**Integration tests:** Fake command through application unit of work to durable events/projection.

**Documentation updates:** Simulation port contract and adapter-author guide.

**Completion evidence:** Contract-test suite runnable against any provider implementation.

**Rollback considerations:** Port changes are compatibility-sensitive; preserve v1 contracts once simple provider begins.

## FP-012 — Simple Deterministic Simulation Provider

**Objective:** Implement fixed-step ground/airborne movement and operational effects for the Phase 1 command vocabulary.

**User or system value:** Produces visible, reproducible aircraft behaviour without AI or external simulators.

**Architecture baseline references:** §§4.6, 5.1, 11.5, 12, 14, 16; ADR-006.

**Dependencies:** FP-010, FP-011.

**Affected modules:** Simple simulation adapter, clock, route follower, effect mapping, tests.

**Inputs:** Valid scenario state, seed, fixed steps, neutral simulation commands.

**Outputs:** Deterministic position/state/route/occupancy effects.

**Domain models:** Simulation clock/state, provider entity state, route progress.

**Events produced and consumed:** Consume accepted simulation commands via application; translate effects to `aircraft.state_changed`, `aircraft.route_assigned`, `runway.occupancy.changed`.

**REST or WebSocket changes:** None.

**Persistence changes:** Persist translated material effects; do not persist routine ticks.

**Configuration changes:** Tick rate and movement speeds as typed settings; final rates are BD-04 benchmark decisions.

**Implementation constraints:** No high-fidelity physics; deterministic math/order; provider remains database/API independent.

**Explicit non-goals:** Voice, pilot/radio, BlueSky, weather/wake/separation.

**Acceptance criteria:** Taxi/hold/line-up/take-off/final/land/go-around/vacate flows produce legal repeatable states; runway occupancy is correct; same seed/input yields same canonical effects.

**Unit tests:** Clock, route interpolation, each action, occupancy boundary, pause, conflict/rejection.

**Integration tests:** Reference scripted movement through durable event pipeline and restart projection.

**Documentation updates:** Simplified movement model and limitations.

**Completion evidence:** Determinism comparison report for scripted scenario.

**Rollback considerations:** Preserve stored effect/event semantics; movement tuning is configuration-compatible.

## FP-013 — Canonical Simulation Snapshots

**Objective:** Create, persist, validate, and restore versioned canonical state snapshots independent of browser DTOs.

**User or system value:** Enables efficient restart and future replay seek without weakening event authority.

**Architecture baseline references:** §§6.4, 11.10, 15.4, 19.4, 20; ADR-008.

**Dependencies:** FP-006, FP-010, FP-012.

**Affected modules:** Snapshot schema/repository, state reducer/restorer, migrations, tests.

**Inputs:** Authoritative domain/simulation state at a committed event sequence.

**Outputs:** Versioned snapshot with checksum, sequence, simulation time.

**Domain models:** CanonicalSessionSnapshot and nested entity/scenario state.

**Events produced and consumed:** Produce `simulation.snapshot_created`; consume ordered state events for reconstruction verification.

**REST or WebSocket changes:** None.

**Persistence changes:** Add `snapshots` table and indexes.

**Configuration changes:** Snapshot interval/retention placeholders; final values are BD-05.

**Implementation constraints:** Snapshot never replaces event history; schema is independent of transport DTO; create only after committed sequence.

**Explicit non-goals:** Replay UI/API, pruning authoritative events.

**Acceptance criteria:** Restore equals source canonical state; corrupted checksum/version is rejected; snapshot plus later events reaches same final state.

**Unit tests:** Serialization, checksum, version compatibility, reducer restore.

**Integration tests:** Persist/restart/reconstruct against SQLite and scripted simulation.

**Documentation updates:** Snapshot schema and recovery procedure.

**Completion evidence:** State-equivalence and corruption-test report.

**Rollback considerations:** Retain previous snapshot reader/migration; event-only reconstruction remains fallback.

## FP-014 — Versioned Session WebSocket Stream

**Objective:** Implement initial snapshot, sequenced deltas/events, multi-client observation, and reconnect/resynchronisation.

**User or system value:** Provides reliable real-time backend-owned state to the browser.

**Architecture baseline references:** §§11.2, 16.4, 18, 22; ADR-009.

**Dependencies:** FP-007, FP-008, FP-013.

**Affected modules:** Gateway, transport DTOs, publisher, client test harness.

**Inputs:** Durable committed events/projection/snapshots and client last-sequence subscription.

**Outputs:** Versioned WebSocket messages.

**Domain models:** None; map domain/projection to transport DTOs.

**Events produced and consumed:** Consume committed session/simulation/health events; produce no domain events.

**REST or WebSocket changes:** Add `/api/v1/sessions/{id}/stream` and baseline server message envelope; implement subscribe/resync.

**Persistence changes:** Query event gaps/snapshots; no new tables.

**Configuration changes:** Connection limits, heartbeat, gap retention/batch limits.

**Implementation constraints:** Publish only after durability; multiple observers allowed; slow clients cannot block simulation; no business logic.

**Explicit non-goals:** Browser rendering, PTT, replay controls.

**Acceptance criteria:** Client receives session state then snapshot; sequenced updates follow; reconnect fills gap or sends fresh snapshot; two clients receive consistent state.

**Unit tests:** DTO mapping, sequence/gap logic, backpressure policy.

**Integration tests:** WebSocket connection, update, disconnect/reconnect, multi-client, missing session.

**Documentation updates:** WebSocket protocol and reconnection examples.

**Completion evidence:** Contract capture and reconnect test logs.

**Rollback considerations:** Version messages; retain previous compatible envelope during any migration.

## FP-015 — Browser Session Shell and Aerodrome Display

**Objective:** Render authoritative session, aerodrome, aircraft, and runway state with connection/staleness handling.

**User or system value:** Provides the first usable browser view of deterministic traffic.

**Architecture baseline references:** §§7, 10, 11.1, 18, 29; ADR-001, ADR-002.

**Dependencies:** FP-009, FP-014.

**Affected modules:** Browser session store, WebSocket client, scenario/session screens, Canvas/SVG aerodrome components.

**Inputs:** Scenario catalogue/session REST and WebSocket snapshot/deltas.

**Outputs:** Visual runway/taxiway/holding points, aircraft/labels, lifecycle/health/connection state.

**Domain models:** Browser DTO models only; no domain authority.

**Events produced and consumed:** Consumes transport representations of session/simulation/health events; produces no domain events.

**REST or WebSocket changes:** Consume existing APIs; no new contract.

**Persistence changes:** None; optional browser preferences only.

**Configuration changes:** API/stream URL and visual interpolation settings.

**Implementation constraints:** No authoritative motion/occupancy logic; colour not sole state indicator; stale state clearly shown.

**Explicit non-goals:** PTT, radio, instructor, scoring, replay.

**Acceptance criteria:** User selects/creates/starts scenario; three reference aircraft render; updates/reconnect work; stale connection freezes authoritative indications; keyboard/focus basics pass.

**Unit tests:** Store reducers, DTO rendering, stale-state UI, label/occupancy components.

**Integration tests:** Browser against test backend through lifecycle and simulation update/reconnect.

**Documentation updates:** UI operation and authority limitation.

**Completion evidence:** Automated browser test and screenshots/video of deterministic display.

**Rollback considerations:** Browser-only rollback; retain transport compatibility.

## FP-016 — Structured Command Schema, Manual Input, and Validator

**Objective:** Implement the Phase 1 command catalogue, deterministic schema/state validator, command events/projection, and instructor-enabled text input.

**User or system value:** Proves the safe command-to-simulation boundary before speech or AI.

**Architecture baseline references:** §§4.2, 12.4, 13, 16.1, 17, 29; ADR-004.

**Dependencies:** FP-008, FP-010, FP-012, FP-014.

**Affected modules:** Command domain/schema, validator, application workflow, command projection, API route, browser diagnostic input.

**Inputs:** Structured/manual text command request, current session/entity/scenario state.

**Outputs:** Accepted/rejected/clarification/review result and optional neutral simulation dispatch.

**Domain models:** ATCCommand, command types/parameters, validation outcome/reason, extraction metadata.

**Events produced and consumed:** Produce `command.extracted`, accepted/rejected/clarification, `command.dispatched`; consume session/scenario/aircraft/occupancy state events.

**REST or WebSocket changes:** Add `POST /sessions/{id}/text-command`; add `command_result` stream message.

**Persistence changes:** Add rebuildable `commands` projection and projection migration.

**Configuration changes:** Manual-input feature flag; initial command confidence threshold.

**Implementation constraints:** `CONTACT_FREQUENCY` rejected; no direct entity mutation; every source uses same validator; stale expected version rejects.

**Explicit non-goals:** Transcript parsing, correction/readback, ASR/LLM, trainee-facing general text input.

**Acceptance criteria:** Every supported command validates against legal/illegal contexts; accepted commands alone dispatch; unsupported/ambiguous requests do not move aircraft; projection rebuilds from events.

**Unit tests:** Schema, parameter rules, each command prerequisite, conflict/ambiguity, reason codes.

**Integration tests:** Text command through API/events/provider/projection/WebSocket/browser state.

**Documentation updates:** Command catalogue, validation matrix, manual fallback warning.

**Completion evidence:** Command contract fixtures and validation coverage report.

**Rollback considerations:** Disable manual endpoint while preserving event/schema reader; do not delete command history.

## FP-017 — Clearance, Readback, Correction, and Action Gate

**Objective:** Implement clearances, expected/readback elements, disputed-action gating, backend correction correlation, and resolution events.

**User or system value:** Enforces safe readback behaviour and enables the central training correction loop.

**Architecture baseline references:** §§6.1, 12.5, 13.5, 16.2, 21, 29; ADR-004.

**Dependencies:** FP-016.

**Affected modules:** Clearance/readback domain and service, command workflow, projections, stream DTOs.

**Inputs:** Accepted ATC command, structured pilot response, controller correction candidate, current disputed clearances.

**Outputs:** Clearance/readback status, action-gate decision, correction correlation/result.

**Domain models:** Clearance, expected elements, structured readback, correction candidate/status, action gate.

**Events produced and consumed:** Consume command events; produce `clearance.issued`, readback received/incorrect, corrected, acknowledged.

**REST or WebSocket changes:** Extend command results and add clearance/readback stream payloads; no new REST route.

**Persistence changes:** Add rebuildable clearance/readback projection.

**Configuration changes:** Correction window placeholder; final value BD-06.

**Implementation constraints:** Trainee never supplies internal clearance ID; ambiguous correlation clarifies; disputed safety-critical action cannot dispatch.

**Explicit non-goals:** Pilot phrase rendering/TTS, competency scoring, instructor override.

**Acceptance criteria:** Correct readback opens gate; incorrect readback blocks; valid correction correlates by context/elements; ambiguous/late correction follows configured outcome; evidence persists/rebuilds.

**Unit tests:** Element comparison, gating, correlation, callsign/context ambiguity, timing boundary.

**Integration tests:** Command-to-clearance-to-readback/correction-to-simulation dispatch with SQLite.

**Documentation updates:** Clearance/readback state model and correction examples.

**Completion evidence:** Safety-gate test matrix.

**Rollback considerations:** Preserve clearance events; feature flag can block automatic dispatch while rolling back UI/service.

## FP-018 — Deterministic Virtual-Pilot Policy and Text Responses

**Objective:** Implement structured virtual-pilot accept/question/readback policy and deterministic template rendering without TTS or LLM.

**User or system value:** Provides repeatable pilot interaction before model integration.

**Architecture baseline references:** §§4.3, 11.7, 12.6, 16.1, 29; ADR-011.

**Dependencies:** FP-017.

**Affected modules:** Virtual-pilot domain/policy, templates, response DTOs, fake phrase/TTS boundary.

**Inputs:** Clearance, pilot profile, scenario/seed, error-free response policy.

**Outputs:** Structured response elements/type and rendered pilot text.

**Domain models:** PilotContext, PilotResponse, response types, reason codes, phrase-render request/result.

**Events produced and consumed:** Consume clearance events; create structured inputs for radio events in FP-021; no direct simulation events.

**REST or WebSocket changes:** Add pilot response/readback display payload through existing stream mapping.

**Persistence changes:** Structured response remains in clearance/radio projections after wiring.

**Configuration changes:** Template locale/profile and deterministic response delay defaults.

**Implementation constraints:** Templates cannot change authoritative elements; clarification uses response type and correlation; no free-form model content.

**Explicit non-goals:** Error injection, radio arbitration, audio/TTS, LLM wording.

**Acceptance criteria:** Supported clearance types yield correct structured/readable responses; question response carries reason/correlation; same input yields same output.

**Unit tests:** Response policy per clearance, callsign/number phrase templates, clarification metadata.

**Integration tests:** Accepted command through clearance and virtual-pilot structured response/action gate.

**Documentation updates:** Pilot policy and phrase-template rules.

**Completion evidence:** Golden structured response/template fixtures.

**Rollback considerations:** Retain structured response schema; fallback can remain text-only.

## FP-019 — Deterministic Scenario Error Injection

**Objective:** Implement seeded, bounded virtual-pilot readback errors defined by the scenario.

**User or system value:** Creates repeatable training errors required by Phase 1.

**Architecture baseline references:** §§4.6, 5.1, 11.4, 11.7, 12.8, 29; ADR-015.

**Dependencies:** FP-009, FP-018.

**Affected modules:** Scenario trigger engine, virtual-pilot error policy, validation, tests.

**Inputs:** Scenario injection definition, seed, trigger context, structured correct response.

**Outputs:** Structured incorrect response with error type/value and occurrence tracking.

**Domain models:** ErrorInjection, trigger, effect, probability, max occurrences, injected-response metadata.

**Events produced and consumed:** Consume command/clearance/scenario events; incorrect readback events retain injection metadata.

**REST or WebSocket changes:** No new contract; instructor/browser may display injection metadata only in instructor mode.

**Persistence changes:** Persist occurrence state via scenario/error event payload/projection.

**Configuration changes:** Global enable/disable and difficulty profile; scenario remains authority.

**Implementation constraints:** Seeded and bounded; cannot create unsupported runway/holding reference unless deliberately valid as an error value; no LLM-selected errors.

**Explicit non-goals:** Adaptive AI error selection, scoring, radio overlap.

**Acceptance criteria:** Reference wrong-runway readback occurs once for the recorded seed; disabled mode produces correct response; restart/replay does not reinject differently.

**Unit tests:** Trigger matching, seed repeatability, probability edges, max occurrence, error transformations.

**Integration tests:** Reference line-up clearance through injected wrong runway and blocked action gate.

**Documentation updates:** Scenario error-injection authoring section.

**Completion evidence:** Determinism run comparison and reference error trace.

**Rollback considerations:** Disable injection via session configuration without changing stored events.

## FP-020 — ADR-010 Radio Audibility Resolution

**Packet type:** Architecture decision gate.

**Objective:** Resolve architecture blocker AB-02 by defining Phase 1 blocked/partial-overlap audibility and evidence semantics.

**User or system value:** Ensures the required competing-transmission demonstration is implementable and assessable.

**Architecture baseline references:** §§11.8, 12.6, 16.3, 28.4 AB-02, 31 ADR-010.

**Dependencies:** FP-018, FP-019.

**Affected modules:** ADR and radio schema/test fixtures only.

**Inputs:** Baseline deterministic priority/no-barge-in rules and reference scenario need.

**Outputs:** Approved audibility states, overlap algorithm, event payloads, UI/audio/debrief representation, retry rule confirmation.

**Domain models:** Radio audibility/blocked reason enums and overlap outcome schema.

**Events produced and consumed:** Finalise payloads for queued/started/finished/blocked radio events.

**REST or WebSocket changes:** Finalise radio stream message shape; no implementation.

**Persistence changes:** Finalise radio projection fields.

**Configuration changes:** Define permitted overlap mode/probability/duration controls.

**Implementation constraints:** Deterministic, one frequency, no mid-transmission barge-in, no automatic retry.

**Explicit non-goals:** Multiple frequencies, realistic RF propagation, speech separation.

**Acceptance criteria:** ADR resolves fully-blocked versus partial audibility, simultaneous timing/ties, audio/text representation, replay, and competency evidence; approval recorded.

**Unit tests:** Executable policy examples/golden outcomes.

**Integration tests:** None beyond deterministic proof fixture.

**Documentation updates:** Approve ADR-010 and baseline amendment reference.

**Completion evidence:** Approved ADR and reference overlap timeline.

**Rollback considerations:** Supersede only through ADR; no production data yet.

## FP-021 — Deterministic One-Frequency Radio Engine

**Objective:** Implement queue, priorities, delays, transmission lifecycle, approved audibility/blocking, history, and transport projection.

**User or system value:** Creates repeatable operational radio behaviour and competing calls.

**Architecture baseline references:** §§11.8, 12.6, 15.2, 16.3, 21; approved ADR-010.

**Dependencies:** FP-018, FP-020.

**Affected modules:** Radio domain/application engine, scheduler, projections, stream DTOs, browser radio log.

**Inputs:** Controller/pilot/instructor transmission requests and simulation time.

**Outputs:** Ordered transmission/audibility results and history.

**Domain models:** RadioTransmission, queue priority, audibility, overlap/block reason, retry relationship.

**Events produced and consumed:** Produce radio queued/started/finished/blocked; consume clearance/pilot/session pause/resume events.

**REST or WebSocket changes:** Add `radio_event` stream payload; no new REST route.

**Persistence changes:** Add rebuildable `radio_transmissions` projection.

**Configuration changes:** Response delay, duration estimate, approved overlap controls/priorities.

**Implementation constraints:** One frequency; deterministic simulation-time ordering; in-progress call not interrupted; blocked is terminal.

**Explicit non-goals:** Multiple frequencies, live audio mixing beyond approved simple model, barge-in.

**Acceptance criteria:** Queue/priorities match ADR; reference blocked call occurs; events/projection/restart are consistent; browser log shows speaker, status, audibility.

**Unit tests:** Ordering, ties, pause, priority, blocking, overlap, no automatic retry.

**Integration tests:** Pilot/controller competing calls through durable events/WebSocket/browser log.

**Documentation updates:** Radio operational model and event examples.

**Completion evidence:** Deterministic radio timeline test/report.

**Rollback considerations:** Text-only sequential mode can be feature-flagged while preserving event compatibility.

## FP-022 — Deterministic Reference Scenario Vertical Slice

**Objective:** Complete the reference YAML schedules/objectives and run the full training logic without live speech or model adapters.

**User or system value:** Proves the complete deterministic core before AI integration.

**Architecture baseline references:** §§2–5, 16, 26, 27 Milestone 3.

**Dependencies:** FP-012, FP-015, FP-016–FP-021.

**Affected modules:** Reference scenario, scenario scheduler/objectives, browser session/radio display, end-to-end fixtures.

**Inputs:** Recorded seed and scripted structured/text commands.

**Outputs:** Complete arrival/taxi/departure/error/correction/blocked-call event history and final state.

**Domain models:** Existing models only.

**Events produced and consumed:** Exercise all implemented session/scenario/command/clearance/radio/simulation events.

**REST or WebSocket changes:** No new boundaries.

**Persistence changes:** Validate projections/snapshots under full deterministic flow.

**Configuration changes:** Reference seed and deterministic fixture profile.

**Implementation constraints:** No ASR/LLM/TTS; text/fixture inputs enter the real command validator; no direct test mutation.

**Explicit non-goals:** Competency score/debrief, replay UI, packaging.

**Acceptance criteria:** Reference flow reaches expected final state; wrong readback blocks until correction; blocked call occurs; repeat run yields same canonical projection; repository remains interactive/runnable.

**Unit tests:** Scenario schedule/objective predicates and end conditions.

**Integration tests:** Full deterministic end-to-end flow with SQLite, WebSocket, browser assertions.

**Documentation updates:** Deterministic demonstration script and expected timeline.

**Completion evidence:** Canonical event trace/hash and browser test recording.

**Rollback considerations:** Keep prior scenario schema versions; revert reference scenario version, not event history.

## FP-023 — Browser Push-to-Talk Audio Capture

**Objective:** Implement microphone permission, keyboard/button PTT, bounded recording, upload, and visible recording/processing/error states.

**User or system value:** Gives trainees the required voice interaction control.

**Architecture baseline references:** §§2, 6.7, 11.1, 16.1, 17, 23.

**Dependencies:** FP-015, FP-008.

**Affected modules:** Browser audio service/PTT component, API audio route shell, upload validation.

**Inputs:** Microphone stream and user PTT actions.

**Outputs:** Validated audio artifact/request with idempotency key and metadata.

**Domain models:** Audio submission DTO/status; no operational command.

**Events produced and consumed:** Produce PTT started/stopped and `audio.received`; no transcript event yet.

**REST or WebSocket changes:** Add `POST /sessions/{id}/audio`; show processing status via response/stream.

**Persistence changes:** Store metadata; raw bytes only according to current off-by-default retention setting.

**Configuration changes:** Input format, maximum duration/size, PTT key, retention flag.

**Implementation constraints:** Permission denial safe; one utterance per request; no automatic always-on recording; path/type validation.

**Explicit non-goals:** ASR, command extraction, audio playback.

**Acceptance criteria:** PTT records/uploads supported audio; too short/long/invalid rejected safely; duplicate idempotency does not duplicate event; keyboard and button states accessible.

**Unit tests:** PTT state machine, duration/size checks, permission/error UI.

**Integration tests:** Browser audio fixture upload through API/event persistence with retention on/off.

**Documentation updates:** Microphone permissions and PTT operation.

**Completion evidence:** Browser test/video and retention verification.

**Rollback considerations:** Disable microphone UI; deterministic text path remains usable.

## FP-024 — ASR Port, Deterministic Fake, and Transcript Workflow

**Objective:** Define the replaceable ASR contract and implement deterministic fixture/fake transcription through the real utterance workflow.

**User or system value:** Integrates audio-to-transcript safely before selecting a local model.

**Architecture baseline references:** §§4.3, 11.6, 11.11, 13.4, 22; ADR-011.

**Dependencies:** FP-007, FP-023.

**Affected modules:** ASR port/types, fake adapter, utterance service, transcript projection/stream mapping.

**Inputs:** Validated audio bytes/reference plus active callsign/aerodrome context.

**Outputs:** Transcript text, quality/confidence availability, warnings, processing metadata.

**Domain models:** ASRContext, TranscriptionResult, quality status.

**Events produced and consumed:** Consume audio.received; produce transcript.created/failed and adapter timeout/failed.

**REST or WebSocket changes:** Add `transcript_result` stream message; audio endpoint returns accepted processing ID.

**Persistence changes:** Add transcript storage/projection with text retained by default; no raw audio change.

**Configuration changes:** Adapter selector, timeout, language, confidence-unavailable policy.

**Implementation constraints:** Fake is deterministic; adapter cannot dispatch commands; failure creates no aircraft action.

**Explicit non-goals:** Local Whisper runtime, transcript parsing, calibration benchmark.

**Acceptance criteria:** Fixture audio produces expected transcript; timeout/failure is recoverable; transcript persists/rebuilds and reaches browser; no command action occurs.

**Unit tests:** Contract, fake mapping, timeout/cancellation, confidence unavailable, context bounds.

**Integration tests:** PTT fixture through fake ASR/event/projection/WebSocket.

**Documentation updates:** ASR adapter contract and fake-fixture guide.

**Completion evidence:** Contract suite and end-to-end fake transcript trace.

**Rollback considerations:** Keep text/manual path; select disabled ASR adapter.

## FP-025 — Deterministic Transcript Normaliser and Command Fast Path

**Objective:** Convert supported unambiguous transcripts into command candidates using deterministic normalisation, callsign resolution, and extraction.

**User or system value:** Provides predictable, low-latency command recognition without an LLM.

**Architecture baseline references:** §§11.6, 13.3–13.6, 16.1; ADR-004, ADR-011.

**Dependencies:** FP-016, FP-024.

**Affected modules:** Transcript normaliser, aviation vocabulary, callsign resolver, deterministic extractor, routing workflow.

**Inputs:** Transcript, active callsigns, scenario runways/holding points, current state.

**Outputs:** Structured command candidate or no-match/ambiguous result.

**Domain models:** NormalisedTranscript, resolved token/value, extraction result/method.

**Events produced and consumed:** Consume transcript.created; produce normal command events through FP-016.

**REST or WebSocket changes:** No new boundary.

**Persistence changes:** Record extraction method and source transcript in command projection.

**Configuration changes:** Vocabulary/profile and initial fast-path confidence policy.

**Implementation constraints:** Must not guess ambiguous callsign/runway; same input/context yields same candidate; all candidates use shared validator.

**Explicit non-goals:** Exhaustive natural language, LLM resolution, provider confidence calibration.

**Acceptance criteria:** Reference phrase variants/numbers/callsigns extract correctly; ambiguous/unsupported transcripts cause no action; correction/SAY_AGAIN supported.

**Unit tests:** Aviation numbers, runway designators, callsigns, compound noise, every supported command, ambiguity/no-match.

**Integration tests:** Fake ASR transcript through fast path/validator/reference scenario.

**Documentation updates:** Supported deterministic phrase patterns and limitations.

**Completion evidence:** Curated utterance corpus results and coverage report.

**Rollback considerations:** Disable fast path and retain manual command workflow; later LLM route must not bypass validator.

## FP-026 — LLM Port, Deterministic Fake, and Extraction Router

**Objective:** Define the local schema-constrained LLM port and route unresolved transcripts through a deterministic fake before real model integration.

**User or system value:** Proves safe LLM-assisted control flow without model/runtime risk.

**Architecture baseline references:** §§4.2–4.3, 11.6, 11.11, 13.4, 22; ADR-011.

**Dependencies:** FP-025.

**Affected modules:** LLM port/types, fake adapter, extraction router, schema-response parser, health tests.

**Inputs:** Bounded transcript/context and strict output schema.

**Outputs:** Candidate command or resolver failure/no-match with metadata.

**Domain models:** LLMResolutionRequest/Result, model metadata, routing decision.

**Events produced and consumed:** Consume unresolved transcript flow; produce command events only after shared validation; adapter failure events.

**REST or WebSocket changes:** No new public contract; health adds LLM fake status.

**Persistence changes:** Record extraction method/model metadata in command event/projection.

**Configuration changes:** Enable flag, adapter, timeout, bounded context, routing threshold.

**Implementation constraints:** Fake deterministic; raw output never executed; unknown fields/invalid JSON rejected; one shared validator remains authoritative.

**Explicit non-goals:** Real model, prompt optimisation, AI scoring or pilot content changes.

**Acceptance criteria:** No-match routes to fake; valid candidate validates; invalid/timeout causes clarification/no action; deterministic fast path does not unnecessarily invoke LLM.

**Unit tests:** Routing matrix, schema parser, bounded context, invalid output, timeout, validator reuse.

**Integration tests:** Fake ASR unresolved phrase through fake LLM to accepted/rejected command and events.

**Documentation updates:** LLM port, routing policy, safety boundary.

**Completion evidence:** Safe-failure integration traces.

**Rollback considerations:** Disable LLM route; deterministic/manual paths remain runnable.

## FP-027 — Local ASR Benchmark and Integration

**Objective:** Resolve BD-01 and integrate the selected local ASR adapter behind the approved port.

**User or system value:** Enables offline trainee speech recognition with measured performance.

**Architecture baseline references:** §§6.3, 8, 11.11, 24, 28.2 BD-01; ADR-011.

**Dependencies:** FP-024, FP-025; may run parallel with FP-028/FP-030 after mocks.

**Affected modules:** ASR adapter, model packaging/configuration, health/preflight, benchmark harness.

**Inputs:** Reference utterance corpus/audio, active vocabulary context.

**Outputs:** Local transcripts/quality metadata and approved benchmark decision.

**Domain models:** Existing ASR contract only.

**Events produced and consumed:** Existing transcript/adapter events.

**REST or WebSocket changes:** None.

**Persistence changes:** Record model/version/settings/latency metadata.

**Configuration changes:** Model path, device/compute/quantisation, timeout, calibrated quality policy.

**Implementation constraints:** Fully offline; no contract bypass; redistribution/licence documented; fake remains for tests.

**Explicit non-goals:** LLM extraction, model fine-tuning, cloud ASR.

**Acceptance criteria:** Selected adapter passes contract; reference callsign/number accuracy and p95 latency are reported; safe failure works; offline preflight verifies model.

**Unit tests:** Adapter mapping and error translation with mocked runtime.

**Integration tests:** Real local model on tagged hardware suite; fake remains default CI path.

**Documentation updates:** Benchmark report, model installation/licence, tuning/limitations.

**Completion evidence:** BD-01 decision record and signed benchmark results.

**Rollback considerations:** Switch adapter to fake/disabled; retain downloaded model separately and manual text fallback.

## FP-028 — Local LLM Benchmark and Integration

**Objective:** Resolve BD-02 and integrate a selected local schema-constrained LLM resolver behind the approved router.

**User or system value:** Improves supported utterance variability while preserving deterministic validation and offline operation.

**Architecture baseline references:** §§6.3, 8, 11.6, 11.11, 13.4, 28.2 BD-02; ADR-011.

**Dependencies:** FP-026; may run parallel with FP-027/FP-030.

**Affected modules:** LLM adapter, prompt/schema assets, model preflight/package config, benchmark harness.

**Inputs:** Unresolved reference utterance/context corpus.

**Outputs:** Schema-valid candidates/failures and benchmark decision.

**Domain models:** Existing LLM contract only.

**Events produced and consumed:** Existing command/adapter events; model metadata recorded.

**REST or WebSocket changes:** None.

**Persistence changes:** No new tables; record model/version/settings/latency in events/session metadata.

**Configuration changes:** Model path/quantisation/device, timeout, routing threshold, deterministic settings.

**Implementation constraints:** Offline, bounded context, strict schema, shared validation, no model output execution, fake retained for CI.

**Explicit non-goals:** AI scoring, model training, cloud LLM, unconstrained dialogue.

**Acceptance criteria:** Contract passes; invalid-output rate, command accuracy, p95 latency, memory are reported; unsafe candidates rejected; fast path remains primary for unambiguous supported forms.

**Unit tests:** Runtime-response mapping, schema failure, timeout/cancellation.

**Integration tests:** Tagged real-model corpus and full safe-failure path.

**Documentation updates:** BD-02 report, model install/licence, routing configuration.

**Completion evidence:** Benchmark decision and corpus result artifact.

**Rollback considerations:** Disable LLM route; deterministic/manual command paths remain operational.

## FP-029 — TTS Port, Deterministic Fake, and Text Fallback

**Objective:** Define replaceable TTS and phrase-render contracts, provide deterministic fake audio metadata, and guarantee text fallback.

**User or system value:** Integrates pilot-audio workflow safely before local voice selection.

**Architecture baseline references:** §§4.3, 11.7, 11.11, 22; ADR-011.

**Dependencies:** FP-018, FP-021.

**Affected modules:** TTS port/types, fake adapter, pilot rendering workflow, audio artifact service/player payload.

**Inputs:** Approved pilot text, voice/profile, radio-filter setting.

**Outputs:** Audio artifact reference/duration or typed failure plus visible text.

**Domain models:** TTSRequest/Result, voice metadata, artifact reference.

**Events produced and consumed:** Consume pilot/radio transmission request; adapter failures; radio events reference optional audio artifact.

**REST or WebSocket changes:** Extend radio message with safe local audio artifact URL/status; add artifact retrieval boundary if needed.

**Persistence changes:** Artifact metadata only; audio retention follows policy.

**Configuration changes:** Adapter/voice/rate/filter, timeout, artifact storage.

**Implementation constraints:** Structured readback elements cannot be changed by renderer; TTS failure never blocks state workflow; safe artifact paths.

**Explicit non-goals:** Real voice model, speech recognition, audio mixing beyond radio ADR.

**Acceptance criteria:** Fake supplies deterministic artifact metadata; browser plays fixture audio and always displays text; failure continues workflow.

**Unit tests:** Contract, artifact path validation, fallback, renderer element preservation.

**Integration tests:** Pilot response through fake TTS/radio/browser playback and failure path.

**Documentation updates:** TTS adapter and fallback contract.

**Completion evidence:** Audio/text fallback test recording.

**Rollback considerations:** Select text-only adapter; no operational state dependency on audio.

## FP-030 — Local TTS Benchmark and Integration

**Objective:** Resolve BD-03 and integrate selected local TTS voice(s) behind the approved port.

**User or system value:** Gives virtual pilots intelligible offline voices.

**Architecture baseline references:** §§6.3, 8, 11.11, 24, 28.2 BD-03; ADR-011.

**Dependencies:** FP-029; may run parallel with FP-027/FP-028.

**Affected modules:** TTS adapter, voice/model assets, packaging/preflight, benchmark harness.

**Inputs:** Reference pilot phrase corpus and voice settings.

**Outputs:** Local audio artifacts and benchmark decision.

**Domain models:** Existing TTS contract only.

**Events produced and consumed:** Existing adapter/radio events.

**REST or WebSocket changes:** None beyond existing artifact delivery.

**Persistence changes:** Record model/voice/settings/latency; artifacts follow retention.

**Configuration changes:** Model/voice paths, device, rate, filter, timeout.

**Implementation constraints:** Offline; documented licence; text fallback always available; no authoritative content alteration.

**Explicit non-goals:** Voice cloning, cloud TTS, advanced RF simulation.

**Acceptance criteria:** Contract passes; intelligibility/resource/real-time-factor results recorded; failure fallback verified; bundle preflight detects missing assets.

**Unit tests:** Adapter mapping and error translation with mocked runtime.

**Integration tests:** Tagged real-model generation/playback on reference hardware.

**Documentation updates:** BD-03 report, model/voice install/licences, operational settings.

**Completion evidence:** Benchmark artifacts and selected-provider record.

**Rollback considerations:** Switch to text-only/fake adapter without affecting session state.

## FP-031 — Rule-Based Competency Observations

**Objective:** Implement the required versioned event-consuming competency rules and evidence-linked observation projection.

**User or system value:** Converts operational events into objective training observations without AI authority.

**Architecture baseline references:** §§4.5, 11.9, 12.7, 21, 25; ADR-012.

**Dependencies:** FP-017, FP-019, FP-021, FP-022.

**Affected modules:** Competency rule engine, rule definitions, observation projection, stream DTOs/browser timeline.

**Inputs:** Ordered authoritative command, clearance, radio, simulation, and scenario events.

**Outputs:** Detected/resolved competency observations with evidence IDs.

**Domain models:** CompetencyObservation, RuleDefinition/Version, severity/category, resolution window.

**Events produced and consumed:** Consume relevant Phase 1 events; produce `competency.observation_detected` and resolved.

**REST or WebSocket changes:** Add `competency_observation` stream payload; expose observations through session/debrief query foundation.

**Persistence changes:** Add rebuildable competency-observation projection.

**Configuration changes:** Versioned rule profile and thresholds; correction/response-delay values referenced from effective config.

**Implementation constraints:** Pure event consumer; deterministic; evidence required; no LLM decisions; no operational state mutation.

**Explicit non-goals:** Score calculation, narrative debrief, adaptive coaching.

**Acceptance criteria:** All baseline §21 rule areas produce correct observations/resolutions; duplicate consumption is idempotent; replay/rebuild produces identical observation projection.

**Unit tests:** Each rule positive/negative/boundary case, evidence links, time windows, idempotency.

**Integration tests:** Reference error/correction, runway conflict, ambiguity, delay, and blocked-call timelines.

**Documentation updates:** Rule catalogue, versions, evidence and severity definitions.

**Completion evidence:** Rule traceability/coverage matrix.

**Rollback considerations:** Preserve rule versions and prior observations; disable new profile without rewriting history.

## FP-032 — Scoring and Evidence-Based Debrief

**Objective:** Implement versioned score calculation, category subscores, structured debrief facts, and deterministic Markdown rendering.

**User or system value:** Gives the trainee an understandable end-of-session assessment.

**Architecture baseline references:** §§4.5, 11.9, 20.2, 21; ADR-012.

**Dependencies:** FP-031, FP-009.

**Affected modules:** Scoring engine, debrief service/renderer, projections, REST route, browser debrief view.

**Inputs:** Final objectives, competency observations, session/scenario/config/rule metadata, evidence events.

**Outputs:** Overall/category scores and structured/Markdown debrief.

**Domain models:** ScoreProfile/Result, CategoryScore, Debrief, EvidenceLink.

**Events produced and consumed:** Consume observation/objective/session events; produce `score.updated`, `debrief.generated`.

**REST or WebSocket changes:** Implement `GET /sessions/{id}/debrief`; add score update stream payload.

**Persistence changes:** Add debrief/score projection/storage with version references.

**Configuration changes:** Versioned scoring profile; optional AI explanation remains disabled/default deterministic.

**Implementation constraints:** Start 100, deductions, clamp 0–100; rules alone determine score; every negative finding links evidence/replay time.

**Explicit non-goals:** LLM authority, replay engine, PDF output.

**Acceptance criteria:** Reference session yields expected scores/findings; rebuild deterministic; missing evidence blocks finding publication; browser presents categories/objectives/evidence/disclaimer.

**Unit tests:** Deductions, duplicate occurrences, clamp, categories, deterministic render, missing evidence.

**Integration tests:** Complete reference session finalisation to persisted debrief/API/browser.

**Documentation updates:** Scoring profile and debrief interpretation guide.

**Completion evidence:** Golden debrief fixture and traceability report.

**Rollback considerations:** Preserve old profile/renderer; regenerate only with explicit version and never rewrite original silently.

## FP-033 — Instructor Timeline Markers and Observation View

**Objective:** Add instructor mode, timeline markers, transcript/command/observation inspection, and visible attribution without override capability.

**User or system value:** Supports demonstration, review, and later replay navigation.

**Architecture baseline references:** §§7.1, 11.1, 17, 20, 23.

**Dependencies:** FP-014, FP-031, FP-032.

**Affected modules:** Instructor browser panel, marker application/API, event/projection, access-mode guard.

**Inputs:** Instructor-mode marker request with text/category/current simulation time.

**Outputs:** Attributed timeline marker and inspection views.

**Domain models:** InstructorMarker, local instructor identity/mode.

**Events produced and consumed:** Produce `instructor.marker_added`; consume transcript/command/observation/radio events for view.

**REST or WebSocket changes:** Implement `POST /sessions/{id}/markers`; stream marker event.

**Persistence changes:** Marker derived from authoritative event; no separate authority table required.

**Configuration changes:** Instructor mode enable and identity representation (IC-08).

**Implementation constraints:** Visible attribution; markers do not mutate operational state/score; trainee display separation.

**Explicit non-goals:** Instructor override, user accounts, remote instructor station.

**Acceptance criteria:** Instructor can add/view marker at current sim time; marker persists/rebuilds; trainee cannot invoke route when instructor mode disabled; inspection data correlates correctly.

**Unit tests:** Mode guard, validation, attribution, event mapping.

**Integration tests:** Browser marker through API/event/stream and debrief timeline.

**Documentation updates:** Instructor-mode and marker operation.

**Completion evidence:** Browser test and audit-event example.

**Rollback considerations:** Disable instructor panel/route; historical marker events remain readable.

## FP-034 — Instructor Override Scope Decision

**Packet type:** Product/architecture decision gate.

**Objective:** Resolve architecture blocker AB-03 by deciding whether audited instructor override is required in Phase 1.

**User or system value:** Prevents an ambiguous safety-bypass capability from entering implementation without product approval.

**Architecture baseline references:** §§13.5, 17, 21, 23, 28.4 AB-03, 29; ADR-004, ADR-009, ADR-012.

**Dependencies:** FP-017, FP-031, FP-033.

**Affected modules:** ADR/product decision record and contract fixtures only.

**Inputs:** Training use case, action-gate policy, instructor workflow, audit/debrief needs.

**Outputs:** Approved decision: include or disable/defer; if included, final endpoint/action/event/UI/score semantics.

**Domain models:** Final InstructorOverride request/result if included.

**Events produced and consumed:** Finalise `instructor.override_applied` or mark reserved/deferred.

**REST or WebSocket changes:** Finalise or remove `/instructor-overrides` from Phase 1 contract.

**Persistence changes:** Finalise audit/projection requirements if included.

**Configuration changes:** Finalise enable/confirmation/identity settings if included.

**Implementation constraints:** Must never appear as normal acknowledgement or erase competency evidence; reason and attribution mandatory.

**Explicit non-goals:** Implementation, remote identity management.

**Acceptance criteria:** Product-owner decision recorded; affected ADR/API/event/test/baseline status updated; no ambiguous optional endpoint remains.

**Unit tests:** Contract fixture validation if included.

**Integration tests:** None.

**Documentation updates:** ADR-009/012 and architecture blocker register.

**Completion evidence:** Signed decision record.

**Rollback considerations:** Supersede only through change control.

## FP-035 — Audited Instructor Override Implementation

**Packet status:** Conditional; create/implement only if FP-034 includes override in Phase 1.

**Objective:** Implement the approved, separately audited instructor intervention without altering original readback/competency evidence.

**User or system value:** Allows controlled demonstration recovery or instructor intervention when explicitly authorised.

**Architecture baseline references:** §§17, 21, 23, 29 and approved FP-034/ADR decisions.

**Dependencies:** FP-034 decision to include; FP-017, FP-031, FP-033.

**Affected modules:** Override domain/application/API, audit event, browser confirmation UI, debrief projection.

**Inputs:** Clearance ID, action, reason, confirmation, instructor identity/mode.

**Outputs:** Override result, action-gate intervention, visible audit/debrief record.

**Domain models:** InstructorOverride.

**Events produced and consumed:** Consume disputed clearance/current state; produce `instructor.override_applied` and resulting simulation events through normal pipeline.

**REST or WebSocket changes:** Implement approved endpoint and stream/audit payload.

**Persistence changes:** Rebuildable override audit projection if required.

**Configuration changes:** Enable flag, confirmation policy, identity.

**Implementation constraints:** No parser path; no ordinary acknowledgement; original observation/score evidence retained; stale/invalid target rejected.

**Explicit non-goals:** Automated overrides, trainee access, hiding intervention.

**Acceptance criteria:** Authorised confirmed override is visible/audited; unauthorised/unconfirmed/stale attempts fail; underlying incorrect-readback observation remains; resulting action uses normal simulation event pipeline.

**Unit tests:** Guard, reason/confirmation, stale state, evidence preservation.

**Integration tests:** Browser/API override through event/simulation/debrief/restart.

**Documentation updates:** Instructor override operating and audit procedure.

**Completion evidence:** Audit trace and safety/evidence tests.

**Rollback considerations:** Disable endpoint via configuration; historical override events remain supported.

## FP-036 — ADR-008 Failed-History Replay Integrity Resolution

**Packet type:** Architecture decision gate.

**Objective:** Resolve architecture blocker AB-04 by defining minimum valid history, snapshot/event corruption handling, and valid-prefix behaviour.

**User or system value:** Prevents replay from presenting fabricated or silently incomplete state.

**Architecture baseline references:** §§20.1, 22, 28.4 AB-04, 31 ADR-008.

**Dependencies:** FP-006, FP-013, FP-032.

**Affected modules:** ADR, integrity validator contract, test fixtures only.

**Inputs:** Completed/stopped/failed histories, snapshot checksums, sequence gaps/corrupt suffix cases.

**Outputs:** Approved integrity states and replay/refusal/diagnostic rules.

**Domain models:** ReplayIntegrityResult/status/reason and valid sequence range.

**Events produced and consumed:** Define diagnostic handling; do not rewrite source events.

**REST or WebSocket changes:** Finalise replay-create error/result fields.

**Persistence changes:** Define integrity metadata/check process.

**Configuration changes:** None unless approved maximum diagnostic tolerance.

**Implementation constraints:** Source session remains terminal; no silent gap filling; valid-prefix view clearly labelled if permitted.

**Explicit non-goals:** Replay implementation, event repair, deleting corrupt data.

**Acceptance criteria:** ADR covers missing snapshot, invalid checksum, sequence gap, unknown schema, append-failure suffix, valid prefix, and export diagnostics; approval recorded.

**Unit tests:** Golden integrity decision fixtures.

**Integration tests:** SQLite corruption/gap proof fixture.

**Documentation updates:** Approve ADR-008 replay-integrity section.

**Completion evidence:** Approved ADR and fixture results.

**Rollback considerations:** Supersede only by ADR; source records untouched.

## FP-037 — Replay Reducer, Integrity Validation, and REST API

**Objective:** Implement read-only replay creation, integrity checks, snapshot/event reduction, seek, speed state, and source-session separation.

**User or system value:** Lets trainees/instructors reconstruct evidence without rerunning AI or mutating history.

**Architecture baseline references:** §§4.4, 11.10, 16.5, 20.1, 22; approved ADR-008.

**Dependencies:** FP-013, FP-031, FP-032, FP-036.

**Affected modules:** Replay service/reducers/integrity validator, REST routes, replay stream mapping.

**Inputs:** Source session ID, target simulation time, stored snapshot/events.

**Outputs:** Read-only ReplayView/state/timeline and integrity result.

**Domain models:** ReplayView, ReplayState, integrity result, reducer registry.

**Events produced and consumed:** Consume stored events; no operational events; replay control is view state, not source event mutation.

**REST or WebSocket changes:** Implement `POST /replays` and `/replays/{id}/seek`; provide `replay_state` messages through defined boundary.

**Persistence changes:** Optional transient/local replay-view metadata only; source history unchanged.

**Configuration changes:** Replay cache and reducer compatibility settings.

**Implementation constraints:** Never call ASR/LLM/TTS/live scheduler; explicit schema compatibility; source lifecycle unchanged.

**Explicit non-goals:** Browser replay controls, export, video recording.

**Acceptance criteria:** Seek reconstructs expected state; failed valid history opens per ADR; corrupt history follows exact refusal/prefix rule; final replay equals authoritative final snapshot; evidence timestamps resolve.

**Unit tests:** Reducers by event type, seek, schema versions, integrity statuses, source immutability.

**Integration tests:** Completed/stopped/failed/corrupt histories through API and SQLite.

**Documentation updates:** Replay API, reducer compatibility, integrity diagnostics.

**Completion evidence:** Replay equivalence and corruption matrix report.

**Rollback considerations:** Replay is read-only; disable endpoint while preserving source data.

## FP-038 — Browser Replay and Evidence Navigation

**Objective:** Implement clearly labelled replay UI with play/pause/seek/speed/event step and jumps to observations/markers.

**User or system value:** Makes debrief evidence explorable without confusing replay with live control.

**Architecture baseline references:** §§11.1, 20, 26.

**Dependencies:** FP-033, FP-037.

**Affected modules:** Browser replay store/screen/controls, aerodrome/radio timeline reuse, debrief links.

**Inputs:** Replay REST/state stream and observation/marker timestamps.

**Outputs:** Read-only reconstructed visual/timeline state.

**Domain models:** Browser Replay DTO/state only.

**Events produced and consumed:** Consumes replay state; produces no domain events.

**REST or WebSocket changes:** Consume existing replay boundaries; no new API.

**Persistence changes:** None.

**Configuration changes:** Client playback speed defaults.

**Implementation constraints:** Prominent replay label; live PTT/commands disabled; source outcome visible; integrity warnings not hidden.

**Explicit non-goals:** Editing history, video export, rerunning models.

**Acceptance criteria:** All baseline controls work; jump from debrief observation/marker reaches correct time; final state matches live recorded state; accessibility/stale handling pass.

**Unit tests:** Replay store/timer, control states, link navigation, read-only enforcement.

**Integration tests:** Browser E2E across seek/speed/marker/evidence and failed-session warning.

**Documentation updates:** Replay user guide.

**Completion evidence:** Browser automation recording and state-equivalence assertion.

**Rollback considerations:** Disable replay UI route; API/source data remain intact.

## FP-039 — Checksummed Offline Session Export

**Objective:** Produce and validate a self-contained offline session export bundle.

**User or system value:** Enables portable review, audit, and troubleshooting without cloud services.

**Architecture baseline references:** §§20.3, 23, 24.

**Dependencies:** FP-032, FP-037.

**Affected modules:** Export service, manifest/checksum schema, artifact route, validation utility.

**Inputs:** Source session, events, debrief, scenario/config/rule/schema metadata, permitted artifacts.

**Outputs:** Bundle containing manifest, JSONL events, summaries/debriefs, metadata, optional audio.

**Domain models:** ExportManifest, ManifestEntry/checksum, export result.

**Events produced and consumed:** Read events only; export generation need not create a domain event unless baseline event catalogue is compatibly extended through change control.

**REST or WebSocket changes:** Implement `GET /sessions/{id}/export` and safe artifact download.

**Persistence changes:** Add artifact metadata/checksum/retention record.

**Configuration changes:** Export directory, archive format, audio inclusion policy.

**Implementation constraints:** Safe paths; no secrets; respect retention; deterministic manifest ordering; local-only.

**Explicit non-goals:** Cloud upload, PDF/video, import/merge.

**Acceptance criteria:** Bundle validates checksums offline; contains required baseline items; excludes raw audio by default; corrupt bundle fails validator; failed-session diagnostic export follows ADR.

**Unit tests:** Manifest ordering/checksum, path sanitisation, retention inclusion.

**Integration tests:** Generate/download/validate completed and failed session exports.

**Documentation updates:** Export format and validation instructions.

**Completion evidence:** Sample validated bundle and validator report.

**Rollback considerations:** Disable export route; existing bundles remain readable under versioned manifest.

## FP-040 — Privacy, Retention, and Local Artifact Controls

**Objective:** Implement raw-audio opt-in, transcript/artifact retention policy, deletion workflow, log redaction, and recorded effective policy.

**User or system value:** Protects trainee data while retaining required evidence.

**Architecture baseline references:** §§6.6, 19, 23, 28.2 BD-07; ADR-014.

**Dependencies:** FP-023, FP-024, FP-029, FP-039.

**Affected modules:** Settings, artifact repository, retention service, browser instructor settings, logs, operating scripts.

**Inputs:** Effective retention settings, session end time, deletion request.

**Outputs:** Retained/deleted artifacts and auditable policy metadata.

**Domain models:** RetentionPolicy, artifact class/status, deletion result.

**Events produced and consumed:** Consume session finalisation; do not delete authoritative events required by baseline unless an approved whole-session deletion policy says so.

**REST or WebSocket changes:** Add local retention status/deletion endpoint only if needed; otherwise operating script/UI action with typed boundary.

**Persistence changes:** Artifact retention/deletion timestamps/status; transcript duration value; raw audio default off.

**Configuration changes:** Resolve BD-07; durations by artifact class and deletion schedule.

**Implementation constraints:** No secret/transcript leakage in logs; deletion targets validated under session storage; exports respect policy.

**Explicit non-goals:** Enterprise records management, cloud backup, legal-policy certification.

**Acceptance criteria:** Raw audio absent by default; opt-in policy recorded; transcript/artifact expiry works; deletion cannot escape storage root; debrief evidence behaviour documented when data expires.

**Unit tests:** Retention calculation, safe deletion paths, redaction, policy capture.

**Integration tests:** Sessions with retention on/off, expiry/deletion, export inclusion, restart.

**Documentation updates:** Privacy notice, retention defaults, deletion/recovery guidance.

**Completion evidence:** BD-07 record and retention test report.

**Rollback considerations:** Disable automatic deletion before rollback; never restore deleted data implicitly.

## FP-041 — Offline Packaging, Preflight, Startup, and Shutdown

**Objective:** Deliver a versioned Windows offline bundle with one-action startup, model/scenario/database preflight, browser launch, and controlled shutdown.

**User or system value:** Makes the prototype reliably demonstrable without development tooling or internet.

**Architecture baseline references:** §§4.7, 23, 24, 27 Milestone 7.

**Dependencies:** FP-027, FP-028, FP-030, FP-039, FP-040; LLM may be disabled if benchmark decision selects deterministic-only operation.

**Affected modules:** Packaging/build, startup/verification/shutdown scripts, model manifest, licences/notices, operations docs.

**Inputs:** Application builds, migrations, scenarios/config, selected local models, checksums.

**Outputs:** Offline installation/bundle and health-ready running application.

**Domain models:** Bundle/component manifest only.

**Events produced and consumed:** Existing health/session failure events during startup; no new required domain event.

**REST or WebSocket changes:** None.

**Persistence changes:** Create/verify data directories and migrations; preserve existing sessions on upgrade.

**Configuration changes:** Packaged production defaults and explicit local override path.

**Implementation constraints:** No runtime download; loopback binding; hidden background helper windows unless user-facing; checksums/licences included.

**Explicit non-goals:** Installer auto-update, cloud deployment, multi-machine service.

**Acceptance criteria:** Clean reference laptop starts with one documented action offline; missing model/port/storage/migration produces actionable preflight failure; controlled shutdown finalises safely; upgrade preserves sessions.

**Unit tests:** Manifest/checksum/preflight logic.

**Integration tests:** Package install/start/stop/restart/upgrade in clean Windows test environment.

**Documentation updates:** Installation, operation, troubleshooting, licences/notices.

**Completion evidence:** Offline installation recording and verification report.

**Rollback considerations:** Versioned side-by-side bundle and database backup/migration downgrade policy.

## FP-042 — Failure Recovery and Performance Hardening

**Objective:** Validate degraded modes, tune benchmarked rates/timeouts/snapshots, and meet reliability/performance targets.

**User or system value:** Makes the demonstration resilient and responsive on the reference laptop.

**Architecture baseline references:** §§6, 22, 25.7, 28.2 BD-04/BD-05.

**Dependencies:** FP-037, FP-041.

**Affected modules:** All runtime components, failure injectors, benchmark harness, configuration profiles.

**Inputs:** Reference scenario/corpus, fault scripts, performance telemetry.

**Outputs:** Approved BD-04/BD-05 values, tuned configuration, fixed defects, performance/recovery report.

**Domain models:** Existing timing/health/failure types.

**Events produced and consumed:** Validate adapter/system failure and timing-anomaly events; no new unapproved events.

**REST or WebSocket changes:** Only compatible corrections; contract changes require change control.

**Persistence changes:** Validate crash/restart, append failure, snapshot interval, DB size/seek.

**Configuration changes:** Final tick/publication/snapshot rates, timeouts, queue limits, backoff.

**Implementation constraints:** Measure before tuning; no cloud fallback; deterministic semantics preserved; no hidden reduction of rule coverage.

**Explicit non-goals:** New product features, major architecture changes, certification.

**Acceptance criteria:** Performance targets reported; ASR/LLM/TTS/database/WebSocket failures follow baseline; reference scenario completes 19/20 preliminary runs; replay final state remains equal.

**Unit tests:** Any defect regression tests.

**Integration tests:** Full fault matrix, load/latency, crash/restart, reconnect, snapshot seek.

**Documentation updates:** Benchmark decisions, reference hardware, recovery runbook, known limits.

**Completion evidence:** Signed performance/failure/reliability report.

**Rollback considerations:** Retain last known-good configuration and bundle; performance tuning changes separately reversible.

## FP-043 — Phase 1 Release Acceptance Campaign

**Objective:** Execute and document the complete baseline §26 offline release acceptance test and traceability review.

**User or system value:** Provides objective evidence that Phase 1 satisfies the authoritative baseline.

**Architecture baseline references:** §§2–6, 26, 29–32.

**Dependencies:** FP-001, FP-001A, FP-001B, FP-002–FP-042, except FP-035 only if FP-034 includes it.

**Affected modules:** Test evidence, release manifest, traceability matrix, defect records, documentation only unless defects are found.

**Inputs:** Release candidate bundle, reference laptop, scenario/seed, model/config/schema/rule versions.

**Outputs:** Acceptance results, 20-run reliability evidence, release decision, checksummed evidence bundle.

**Domain models:** None.

**Events produced and consumed:** Validate the complete authoritative catalogue and canonical projections.

**REST or WebSocket changes:** None; any required change returns to change control and earlier packet.

**Persistence changes:** None beyond test sessions/evidence.

**Configuration changes:** Freeze release profile and hashes.

**Implementation constraints:** Laptop disconnected from networks; no waiver hidden in results; every failure recorded/retested; no feature work inside acceptance packet.

**Explicit non-goals:** Feature expansion, Unity/BlueSky/cloud/distributed testing.

**Acceptance criteria:** All 20 baseline steps pass; 19/20 reliability achieved; traceability complete; no unresolved architecture blocker; product owner approves release evidence.

**Unit tests:** None newly required; verify all suites pass.

**Integration tests:** Execute full release acceptance campaign and failure demonstrations.

**Documentation updates:** Final release notes, known limitations, test report, baseline/ADR/schema/model hashes.

**Completion evidence:** Signed acceptance report and checksummed evidence bundle.

**Rollback considerations:** Reject release candidate and retain previous bundle; defects return to responsible packet/new issue under change control.

# 4. Recommended GitHub Issue Order

Create issues in packet ID order. Keep future issues in “Blocked/Planned” state until dependencies close. Recommended merge order is:

1. FP-001, FP-001A, FP-001B, FP-002–FP-004: runnable foundation, local model preservation, acquisition tooling, and contracts.
2. FP-005: close AB-01 before durable state integration.
3. FP-006–FP-015: persistence, scenario, deterministic simulation, live browser.
4. FP-016–FP-019: deterministic command/pilot/error core.
5. FP-020: close AB-02 before radio implementation.
6. FP-021–FP-026: deterministic vertical slice and model fakes.
7. FP-027–FP-030: local model benchmarks/integration.
8. FP-031–FP-033: competency, debrief, instructor review.
9. FP-034 followed by FP-035 only if override is approved.
10. FP-036: close AB-04 before replay.
11. FP-037–FP-040: replay, export, privacy.
12. FP-041–FP-043: packaging, hardening, release acceptance.

GitHub labels should include milestone, component, packet type (`implementation`, `architecture-decision`, `benchmark`, `conditional`), critical path, and blocked-by IDs.

# 5. Milestone Allocation

| Milestone | Packets | Exit gate |
|---|---|---|
| M1 — Architecture foundation | FP-001, FP-001A, FP-001B, FP-002–FP-008 | Durable events/session lifecycle, health, runnable repository, AB-01 closed |
| M2 — Scenario and deterministic simulation | FP-009–FP-015 | Deterministic scripted traffic visible in browser and reconstructable |
| M3 — Command, pilot, error, and radio core | FP-016–FP-022 | Full reference training logic works without live models; AB-02 closed |
| M4 — Local speech/language | FP-023–FP-030 | Offline voice loop uses fakes in CI and benchmarked local adapters on reference hardware |
| M5 — Competency and debrief | FP-031–FP-035 | Evidence-linked findings/score/debrief; AB-03 resolved; override implemented only if approved |
| M6 — Replay and export | FP-036–FP-039 | AB-04 closed; replay equivalence and offline export validation pass |
| M7 — Packaging and hardening | FP-040–FP-043 | Offline package, privacy, performance/reliability, and release campaign pass |

# 6. Critical-Path Packets

The primary critical path is:

```text
FP-001 -> 001A -> 001B -> 002 -> 003 -> 004 -> 005 -> 006 -> 008 -> 009 -> 010
-> 011 -> 012 -> 013 -> 014 -> 015 -> 016 -> 017 -> 018 -> 019
-> 020 -> 021 -> 022 -> 023 -> 024 -> 025 -> 026 -> 027/028/029/030
-> 031 -> 032 -> 036 -> 037 -> 038/039 -> 040 -> 041 -> 042 -> 043
```

Critical decision gates are FP-005, FP-020, FP-034, and FP-036. FP-034 does not block unrelated competency/debrief work, but it blocks final instructor REST scope and release contract freeze.

# 7. Packets That May Run in Parallel

Parallel work is permitted only after shared dependency contracts are merged:

- FP-001A must merge after FP-001. FP-001B must then merge after FP-001A and before FP-002. Early FP-002 design may proceed while FP-001B is being reviewed, but FP-002 must not merge until FP-001B is complete. Early FP-003 design may overlap FP-002, but FP-002 merges first if FP-003 uses settings.
- FP-007 observability can overlap late FP-006 repository work after event/persistence interfaces stabilise.
- FP-009 scenario schema and FP-010 domain design can be developed in parallel, but FP-010 merges after scenario mapping contracts.
- FP-013 snapshots and FP-014 WebSocket design can overlap after FP-012, but FP-014 requires the snapshot contract.
- FP-015 browser display can develop against FP-014 contract fakes while backend stream implementation completes.
- FP-018 virtual-pilot policy and FP-019 error-injection design can overlap after FP-017, with FP-019 merging after FP-018.
- FP-023 browser PTT may run in parallel with FP-024 ASR-port design after audio REST shape is agreed.
- FP-027 local ASR, FP-028 local LLM, and FP-030 local TTS benchmarks may run in parallel after FP-024, FP-026, and FP-029 respectively.
- FP-029 TTS fake can run in parallel with FP-025/FP-026 because it depends on the pilot/radio core, not extraction.
- FP-031 competency engine and FP-033 instructor marker UI may overlap after event/stream contracts, but FP-033 observation view completes after FP-031.
- FP-034 product decision can run while FP-031–FP-033 are implemented.
- FP-039 export design can overlap FP-038 browser replay after FP-037 API/reducer contracts stabilise.
- FP-040 privacy controls can begin against artifact contracts while FP-039 completes.

Do not parallelise two packets that both change the same authoritative schema until one establishes the versioned contract.

# 8. Complete GitHub Issue Text — FP-001

## Title

`FP-001: Establish runnable repository and application foundation`

## Body

### Feature packet

**ID:** FP-001  
**Milestone:** M1 — Architecture foundation  
**Type:** Implementation  
**Critical path:** Yes  
**Dependencies:** None

### Objective

Create the smallest runnable ATC Portable Trainer repository containing a local FastAPI backend, React/TypeScript/Vite browser application, pinned development toolchains, automated test commands, and enforced architecture boundaries.

This issue establishes the base for every later Phase 1 packet. It must not implement training or simulation features prematurely.

### User or system value

- A developer can clone the repository, install dependencies, start the backend and browser, and confirm local health using documented Windows commands.
- The default branch remains runnable from the first merge.
- Automated checks prevent application/infrastructure dependencies from leaking into the domain layer.

### Architecture baseline references

- §1 — Document Control
- §8 — Approved Technology Stack
- §9 — Component Architecture
- §24 — Offline Deployment
- §25 — Testing Strategy
- §29 — Architectural Constraints
- ADR-003 — Layering, dependency direction, and domain-owned ports

### Required repository shape

Create only the files needed for this issue under stable top-level boundaries:

```text
apps/
  api/
  web/
packages/
  domain/
  application/
  infrastructure/
tests/
scripts/
docs/
```

Subdirectories may differ if the same ownership and dependency rules are preserved. Do not create empty future feature modules merely to anticipate later packets.

### Scope

1. Configure the Python project with pinned FastAPI, Pydantic, Uvicorn, test, lint, and type-check dependencies.
2. Add a FastAPI application that binds to loopback by default.
3. Add `GET /health` returning a typed response indicating that the API process is running.
4. Create a Vite React TypeScript application.
5. Display backend reachability/health in the browser.
6. Configure backend unit tests and frontend unit tests.
7. Configure lint, formatting, and type-check commands.
8. Add an automated architecture-boundary check proving that domain code cannot import application entry points or infrastructure adapters.
9. Add a Windows development script or documented command sequence that starts the applications without requiring cloud services.
10. Add a production frontend build check.

### Affected modules

- Root project/tooling files
- `apps/api`
- `apps/web`
- Initial package boundary markers under `packages`
- `tests`
- `scripts`
- Root README

### Inputs

- Architecture Baseline v1.0 technology and dependency rules.
- Local development environment.

### Outputs

- Runnable local backend.
- Runnable local browser application.
- Typed health response.
- Repeatable backend/frontend test and build commands.
- Automated dependency-boundary enforcement.
- Windows quick-start documentation.

### Domain models

None. Do not create session, aircraft, scenario, command, radio, competency, or replay models in this issue.

### Events produced or consumed

None. The event envelope is introduced by FP-004.

### REST and WebSocket changes

Add:

```text
GET /health
```

Minimum response:

```json
{
  "status": "ok"
}
```

Do not add a WebSocket endpoint.

### Persistence changes

None. Do not add SQLite, migrations, session files, or event storage.

### Configuration changes

Only minimal development defaults required to start the API and point the browser to it. FP-002 introduces the typed configuration system.

Do not add secrets or cloud credentials.

### Implementation constraints

- Use React, TypeScript, and Vite for the browser.
- Use Python, FastAPI, Pydantic, and Uvicorn for the backend.
- Bind backend services to loopback by default.
- Domain packages must not import `apps` or concrete infrastructure packages.
- Do not add cloud SDKs or required network services.
- All documented commands must work on Windows.
- Keep the repository runnable after this issue merges.
- Preserve user-owned or unrelated existing files.

### Explicit non-goals

- Session lifecycle or scenario selection.
- SQLite or event persistence.
- Aircraft, runway, simulation, or WebSocket implementation.
- ASR, LLM, TTS, radio, virtual pilots, scoring, replay, or debrief.
- Unity, BlueSky, cloud services, containers as a runtime requirement, or distributed deployment.
- Production installer or final offline bundle.

### Acceptance criteria

- [ ] A documented backend install/start command completes successfully on Windows.
- [ ] `GET /health` returns HTTP 200 with the typed `{"status":"ok"}` response.
- [ ] A documented frontend install/start command loads the browser application.
- [ ] The browser reports backend health as connected/healthy.
- [ ] Backend unit tests pass.
- [ ] Frontend unit tests pass.
- [ ] Backend lint and type checks pass.
- [ ] Frontend lint and TypeScript checks pass.
- [ ] The frontend production build succeeds.
- [ ] The architecture-boundary test passes for valid imports and fails against a deliberately invalid test fixture.
- [ ] No cloud service or internet connection is required after dependencies are installed.
- [ ] README documents prerequisites, setup, start, test, build, and architecture-boundary rules.
- [ ] No functionality listed under explicit non-goals is introduced.

### Unit tests

- API health handler returns the typed healthy response.
- Browser health component renders healthy, unavailable, and loading states.
- Architecture-boundary rule accepts domain-only imports.
- Architecture-boundary rule detects an invalid domain-to-infrastructure/application import fixture.

### Integration tests

- Start the FastAPI test application and perform a real HTTP request to `/health`.
- Build the frontend production bundle.
- If practical in the selected frontend test tooling, render the application with a mocked healthy backend response and verify the visible status.

### Documentation updates

Create/update `README.md` with:

- Phase 1 prototype/non-certification statement.
- Supported target: local Windows laptop.
- Required Python and Node versions.
- Backend/frontend installation commands.
- Backend/frontend start commands.
- Test, lint, type-check, and build commands.
- Repository layer responsibilities and prohibited dependency direction.
- Confirmation that Unity, BlueSky, cloud services, and distributed deployment are not required.

### Completion evidence

Attach or paste:

1. Backend test/lint/type-check output.
2. Frontend test/lint/type-check/build output.
3. Example `/health` request and response.
4. Screenshot of the browser displaying healthy backend status.
5. Architecture-boundary test output, including proof that its invalid fixture is detected.
6. List of files created/changed.

### Rollback considerations

- This issue introduces no persistent user data or migrations.
- Keep the foundation changes in one intentionally scoped merge so they can be reverted cleanly.
- If a tool choice must be rolled back, retain the baseline-required stack and documented commands.
- Do not delete unrelated repository files during rollback.

### Definition of done

This issue is complete only when every acceptance checkbox is satisfied, all required evidence is attached, the repository remains runnable, and no later-phase feature has been introduced.

---

**End of Phase 1 Feature Packets**
