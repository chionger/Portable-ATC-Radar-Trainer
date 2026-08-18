# ATC Portable Trainer
## Phase 1 Architecture Baseline v1.0

**Document type:** Authoritative engineering architecture baseline  
**Version:** 1.0  
**Approval authority:** HSA, Product Owner  
**Baseline date:** 2026-08-07  
**Implementation target:** Local Windows laptop  
**Operating mode:** Offline, single trainee, single frequency  
**Status:** Approved architecture baseline subject only to items explicitly classified in Section 28

---

# 1. Document Control

## 1.1 Authority

This document is the authoritative engineering baseline for Phase 1 of the ATC Portable Trainer. Implementations, tests, interface schemas, deployment assets, and subsequent feature packets shall conform to it.

Where implementation documentation conflicts with this baseline, this baseline takes precedence unless superseded through the change-control process in Section 30.

## 1.2 Approval

The product owner has approved the architecture decisions incorporated into this baseline.

**Product owner:** HSA  
**Approval date:** 2026-08-07  
**Approval status:** Approved for baseline consolidation

## 1.3 Versioning

Baseline versions use semantic document versioning:

- **Major:** incompatible architectural change, changed authority boundary, changed Phase 1 objective, or incompatible contract family.
- **Minor:** additive architectural capability or compatible contract expansion.
- **Patch:** clarification that does not change required behaviour or compatibility.

Interface schemas, scenarios, events, snapshots, configuration, scoring rules, and exports are versioned independently and referenced by each session.

## 1.4 Normative language

The terms **shall**, **must**, and **required** are normative. **Should** indicates a preferred implementation that may be varied through a documented implementation choice. **May** indicates an optional capability.

## 1.5 Open-item classifications

Every remaining open item is assigned one of these classifications:

- **Implementation choice:** may be selected by the implementation team within stated constraints without changing this baseline.
- **Benchmark decision:** must be selected using measured evidence on the reference laptop.
- **Deferred decision:** intentionally postponed beyond the current Phase 1 scope or until a named later milestone.
- **Architecture blocker:** must be resolved and recorded in an ADR before implementation of the affected architectural area proceeds.

# 2. Purpose

Phase 1 shall prove that an offline, browser-based ATC training system can execute a complete aerodrome-control training loop on one Windows laptop:

1. A trainee selects and starts a scenario.
2. Aircraft and aerodrome state are displayed in a browser.
3. The trainee issues spoken ATC instructions through push-to-talk.
4. Local speech recognition produces a transcript.
5. The backend converts the transcript into a validated structured command.
6. A virtual pilot creates and transmits a structured response or readback.
7. Aircraft state changes only through accepted commands and applicable acknowledgement rules.
8. Deterministic error injection creates selected training events.
9. Rule-based competency logic records evidence-linked observations.
10. The system produces a debrief and reconstructable event-based replay.

Phase 1 is a training-architecture and workflow prototype. It is not a certified ATC simulator and shall not be represented as suitable for operational traffic control.

# 3. Product Objective

The Phase 1 product objective is:

> A trainee aerodrome controller can complete a short scenario through a browser, communicate with virtual pilots using voice, observe resulting aircraft behaviour, encounter controlled errors and radio events, and receive an evidence-based debrief and replay without internet connectivity.

The reference demonstration shall run for approximately 10–15 minutes and contain at least:

- one departure;
- one arrival;
- one taxiing aircraft;
- one runway-occupancy event;
- one correct readback;
- one deliberately incorrect readback;
- one required controller correction;
- one blocked or competing transmission;
- one competency observation;
- one completed debrief and replay.

# 4. Architectural Principles

## 4.1 Backend authority

The backend is authoritative for simulation time, session state, aircraft state, runway occupancy, scenarios, commands, clearances, radio state, competency observations, scores, events, snapshots, replay, and debrief data.

The browser provides input and presentation only. Browser interpolation may smooth visual motion but shall not create authoritative position, clearance, occupancy, score, or scenario state.

## 4.2 Structured-command safety boundary

Free text, transcripts, and model output shall never directly control an aircraft. Every operational instruction shall become a schema-valid structured command and pass semantic validation against current authoritative state before dispatch.

## 4.3 Replaceable adapters

ASR, LLM, TTS, simulation, persistence, phrase rendering, and scoring explanation providers shall be accessed through domain-owned ports. Vendor-specific types shall not cross these ports.

## 4.4 Events as authoritative history

Material state changes and training actions shall be recorded as ordered, versioned domain events. Query tables are rebuildable projections. Replay shall use stored events and snapshots, not recorded video and not re-executed AI inference.

## 4.5 Rules as assessment authority

Explicit, versioned rules are authoritative for Phase 1 competency observations and scoring. AI may render explanations but shall not create or remove authoritative safety findings or score changes.

## 4.6 Deterministic operational core

Given the same scenario version, seed, structured inputs, and simulation timing, deterministic simulation, radio policy, error injection, rules, and replay reduction shall produce the same canonical semantic outcome.

## 4.7 Offline first

Normal startup, training, debrief, replay, and export shall not require internet access. No runtime component may silently fall back to a cloud service.

Model assets required for approved local AI functions shall be capable of being preserved, verified, backed up, restored, and used without dependence on continued availability of their original upstream distribution service. Model binaries remain external deployment assets and shall not be stored in the application Git repository.

# 5. Scope

## 5.1 In scope

- React/TypeScript browser interface.
- Local FastAPI backend.
- Single trainee and optional instructor controls in the same browser application.
- One aerodrome and one active operational frequency.
- Two-dimensional runway, taxiway, holding-point, aircraft, label, and status display.
- Simplified deterministic ground and airborne movement.
- Versioned YAML scenario definitions.
- Push-to-talk and local speech recognition.
- Transcript normalisation, callsign resolution, structured command extraction, and validation.
- Deterministic command fast path and constrained local LLM assistance.
- Virtual-pilot policy, correct/incorrect readbacks, clarification requests, phrase rendering, and local TTS.
- Taxi, hold, line-up, take-off, continue approach, land, go-around, vacate, correction, and say-again commands required by the reference scenario.
- Deterministic error injection.
- One-frequency radio queue, priority, blocked-transmission and controlled-overlap behaviour.
- Aircraft-state and runway-occupancy updates.
- SQLite event history, projections, snapshots, and exports.
- Rule-based competency observations, scoring, debrief, and event-based replay.
- Component health, structured logging, offline packaging, automated tests, and operating documentation.

