# FP-011: Neutral simulation port and deterministic fake

## Ownership and scope

`SimulationPort.apply(command, state) -> ApplyResult` is the version-one command port.
The caller supplies an immutable authoritative `TrafficState` snapshot. The provider
calculates neutral effects without mutating the snapshot or retaining speculative state.
The application validates those effects against the original command and domain policy,
creates authoritative events, and commits them with projections and outbox intent.

FP-011 has no motion, stepping, external engine, AI, radio, REST or WebSocket changes.
The fake makes immediate phase transitions so the boundary can be tested before FP-012
implements movement. Its results are contract fixtures, not aircraft dynamics or clearance
authorization. Coordinates, speed, altitude and heading remain unchanged.

There is no production provider default or automatic fake fallback. `SimulationService`
requires an explicitly supplied provider; tests inject `DeterministicFake`. Production
composition and a simple moving provider remain later work. No setting or table is added.

## Version-one data contract

All models are frozen, strict and reject unknown fields. JSON schemas are published in
`tests/fixtures/simulation`. Python collection inputs use tuples; JSON inputs use arrays.

| Type | Fields |
| --- | --- |
| SimulationCommand | schema_version 1.0, command_id, aircraft_id, action, parameters, expected_entity_version, issued_at_sim_time |
| SimulationParameters | optional route, holding_point_id, runway_id |
| ProviderEffect | effect_type, entity_id, structured_payload |
| StateEffect | target, expected_entity_version, optional expected_runway_version, holding_point_id, runway_id |
| RouteEffect | non-empty route, expected_entity_version |
| ApplyResult | schema_version 1.0, accepted, rejection_code, effects, resulting_entity_version |

Versions are positive integers; booleans are rejected. Simulation time is finite and
nonnegative. IDs use the scenario identifier syntax. Routes contain at most 256 geometry
IDs. HOLD requires a holding-point ID; other actions forbid it. Only TAXI may supply a
route. Empty route means retain the current route. Runway omission retains the assignment.

| Action | Fake target phase |
| --- | --- |
| TAXI | TAXIING |
| HOLD | HOLDING |
| LINE_UP | LINED_UP |
| TAKE_OFF | TAKEOFF_ROLL |
| CONTINUE_APPROACH | FINAL |
| LAND | LANDING_ROLL |
| GO_AROUND | AIRBORNE |
| VACATE | VACATING |

All actions obey the [FP-010 state matrix](traffic-state.md). For example, TAXI from PARKED
rejects: the aircraft must first be READY_TO_TAXI. The fake does not invent intervening
phases. VACATE does not immediately clear the runway; later transition to TAXIING does.

Accepted results have no rejection code, contain one STATE_CHANGED effect, and report the
resulting aircraft version. A changed TAXI route adds one preceding ROUTE_ASSIGNED effect:
the route and state changes each advance the aircraft version once. Repeating the existing
route omits the route effect. Route assignment resets progress, preserves other fields,
and is permitted only in READY_TO_TAXI, TAXIING or HOLDING outside runway occupancy.

The domain remains the sole occupancy authority. State effects carry an expected runway
version when relevant; the application derives and validates any paired occupancy event.
Providers cannot directly overwrite runway membership or supply authoritative envelopes.

Rejected results have a rejection code, no effects, and retain the observed aircraft
version, or null for an unknown entity. Fake rejection precedence is unknown entity,
version conflict, illegal phase, closed-runway entry, then invalid parameters/references.

| Rejection | Meaning |
| --- | --- |
| UNKNOWN_ENTITY | Aircraft absent from supplied snapshot |
| VERSION_CONFLICT | Expected aircraft version differs |
| ILLEGAL_STATE | Action's target is not a legal next state |
| RUNWAY_CLOSED | Attempt to enter a closed runway |
| INVALID_PARAMETERS | Invalid geometry, route, holding point or runway assignment |

Malformed/unknown-version contracts fail validation rather than returning operational
rejection codes. Application-level history, session-version, phase and simulation-time
conflicts remain separate from provider rejections.

## Application translation and durability

`translate_effects` reparses provider results, including values constructed with validation
bypasses. It checks effect order/count, target entity, exact command intent, route, each
entity version, resulting version and all domain transition/occupancy rules. An invalid
provider result never becomes an event. Accepted facts map to `aircraft.route_assigned`,
`aircraft.state_changed` and, when membership changes, `runway.occupancy_changed`.

`SimulationService.apply` reads a snapshot, calls the provider and translates effects
outside the transaction. Its pure commit builder checks the observed history sequence and
RUNNING phase under the existing unit of work. The request also checks session version;
command time must equal committed simulation time. Route/state/occupancy facts, session
projection, idempotency record and outbox intent commit atomically. Session lifecycle
version and simulation time remain unchanged. The application allocates event IDs, time
and sequence; the command ID is retained as causation and transport correlation is shared.

The optional `on_committed` notification hook runs only after commit returns. A separate
database connection can observe the events and outbox before the hook runs. A hook failure
does not undo committed data. The outbox remains available for retry by the delivery layer.
The hook is at-least-once: same-key retries may notify again, so consumers deduplicate by
event ID. It is not a replacement for the ordered outbox dispatcher.

Successful command retries return the original committed result, even after provider
failure or later state changes. Provider failures are captured before the transaction and
raised only if a new request needs its builder; existing durable retry results take
precedence. Reusing a key with different command input conflicts. New rejected commands
persist and publish nothing. This packet does not activate command rejection/radio events.

## Adapter-author guide

1. Implement the structural `SimulationPort` protocol; do not subclass the fake.
2. Accept only validated v1 commands and snapshots, and return typed `ApplyResult` values.
3. Keep `apply` a side-effect-free calculation. It may be retried or its result discarded
   after a concurrent commit. Do not allocate IDs/sequences, read clocks, call APIs or
   databases, publish, or mutate external/provider state.
4. Use domain policy to reject illegal phases and stale versions. Preserve rejected state.
   Never guess missing references, clear another aircraft's occupancy, or repair bad input.
5. Provide repeatable canonical effects for identical inputs. Future seeded movement and
   stepping require explicit additional contracts; do not hide them inside this fake.
6. Run the reusable conformance suite and the application persistence integration tests.

Example test registration for another implementation:

```python
import pytest
from simulation_contract import SimulationProviderContract

class TestMyProvider(SimulationProviderContract):
    @pytest.fixture
    def provider(self):
        return MyProvider()
```

Place the registration under `tests/backend`, where `simulation_contract.py` is importable.
The suite covers eight actions, repeatability, input immutability, stale versions, unknown
entities, terminal rejection, geometry errors, closed runways and route/state ordering.
Application tests additionally cover forged effects, atomic rollback, replay, durable retry,
concurrent history, causation and publication ordering. The production fake has only domain
imports, with a dependency regression check.

## Compatibility

Port and published command/result schemas are v1. Unknown versions fail closed. Preserve
v1 semantics when adding the real provider; add explicit extensions or migrations where
needed. The previously reserved `aircraft.route_assigned` event is now implemented in the
central catalogue and schema. Its canonical projection includes complete before/after
aircraft state. Old history still replays; readers predating FP-011 reject the new route
event. Keep compatible readers and authoritative history. AB-04 remains separate.