## 5.2 Out of scope

- Certification, operational approval, or safety assurance for live ATC.
- Unity, BlueSky, VR-Forces, or any other external simulation engine on the Phase 1 critical path.
- Three-dimensional tower views, VR, MR, or photorealistic visuals.
- Multiple human controllers, multiple active frequencies, or distributed multi-laptop sessions.
- Functional frequency handoff and the `CONTACT_FREQUENCY` command.
- Cloud deployment or required cloud inference.
- High-fidelity aircraft dynamics, surveillance modelling, wake turbulence, advanced weather, or separation assurance.
- Worldwide airport support and general-purpose surface-route optimisation.
- Electronic flight strips or a complete digital-tower suite.
- DIS or HLA integration.
- Foundation-model training, fine-tuning, or reinforcement learning.
- Unrestricted natural-language ATC.
- Production identity management, high concurrency, or cybersecurity accreditation.

# 6. Quality Attributes

## 6.1 Safety of state changes

- No transcript or LLM output shall bypass structured-command validation.
- Unsupported, ambiguous, stale, or low-quality instructions shall not cause aircraft action.
- Disputed safety-critical readbacks shall block the disputed action until valid correction or an explicitly audited instructor intervention.
- Every material state mutation shall produce an authoritative event.

## 6.2 Reliability

- A 15-minute reference scenario shall complete successfully in at least 19 of 20 consecutive runs on the reference laptop, excluding deliberate trainee errors.
- Failure of ASR, LLM, or TTS shall not corrupt authoritative state.
- A TTS failure shall degrade to text.
- A database append failure shall stop or pause state-changing processing rather than permit unrecorded operation.

## 6.3 Performance targets

- Browser state display: target 10 Hz; minimum 5 Hz during the reference scenario.
- Non-model API response: p95 below 250 ms.
- PTT release to transcript: target p95 below 2.5 seconds after warm-up.
- Transcript to command outcome: target p95 below 2 seconds.
- Accepted command to visible state acknowledgement: below 500 ms, excluding intentional radio delays.
- Replay seek within a 15-minute session: target below 1 second.
- TTS generation: target faster than real time after warm-up.

Targets requiring model/hardware validation are benchmark decisions identified in Section 28.

## 6.4 Determinism

Canonical replay comparison shall include ordered semantic event types, scenario entity identities, structured command/readback elements, simulation state, objective/rule results, and deterministic simulation time.

It shall exclude generated event/request IDs, wall-clock time, processing duration, audio file references, diagnostic metadata, and non-authoritative rendered wording.

## 6.5 Maintainability

- Domain and application layers shall not depend on concrete provider libraries.
- Shared contracts shall be versioned and contract-tested.
- Components shall use typed configuration and dependency injection.
- Architectural dependency rules shall be automatically checked.

## 6.6 Privacy

- Raw audio retention is disabled by default.
- Transcript text is retained locally by default for the configured retention period.
- Effective retention policy is recorded with the session.
- Logs shall not contain raw audio and should avoid unnecessary transcript duplication.

## 6.7 Accessibility and usability

Core controls shall support keyboard operation, including configurable PTT. Colour shall not be the sole status indicator. Focus and contrast shall meet WCAG 2.1 AA where practical for the prototype.

### 6.8 Local Model Zoo and Model Asset Preservation

Phase 1 shall maintain an offline-capable local model zoo for candidate AI model assets that may later be evaluated for ASR, LLM, TTS, and other approved local AI roles.

The model zoo is an **asset-preservation and provenance facility**, not an application runtime component.

The Git repository shall contain only the information and tooling required to identify, verify, manage, and restore model assets. This may include:

- model identity and family;
- exact version or revision;
- model category and intended role;
- file format;
- quantisation, where applicable;
- original source and acquisition information;
- licence and usage-rights information;
- cryptographic checksums;
- runtime compatibility information;
- local storage convention;
- verification status; and
- backup and restoration instructions.

Large model binaries and model weights shall **not** be committed to the application Git repository. They shall be stored as external local deployment assets using a documented storage convention suitable for offline and air-gapped operation.

The architecture shall distinguish the following states:

**Available** — the model asset has been acquired and catalogued.

**Verified** — the locally stored asset matches its recorded identity and cryptographic checksum.

**Benchmarked** — the model has been evaluated under the relevant benchmark feature packet.

**Approved for runtime** — the model has satisfied the applicable acceptance criteria and has been explicitly selected for an application role.

These states are not interchangeable. In particular:

**Available ≠ Verified ≠ Benchmarked ≠ Approved for runtime.**

FP-001A establishes only the model-zoo foundation, metadata, storage convention, provenance, integrity verification, and operating procedure.

FP-001A shall not introduce ASR inference, LLM inference, TTS inference, model fine-tuning, automatic model downloading, runtime model selection, or model-specific ATC application dependencies.

Actual model evaluation and runtime integration remain governed by the later feature packets responsible for ASR, LLM, and TTS benchmarking and integration.

Model-zoo verification shall be capable of operating without network connectivity after model assets have been acquired. The application itself shall not require access to an upstream model repository in order to verify locally preserved assets.

# 7. System Context

## 7.1 Actors

### Trainee controller

Selects a scenario, starts/pauses/stops a session, transmits instructions, observes traffic, hears or reads pilot responses, receives clarification, completes objectives, and reviews debrief/replay.

### Instructor or demonstrator

Selects difficulty and seed, enables configured error injection, observes transcripts/commands/findings, adds timeline markers, controls session lifecycle, reviews/export results, and may use a separately audited intervention if enabled.

## 7.2 External dependencies

The deployed Phase 1 system has no required network dependency. Local external resources are:

- microphone and audio output;
- local ASR model/runtime;
- local LLM model/runtime when enabled;
- local TTS model/runtime;
- local filesystem and SQLite database;
- local model-zoo storage containing preserved candidate model assets, manifests, checksums, and licence/provenance records;
- a supported local web browser.

## 7.3 Trust boundary

Browser input, audio, scenario files, configuration, model output, and imported/exported artifacts are untrusted at their entry boundaries and shall be validated before use.

# 8. Approved Technology Stack

| Area | Approved technology |
|---|---|
| Browser | React, TypeScript, Vite |
| Visual display | HTML Canvas or SVG |
| Browser state/transport | Typed client store, HTTP, WebSocket, browser audio APIs |
| Backend | Python, FastAPI, Pydantic, Uvicorn |
| Persistence | SQLite with migrations and WAL mode |
| Scenario/configuration | Versioned YAML validated into typed models |
| Diagnostic/export formats | JSON, JSONL, Markdown, checksummed artifact bundle |
| ASR | Local adapter; faster-whisper or whisper.cpp are approved candidates |
| LLM | Local, replaceable, schema-constrained adapter |
| TTS | Local adapter; Kokoro or Piper are approved candidates |
| Simulation | Phase 1 `SimpleSimulationProvider` behind a neutral port |
| Testing | pytest, FastAPI test tooling, Vitest, browser end-to-end tooling selected by implementation |

The choice between listed candidate implementations is not an architectural change if the approved port and offline constraints remain satisfied.

# 9. Component Architecture

```text
Browser Presentation
  Aerodrome | Radio | PTT | Instructor | Debrief | Replay
                             |
                     REST + WebSocket
                             |
API and Real-Time Gateway
                             |
Application Services
  Session | Utterance/Command | Clearance/Readback
  Instructor Intervention | Debrief/Replay/Export
                             |
Domain and Training Core
  Session/Aircraft/Runway | Commands/Clearances
  Virtual Pilot | Radio Policy | Competency Rules | Events
                             |
Domain-Owned Ports
  Simulation | Event/Snapshot Repository | ASR | LLM | TTS
                             |
Local Infrastructure Adapters
  Simple Simulation | SQLite | Local ASR/LLM/TTS | Filesystem
```

Dependencies shall point inward. Infrastructure implements ports owned by inner layers. Browser and API DTOs shall not become domain models by convenience.

# 10. State Ownership

| State | Authoritative owner | Notes |
|---|---|---|
| Session lifecycle | Session application service with domain transition policy | Persisted as events/projection |
| Simulation time | Simulation clock/core | Separate from wall clock |
| Aircraft state/position | Simulation core/provider under backend control | Browser interpolation is non-authoritative |
| Runway occupancy | Runway occupancy policy within simulation update boundary | Single mutation authority |
| Scenario phase/objectives | Scenario engine | Based on versioned scenario and events |
| Transcript | Utterance workflow/event history | ASR result is input evidence, not command authority |
| Command/validation status | Command processor | Shared validator regardless of extraction source |
| Clearance/readback status | Clearance/readback service | Disputed action gating enforced here |
| Radio queue/audibility | Radio engine | Deterministic ordering and blocking |
| Pilot response elements | Virtual-pilot policy | Rendering/TTS cannot alter elements |
| Competency observations/score | Rule and scoring engine | Rules authoritative; explanations non-authoritative |
| Event sequence | Event persistence/application boundary | Monotonic within session |
| Replay state | Replay service | Read-only derived state; does not mutate source session |
| UI selection/layout | Browser | Non-authoritative presentation state |

# 11. Component Responsibilities

## 11.1 Browser presentation

- Scenario selection and lifecycle controls.
- Aerodrome, runway, taxiway, holding-point, aircraft, label, route, and occupancy rendering.
- PTT capture and upload status.
- Radio history, transcripts, command outcomes, clarifications, health, and alerts.
- Instructor controls, debrief, replay, and export interface.
- WebSocket reconnect using last processed sequence and snapshot resynchronisation.

The browser shall not validate clearances, mutate aircraft/runway state, calculate scores, call models directly, or write SQLite.

## 11.2 API and real-time gateway

- Versioned REST and WebSocket contracts.
- Authentication-mode boundary for trainee/instructor actions in the single-laptop prototype.
- Request schema, file size/type, session, idempotency, and lifecycle validation.
- Audio routing, state/debrief/event queries, and artifact download.
- Sequenced snapshot/delta delivery and health/error messages.
- No domain or simulation business rules.

## 11.3 Session application service

- Create IDs and pin scenario/configuration/model/rule versions.
- Initialise scenario, database, clock, adapters, and seed.
- Enforce lifecycle transitions.
- Coordinate pause/resume/stop/failure/finalisation.
- Trigger debrief and expose replay creation.

## 11.4 Scenario engine

- Load and validate YAML before session readiness.
- Instantiate geometry/entities and schedule deterministic events.
- Track phases, objectives, error injections, success, failure, and time limit.
- Emit scenario and objective events.

## 11.5 Simulation core and provider

- Maintain deterministic simulation time and entity state.
- Apply neutral validated simulation commands.
- Enforce state-transition and occupancy rules.
- Advance movement at configured fixed steps.
- Produce neutral provider effects and canonical snapshots.
- Never allocate authoritative event sequence or persist directly.

## 11.6 Utterance and command processor

- Normalise audio and transcripts.
- Resolve callsigns, aviation numbers, runways, and holding points.
- Apply deterministic extraction fast path.
- Invoke constrained LLM resolver when configured and unresolved.
- Validate every candidate using the same schema and semantic rules.
- Correlate valid corrections with disputed clearances.
- Produce accepted, rejected, clarification-required, or instructor-review outcomes.

## 11.7 Virtual-pilot engine

- Maintain aircraft/pilot context.
- Decide structured accept, question, correct readback, or configured misread outcome.
- Apply deterministic seeded error injection.
- Create immutable response elements and correlation.
- Render approved phraseology and request TTS.
- Permit aircraft action only through clearance/readback policy.

## 11.8 Radio engine

- Maintain one operational frequency.
- Queue transmissions using deterministic priorities.
- Track start/end/duration, audibility, blocking, and overlap.
- Publish structured radio events and history.
- Require a new call event for retry after a blocked attempt.

## 11.9 Competency and scoring engine

- Consume events without mutating operational state.
- Evaluate versioned rules and resolution windows.
- Record severity, category, evidence IDs, score impact, and resolution.
- Produce overall/category scores and structured debrief facts.
- Allow optional AI wording only after authoritative findings exist.

## 11.10 Event, persistence, replay, and export services

- Allocate event IDs and monotonic session sequence.
- Persist authoritative events before external publication.
- Maintain rebuildable projections and versioned snapshots.
- Reconstruct read-only state from snapshots and ordered events.
- Create checksummed offline export bundles.

## 11.11 Model adapters

- Expose typed request/response interfaces and health.
- Enforce local-only inference, timeout, cancellation, and bounded context.
- Record model/version/settings/latency metadata.
- Return failures without directly changing operational state.

# 12. Domain Model

## 12.1 Session

Required fields:

- `session_id`
- `scenario_id` and `scenario_version`
- `lifecycle_state`
- `seed`
- `simulation_time`
- `created_at`, `started_at`, `ended_at`
- effective configuration, rule, schema, and adapter versions
- outcome and failure information

Live lifecycle states:

```text
CREATED -> INITIALISING -> READY -> RUNNING <-> PAUSED
RUNNING|PAUSED -> COMPLETED|STOPPED|FAILED
CREATED|INITIALISING|READY -> FAILED
```

Terminal source sessions remain `COMPLETED`, `STOPPED`, or `FAILED`. Replay is a separate read-only view and not a transition that changes the source session.

## 12.2 Aircraft

Required fields:

- `aircraft_id`, `callsign`, `aircraft_type`, optional wake category;
- position, heading, ground speed, altitude;
- operational state and entity version;
- route and route progress;
- assigned runway and current clearance state;
- pilot profile and active response state.

Canonical Phase 1 operational states:

- `PARKED`
- `READY_TO_TAXI`
- `TAXIING`
- `HOLDING`
- `LINED_UP`
- `TAKEOFF_ROLL`
- `AIRBORNE`
- `INBOUND`
- `FINAL`
- `LANDING_ROLL`
- `VACATING`
- `STOPPED`

State transitions shall be explicit, versioned, and command/scenario driven. `HOLDING` carries a holding-point identifier; display wording may say “holding short.” `INBOUND` precedes `FINAL` and is not interchangeable with it.

## 12.3 Runway and aerodrome geometry

Runway includes identifier/designator, threshold/end geometry, width, operational status, occupancy state, and occupying entities. Taxiways and holding points use scenario-defined geometry and stable identifiers.

Runway occupancy membership has one authoritative mutation policy and changes atomically with the associated simulation effect/event batch.

## 12.4 Command

A command represents a controller instruction candidate and its outcome. It records source transcript, target, type, parameters, confidence/quality, correlation, issued simulation time, validation result, and internal correction linkage where applicable.

## 12.5 Clearance and readback

Clearance includes:

- `clearance_id`, source command, target, type, parameters;
- required readback elements;
- issued time and action gate;
- actual structured response;
- readback/correction/override status;
- referenced evidence events.

## 12.6 Radio transmission

Includes speaker kind/identity, structured response type, text/audio artifact, queue/start/end simulation times, priority, audibility, overlap/blocking information, retry relationship, and command/clearance correlation.

## 12.7 Competency observation

Includes observation ID, rule/version, category, severity, simulation time, evidence event IDs, score delta, resolution, and optional instructor note.

## 12.8 Scenario

Contains versioned metadata, aerodrome geometry, environment, entities, schedules, objectives, deterministic error injections, success/failure conditions, default seed, and presentation metadata.

# 13. Structured Command Model

## 13.1 Supported command types

- `TAXI_TO_HOLDING_POINT`
- `HOLD_POSITION`
- `LINE_UP_AND_WAIT`
- `CLEARED_FOR_TAKEOFF`
- `CLEARED_TO_LAND`
- `CONTINUE_APPROACH`
- `GO_AROUND`
- `VACATE_RUNWAY`
- `CORRECT_READBACK`
- `SAY_AGAIN`

`CONTACT_FREQUENCY` is not supported in Phase 1.

## 13.2 Command schema

```json
{
  "command_id": "cmd-000124",
  "session_id": "session-001",
  "issued_at_sim_time": 142.7,
  "speaker": "CONTROLLER",
  "target_callsign": "SIA217",
  "command_type": "LINE_UP_AND_WAIT",
  "parameters": {"runway": "20C"},
  "source_transcript_id": "tr-00051",
  "source_text": "Singapore two one seven line up and wait runway two zero centre",
  "extraction_method": "DETERMINISTIC_FAST_PATH",
  "confidence": 0.94,
  "corrects_clearance_id": null,
  "status": "ACCEPTED",
  "schema_version": "1.0"
}
```

## 13.3 Validation outcomes

- `ACCEPTED`
- `REJECTED`
- `CLARIFICATION_REQUIRED`
- `INSTRUCTOR_REVIEW`

Validation includes schema, supported command, callsign resolution, parameter existence, confidence/quality, current entity version/state, runway/holding point, command prerequisites, runway conflict rules, and correction correlation.

## 13.4 Extraction routing

1. Deterministic transcript normalisation and callsign resolution always run.
2. A deterministic fast path handles unambiguous supported forms.
3. A constrained local LLM resolver may process unresolved utterances.
4. All candidates pass the same schema and semantic validator.
5. Invalid LLM output is never repaired by execution-time guessing; deterministic fallback or clarification is used.

## 13.5 Corrections

The trainee does not reference internal IDs. The backend correlates a correction using target callsign, active disputed clearance, disputed elements, and configured time window. The correction must clearly contain the disputed safety-critical elements. Ambiguous correlation produces clarification.

## 13.6 SAY AGAIN

`SAY_AGAIN` is controller-to-pilot, radio-directed, and requires `target_callsign`. Replaying a transcript in the UI is not this command and creates no operational command event.

# 14. Simulation Provider Contract

## 14.1 Neutral command

```text
SimulationCommand
  command_id
  aircraft_id
  action
  parameters
  expected_entity_version
  issued_at_sim_time
```

Neutral actions are taxi, hold, line-up, take-off, continue approach, land, go-around, and vacate.

## 14.2 Result

```text
ApplyResult
  accepted
  rejection_code
  effects[]
  resulting_entity_version

ProviderEffect
  effect_type
  entity_id
  structured_payload
```

The provider shall not create authoritative event IDs, session sequences, competency events, radio events, or persistence records. Application/domain services translate accepted effects into authoritative domain events.

## 14.3 Determinism

The simple provider shall produce the same canonical effects for the same scenario state, entity versions, command, step sequence, and seed.

# 15. Event Model

## 15.1 Event envelope

Every authoritative event contains:

- `event_id`
- `event_type`
- `schema_version`
- `session_id`
- monotonically increasing `sequence`
- `sim_time`
- `wall_time_utc`
- `actor` and `source`
- `correlation_id`
- optional `causation_id`
- typed payload

Events are immutable after durable append.

## 15.2 Minimum event catalogue

| Category | Required events |
|---|---|
| Session | `session.created`, `session.initialising`, `session.ready`, `session.started`, `session.paused`, `session.resumed`, `session.completed`, `session.stopped`, `session.failed` |
| Scenario | `scenario.loaded`, `scenario.phase_changed`, `scenario.objective_updated`, `scenario.event_triggered` |
| PTT/ASR | `controller.ptt_started`, `controller.ptt_stopped`, `audio.received`, `transcript.created`, `transcript.failed` |
| Command | `command.extracted`, `command.accepted`, `command.rejected`, `command.clarification_required`, `command.dispatched` |
| Clearance | `clearance.issued`, `clearance.readback_received`, `clearance.readback_incorrect`, `clearance.corrected`, `clearance.acknowledged` |
| Instructor | `instructor.marker_added`, `instructor.override_applied` when override is enabled |
| Radio | `radio.transmission_queued`, `radio.transmission_started`, `radio.transmission_finished`, `radio.transmission_blocked` |
| Simulation | `aircraft.spawned`, `aircraft.state_changed`, `aircraft.route_assigned`, `runway.occupancy_changed`, `simulation.snapshot_created`, `simulation.timing_anomaly` |
| Training | `competency.observation_detected`, `competency.observation_resolved`, `score.updated`, `debrief.generated` |
| System | `component.health_changed`, `adapter.timeout`, `adapter.failed` |

Routine fixed clock ticks shall not be persisted as events. Timing anomalies and material state effects shall be recorded.

## 15.3 Schema evolution

- Unknown major versions shall be rejected by consumers that cannot migrate them.
- Additive optional fields may be introduced within a compatible major version.
- Event payload schemas shall be stored centrally and contract-tested.
- Migrations shall never rewrite historical semantic meaning without retaining the original record.

## 15.4 Canonical projection

Each event schema shall define fields used for deterministic semantic comparison. Canonical projections are versioned separately from raw event payloads and shall be usable by replay/determinism tests.

# 16. Data Flows

## 16.1 Controller utterance to aircraft action

```text
PTT audio
  -> validated audio upload
  -> local ASR transcript
  -> deterministic normalization/callsign resolution
  -> deterministic fast path or constrained LLM candidate
  -> shared schema and semantic validation
  -> structured command outcome
  -> clearance creation
  -> virtual-pilot structured response/error injection
  -> radio queue and TTS/text fallback
  -> readback/correction gate
  -> neutral simulation command
  -> provider effects
  -> authoritative events and projections
  -> WebSocket state/radio/training updates
```

## 16.2 Incorrect readback and correction

1. Virtual-pilot policy injects a seeded readback error.
2. Structured readback and `clearance.readback_incorrect` are persisted.
3. The disputed action gate remains closed.
4. Competency rule opens a correction window.
5. The controller issues a correction containing the disputed elements.
6. Backend correlates it with the active disputed clearance.
7. `clearance.corrected` is persisted and the observation is resolved where rules permit.
8. Pilot provides correct readback or acknowledgement under configured policy.
9. Action gate opens and dispatch proceeds.

## 16.3 Radio blocking

1. Calls enter the priority queue with simulation time and deterministic tie-break metadata.
2. An in-progress transmission completes; Phase 1 has no barge-in.
3. A selected call starts.
4. Scenario-configured overlap may modify audibility.
5. Losing attempts end as `BLOCKED` with blocking reference/reason.
6. A retry, if required, is a new scheduled/pilot-policy call.

## 16.4 Event publication

Material domain/simulation results are assigned identity and sequence, durably appended, projected consistently, and only then published to clients. The exact atomicity mechanism is an architecture blocker in Section 28.

## 16.5 Replay

Replay opens the latest compatible snapshot at or before the target time, applies subsequent ordered events using versioned reducers, and publishes read-only replay state. It never invokes ASR, LLM, TTS, live radio arbitration, or live scenario scheduling.

# 17. REST Boundary

All Phase 1 endpoints are versioned under `/api/v1`. State-changing requests shall support idempotency where retry could duplicate an effect.

| Method | Endpoint | Responsibility |
|---|---|---|
| GET | `/health` | Overall/component readiness; no session mutation |
| GET | `/api/v1/scenarios` | List validated scenario metadata |
| GET | `/api/v1/scenarios/{id}` | Scenario metadata/version |
| POST | `/api/v1/sessions` | Create and initialise session |
| GET | `/api/v1/sessions/{id}` | Current session summary |
| POST | `/api/v1/sessions/{id}/start` | Start ready session |
| POST | `/api/v1/sessions/{id}/pause` | Pause running session |
| POST | `/api/v1/sessions/{id}/resume` | Resume paused session |
| POST | `/api/v1/sessions/{id}/stop` | Stop and finalise |
| POST | `/api/v1/sessions/{id}/audio` | Submit one PTT utterance |
| POST | `/api/v1/sessions/{id}/text-command` | Explicit instructor-enabled fallback input |
| GET | `/api/v1/sessions/{id}/state` | Authoritative current snapshot |
| GET | `/api/v1/sessions/{id}/events` | Paginated event query |
| POST | `/api/v1/sessions/{id}/markers` | Add instructor timeline marker |
| POST | `/api/v1/sessions/{id}/instructor-overrides` | Audited override, if enabled |
| GET | `/api/v1/sessions/{id}/debrief` | Structured debrief and score |
| GET | `/api/v1/sessions/{id}/export` | Checksummed export bundle |
| POST | `/api/v1/replays` | Create read-only replay view from source session |
| POST | `/api/v1/replays/{id}/seek` | Seek replay simulation time |

Stable error responses include code, message, structured details, and correlation ID. Invalid lifecycle transitions return conflict and produce no state mutation.

# 18. WebSocket Boundary

Endpoint:

```text
/api/v1/sessions/{session_id}/stream
```

Server envelope:

```json
{
  "message_type": "aircraft_delta",
  "schema_version": "1.0",
  "session_id": "session-001",
  "sequence": 145,
  "sim_time": 142.7,
  "payload": {}
}
```

Server messages include:

- `session_state`
- `simulation_snapshot`
- `aircraft_delta`
- `runway_delta`
- `radio_event`
- `transcript_result`
- `command_result`
- `competency_observation`
- `score_update`
- `component_health`
- `replay_state`
- `error`

Multiple browser clients may observe one session. On connection, the server sends current session state and an authoritative snapshot. The client reports the last processed sequence when reconnecting. The server fills an available gap or sends a new snapshot. Session mutations use REST; WebSocket is primarily server-to-client state/event delivery and replay control where explicitly defined.

# 19. Persistence

## 19.1 Authority

SQLite is the Phase 1 durable store. The `events` table is the authoritative history. Commands, transmissions, competency observations, scores, and session summaries are rebuildable projections.

## 19.2 Minimum tables

- `sessions`
- `events`
- `snapshots`
- `transcripts`
- `commands` projection
- `radio_transmissions` projection
- `competency_observations` projection
- `debriefs`
- `artifacts`
- migration/projection metadata

## 19.3 Database rules

- Foreign keys and WAL mode enabled.
- Unique `(session_id, sequence)`.
- Indexes for session/sequence, session/simulation time, event type, and session creation time.
- Schema changes use migrations.
- Projection rows record source sequence and projection version.
- Event append failure prevents dependent state publication/action continuation.
- Raw audio storage follows per-session retention configuration.

## 19.4 Snapshots

Snapshots are versioned canonical state documents created periodically and at key lifecycle transitions. They optimise seeking but do not replace event history. Snapshot payloads are independent of browser DTOs.

# 20. Replay and Debrief

## 20.1 Replay

- Replay is a separate read-only view of a source session.
- Completed, stopped, and failed sessions may be replayed when event-history integrity is sufficient.
- Controls include play, pause, seek, 0.5x/1x/2x/4x speed, event step, and jump to competency observation or instructor marker.
- Replay is visually distinguishable from live operation.
- Replay does not modify or reclassify the source session.

## 20.2 Debrief

Debrief includes:

- session/scenario/configuration metadata;
- outcome and overall/category scores;
- achieved/missed objectives;
- chronological evidence-linked competency observations;
- relevant transcript, command, clearance, readback, correction, override, and radio evidence;
- positive actions and improvement points;
- replay links/timestamps;
- non-certification disclaimer.

## 20.3 Export

The offline export bundle contains a manifest with checksums, session summary, ordered JSONL events, structured and Markdown debrief, scenario/configuration/rule/schema versions, and optional retained audio artifacts.

# 21. Competency and Scoring

Required Phase 1 rule coverage:

- incorrect readback detected;
- valid correction within configured window;
- uncorrected incorrect readback;
- take-off clearance while runway blocked/occupied under configured rules;
- landing clearance with configured runway conflict;
- missing required runway or holding-point element;
- unknown or ambiguous callsign;
- avoidable controller response delay above threshold;
- blocked/overlapping transmission occurrence/handling;
- scenario objective completion.

Default scoring begins at 100, applies versioned per-occurrence deductions, clamps to 0–100, and reports safety, communication, traffic-management, and procedural-compliance categories.

Instructor override never erases the underlying readback or competency evidence. AI-generated narrative may explain an observation but cannot change rule result or score.

# 22. Failure Handling

| Failure | Required behaviour |
|---|---|
| Invalid scenario/configuration | Block session readiness and identify exact validation error |
| Model missing/warm-up failure | Transition initialising session to failed; expose health detail |
| Microphone denied | Show remediation; permit explicit text fallback when enabled |
| Invalid/empty/oversized audio | Record recoverable outcome; no command/action |
| ASR timeout/failure | Emit adapter/transcript failure; retry or text fallback; no action |
| Ambiguous/low-quality command | Clarification required; no action |
| Invalid LLM output | Reject candidate, deterministic fallback or clarification; never execute raw output |
| TTS failure | Show pilot text and continue radio/state workflow |
| WebSocket loss | Mark client state stale, reconnect with backoff, resynchronise sequence/snapshot |
| SQLite append failure | Stop/pause state-changing processing and raise fatal persistence alert |
| Simulation tick overrun | Record metric/anomaly; preserve deterministic simulation-time policy |
| Browser refresh | Reconnect to active session after explicit confirmation |
| Corrupt replay history | Refuse unsafe reconstruction; provide diagnostic/export of valid prefix where permitted |

Component failure must not silently change training rules, validation thresholds, or adapter provider.

# 23. Security and Privacy

- Bind backend services to loopback by default.
- Validate all HTTP/WebSocket input and YAML/JSON schemas.
- Enforce upload type/size/duration limits.
- Resolve artifact paths under configured session storage; prevent traversal.
- Escape transcript/model/user text before browser rendering.
- Never execute model output, generated code, shell text, or arbitrary scenario expressions.
- Keep secrets out of source, logs, scenarios, and exports.
- Record instructor interventions with reason and source.
- Raw audio retention is explicit opt-in; transcript retention duration is configurable.
- Exports remain local and checksummed.
- Production authentication/accreditation is outside Phase 1; instructor-only operations still require explicit application mode and visible attribution.

# 24. Offline Deployment

## 24.1 Target

Windows 11 laptop with supported browser, microphone, audio output, sufficient local storage, and model-compatible CPU/GPU resources.

## 24.2 Bundle

The offline bundle shall contain:

- application and required runtimes;
- frontend assets;
- database migrations;
- reference scenario and configuration;
- permitted local model files or documented offline installation package;
- startup, verification, and shutdown scripts;
- licences, third-party notices, checksums, and operating documentation.

## 24.3 Startup

One documented action shall:

1. verify writable storage and available ports;
2. apply/verify migrations;
3. validate scenarios/configuration;
4. verify and warm required model adapters;
5. start backend/frontend services;
6. open the browser after readiness;
7. show component health before session creation.

No automatic external download shall occur during normal startup or training.

## 24.4 Shutdown and recovery

Controlled shutdown finalises or fails the active session, flushes durable events, closes adapters, and stops child processes. Restart exposes prior sessions for debrief/replay according to integrity state.

# 25. Testing Strategy

## 25.1 Unit tests

Cover lifecycle/state transitions, command schema/validation, correction correlation, clearance gates, occupancy, deterministic movement, radio ordering/blocking, error injection, competency rules, scoring, scenario predicates, event projection, and replay reducers.

## 25.2 Architecture tests

Verify inward dependencies, no domain import of apps/concrete adapters, no browser-owned simulation rules, and provider/event identity separation.

## 25.3 Contract tests

Cover REST/OpenAPI, WebSocket envelopes/reconnect, event/snapshot schemas, YAML scenarios, simulation port, ASR/LLM/TTS ports, exports, and compatibility/migration behaviour.

## 25.4 Integration tests

Cover lifecycle plus SQLite, fixture audio/transcript to command, incorrect readback/correction, simulation effects/events/projections, radio blocking, component failure, WebSocket snapshot/delta, debrief, replay, and export verification.

## 25.5 Determinism tests

Run canonical scenarios twice with the same seed and structured/timed inputs. Compare the canonical semantic event projection and final snapshot. Separately reconstruct from persisted snapshots/events and compare the replay state with the recorded authoritative state.

## 25.6 End-to-end tests

Automate scenario selection, start, scripted controller inputs, pilot responses, traffic updates, error/correction, competency observation, completion, debrief, replay, and export. Perform supervised microphone/model tests on the reference laptop.

## 25.7 Failure and privacy tests

Inject ASR timeout, invalid LLM schema, TTS failure, database append failure, WebSocket interruption, corrupt scenario, corrupt replay suffix, browser refresh, and audio-retention configurations.

# 26. Release Acceptance Test

Phase 1 v1.0 shall not be released unless the following single end-to-end acceptance campaign passes:

1. Disconnect the reference laptop from all networks.
2. Start the packaged application through the documented action.
3. Verify scenario, database, ASR, optional LLM, TTS, simulation, and browser health.
4. Start the versioned reference scenario with a recorded seed.
5. Confirm backend-owned display of SIA217, MAS602, QTR833, Runway 20C, taxiway, and holding point A1.
6. Issue required taxi, hold/line-up, landing, take-off, and vacate instructions by voice.
7. Verify every utterance creates traceable transcript and structured command outcome.
8. Verify ambiguous/unsupported input causes no aircraft action.
9. Trigger the deterministic incorrect runway readback.
10. Confirm the disputed action remains blocked.
11. Issue a valid spoken correction and confirm correlation/resolution.
12. Confirm correct pilot response and resulting aircraft state change.
13. Trigger the configured competing/blocked radio call and verify evidence.
14. Complete arrival, runway vacating, and departure objectives.
15. Verify required competency observations and evidence-linked score/debrief.
16. Stop or complete the session cleanly.
17. Replay from before the incorrect readback, seek to the correction, and verify reconstructed final state.
18. Export the session and validate all manifest checksums offline.
19. Demonstrate TTS text fallback and one ASR/LLM safe-failure path with no unintended action.
20. Repeat the reference scenario campaign until the 19-of-20 reliability criterion is met.

Acceptance evidence shall record hardware, OS, model versions, configuration hashes, scenario/rule/schema versions, seeds, latency results, test logs, defects, and approval.

# 27. Milestones

## Milestone 1 — Architecture foundation

Deliver repository boundaries, typed configuration, domain/event schemas, lifecycle, SQLite foundation, health, logging, migrations, and architecture/contract test framework.

**Gate:** authoritative events can be durably appended and queried; dependency rules pass.

## Milestone 2 — Scenario and deterministic simulation

Deliver scenario validation, geometry, aircraft states/routes, clock, occupancy, neutral simulation port, simple provider, canonical snapshots, and backend-to-browser display.

**Gate:** scripted reference traffic runs deterministically and reconstructs from events/snapshots.

## Milestone 3 — Structured command, clearance, pilot, and radio core

Deliver text/fixture command path, validation, correction correlation, clearances, virtual-pilot structured responses, error injection, radio queue/blocking, and text pilot output.

**Gate:** complete reference training logic works without live models.

## Milestone 4 — Local speech and language adapters

Deliver PTT, ASR, deterministic extraction fast path, constrained LLM resolver, phrase renderer, TTS, thresholds, health, timeouts, and fallbacks.

**Gate:** offline voice loop meets benchmarked latency/accuracy on the reference laptop.

## Milestone 5 — Competency and debrief

Deliver versioned rules, observations, score, objective tracking, evidence links, instructor markers/intervention decision, and structured/rendered debrief.

**Gate:** reference error/correction produces correct evidence and score.

## Milestone 6 — Replay and export

Deliver replay views, seek/speed/markers, failed-history integrity handling, canonical determinism tests, and checksummed exports.

**Gate:** replay reproduces recorded authoritative final state and export verifies offline.

## Milestone 7 — Packaging and hardening

Deliver one-action startup/shutdown, model warm-up, privacy controls, accessibility pass, documentation, performance tuning, failure recovery, and 20-run campaign.

**Gate:** all release acceptance tests pass on the reference laptop.

Milestones describe outcomes and gates. They are not feature packets or GitHub issues.

# 28. Classified Remaining Decisions

## 28.1 Implementation choices

| ID | Choice | Constraint |
|---|---|---|
| IC-01 | Canvas versus SVG for aerodrome display | Must meet update, accessibility, and browser performance requirements |
| IC-02 | Browser state-management and E2E-test libraries | Must preserve typed contracts and backend authority |
| IC-03 | Internal repository/module layout | Must enforce dependency rules and stable contract ownership |
| IC-04 | Snapshot compression and JSON serialization libraries | Must preserve schema/version and offline readability/migration |
| IC-05 | Pydantic/ORM/repository implementation details | Events remain authoritative and SQLite rules remain satisfied |
| IC-06 | Exact phrase templates and radio audio filter | Structured response elements remain authoritative |
| IC-07 | Callsign/number normalisation algorithms | Must be deterministic and contract-tested |
| IC-08 | Instructor identity representation on one laptop | Must visibly attribute and audit interventions |

## 28.2 Benchmark decisions

| ID | Decision | Required evidence |
|---|---|---|
| BD-01 | ASR runtime/model and quality threshold calibration | Reference utterance corpus, callsign/number accuracy, latency, memory |
| BD-02 | Local LLM model, quantisation, routing threshold, and timeout | Structured-command accuracy, invalid-output rate, latency, memory |
| BD-03 | TTS provider/voice configuration | Generation speed, intelligibility, resource use, offline licence |
| BD-04 | Simulation tick and browser publication rates | Smoothness, CPU load, determinism, event/delta volume |
| BD-05 | Snapshot interval/retention | Seek latency, database size, snapshot creation overhead |
| BD-06 | Correction time window | Representative scenario tempo and competency validity |
| BD-07 | Transcript retention duration default | Training evidence need, privacy expectation, storage footprint |

Benchmark decisions shall be recorded in configuration and an ADR amendment or benchmark report before the affected milestone gate.

## 28.3 Deferred decisions

| ID | Deferred capability | Earliest reconsideration |
|---|---|---|
| DD-01 | Functional frequency handoff and `CONTACT_FREQUENCY` | Multi-frequency phase |
| DD-02 | Unity/3D/VR/MR presentation | Post-Phase 1 visualisation phase |
| DD-03 | BlueSky, VR-Forces, or other provider integration | After neutral provider contract is proven |
| DD-04 | Multi-controller/distributed sessions | Post-Phase 1 concurrency/federation phase |
| DD-05 | Cloud deployment/inference | Only through a future privacy/deployment baseline |
| DD-06 | DIS/HLA | Commercial/federated integration phase |
| DD-07 | High-fidelity dynamics/weather/wake/surveillance | Future fidelity requirements |
| DD-08 | Production identity, cybersecurity accreditation, certification | Productisation phase |

## 28.4 Architecture blockers

| ID | Blocker | Required resolution | Blocks |
|---|---|---|---|
| AB-01 | Atomic consistency between in-memory/domain state, SQLite event append, projections, and client publication | ADR-008 shall select and specify transaction/unit-of-work/outbox or equivalent recovery model, including append failure | Milestone 1 event/state integration and all later state-changing workflows |
| AB-02 | Radio partial-overlap audibility semantics | ADR-010 shall define whether Phase 1 supports fully blocked only or deterministic partial audibility, including transcript/audio/debrief representation | Milestone 3 radio contract and acceptance scenario |
| AB-03 | Instructor override inclusion | Product owner shall decide whether the override endpoint/UI is required in Phase 1 or disabled/deferred; if included, approve audit/action-gate rules | Milestone 5 instructor workflow and final REST contract |
| AB-04 | Failed-history replay integrity threshold | ADR-008 shall define the minimum valid event/snapshot conditions and behaviour for invalid suffixes | Milestone 6 failed-session replay |

No implementation team may silently choose an architecture-blocker outcome. The responsible ADR must be approved first. Work outside the blocked area may continue.

# 29. Architectural Constraints

1. Phase 1 shall remain browser based.
2. Normal operation shall remain local and offline.
3. The backend shall own authoritative operational and training state.
4. The browser shall not implement authoritative simulation, clearance, scoring, or replay rules.
5. Free text and model output shall not directly control aircraft.
6. Structured commands shall be schema- and state-validated before action.
7. Virtual-pilot content affecting action shall be structured before phrase rendering/TTS.
8. Error injection shall be scenario-configured and deterministic under the session seed.
9. Competency observations and scores shall be rule-authoritative and evidence linked.
10. Material state changes shall be event recorded before publication.
11. Replay shall use stored events/snapshots and shall not rerun live AI components.
12. ASR, LLM, TTS, and simulation implementations shall remain replaceable behind domain-owned ports.
13. The Phase 1 simulation provider shall be the local simple provider.
14. Unity and BlueSky shall not be Phase 1 dependencies or acceptance requirements.
15. Vendor DTOs and browser transport models shall not become domain contracts.
16. Historical event meaning shall remain versioned and auditable.
17. Database failure shall not permit silent unrecorded operation.
18. Instructor override, if enabled, shall never appear as an ordinary correct readback or erase competency evidence.
19. No deferred capability may enter Phase 1 without approved change control.

# 30. Change-Control Process

## 30.1 Change classes

- **Implementation change:** stays within approved ports, schemas, constraints, and quality gates; record in normal implementation documentation.
- **Compatible baseline clarification:** no behaviour/compatibility change; issue a v1.0.x patch after architecture review.
- **Compatible architectural addition:** additive capability or optional schema field; issue a v1.x minor baseline and ADR.
- **Breaking architectural change:** authority, scope, safety boundary, lifecycle, persistence semantics, incompatible schema, or critical-path technology change; issue a new major baseline and superseding ADR.

## 30.2 Required change record

Every architectural change proposal shall state:

- problem and driver;
- affected requirement, component, schema, event, API, ADR, test, and milestone;
- compatibility/migration impact;
- offline, performance, privacy, reliability, and replay impact;
- alternatives considered;
- product-owner and architecture approval;
- effective baseline/schema versions.

## 30.3 Decision authority

- Implementation choices may be approved by the technical lead within this baseline.
- Benchmark decisions require recorded measurement and technical approval.
- Deferred decisions require a formal scope change before implementation.
- Architecture blockers require an approved ADR and product-owner acknowledgement where product scope is affected.
- Feature packets created later shall cite the applicable baseline and ADR versions.

## 30.4 Traceability

The project shall maintain traceability from non-negotiable requirements to architecture sections, ADRs, schemas, tests, and later feature packets. A change is incomplete until traceability and affected acceptance tests are updated.

# 31. ADR Index

| ADR | Title | Baseline status |
|---|---|---|
| ADR-001 | Backend-authoritative architecture | Approved |
| ADR-002 | Browser-first Phase 1; Unity and BlueSky deferred | Approved |
| ADR-003 | Layering, dependency direction, and domain-owned ports | Approved |
| ADR-004 | Structured command, correction, and readback safety boundary | Approved; correction window is BD-06 |
| ADR-005 | Session lifecycle and separate replay views | Approved |
| ADR-006 | Neutral simulation provider and provider-effect ownership | Approved |
| ADR-007 | Event authority, sequencing, schema evolution, and canonical determinism | Approved |
| ADR-008 | SQLite consistency, projections, snapshots, and replay integrity | **Open: AB-01 and AB-04** |
| ADR-009 | REST/WebSocket boundaries and reconnection | Approved; override surface depends on AB-03 |
| ADR-010 | One-frequency radio arbitration and audibility | **Open: AB-02** |
| ADR-011 | Offline ASR/LLM/TTS adapters, routing, thresholds, and fallback | Approved; provider selections are benchmark decisions |
| ADR-012 | Rule-authoritative competency, scoring, and AI explanation limits | Approved |
| ADR-013 | Typed configuration and effective-session version capture | Approved |
| ADR-014 | Audio/transcript privacy, retention, and exports | Approved; duration is BD-07 |
| ADR-015 | Versioned YAML scenarios and deterministic error injection | Approved |

# 32. Baseline Completion and Use

This baseline is authoritative for all unblocked Phase 1 architecture and implementation work. Architecture blockers in Section 28 shall be resolved through the indexed ADRs before their affected milestones proceed. Implementation and benchmark choices shall remain within the stated constraints and be recorded with the resulting system version.

Feature packets are intentionally outside this document. They may be produced only after the relevant baseline sections, interface drafts, and blocking ADRs are approved and shall not redefine architecture locally.

---

**End of ATC Portable Trainer Phase 1 Architecture Baseline v1.0**
