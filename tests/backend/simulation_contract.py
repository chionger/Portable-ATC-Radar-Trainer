"""Reusable v1 provider conformance tests. Subclass and supply a `provider` fixture."""

from pathlib import Path

import pytest

from packages.application.simulation import translate_effects
from packages.application.traffic_projection import initial_traffic
from packages.domain.simulation import (
    ApplyResult,
    RejectionCode,
    SimulationAction,
    SimulationCommand,
    SimulationParameters,
)
from packages.domain.traffic import Aerodrome, Aircraft, AircraftState, RunwayState, TrafficState
from packages.infrastructure.scenarios import load_scenario

S = AircraftState
A = SimulationAction
CASES = [
    (A.TAXI, S.READY_TO_TAXI, S.TAXIING),
    (A.HOLD, S.TAXIING, S.HOLDING),
    (A.LINE_UP, S.HOLDING, S.LINED_UP),
    (A.TAKE_OFF, S.LINED_UP, S.TAKEOFF_ROLL),
    (A.CONTINUE_APPROACH, S.INBOUND, S.FINAL),
    (A.LAND, S.FINAL, S.LANDING_ROLL),
    (A.GO_AROUND, S.FINAL, S.AIRBORNE),
    (A.VACATE, S.LANDING_ROLL, S.VACATING),
]


def traffic(state=S.READY_TO_TAXI):
    path = Path(__file__).parents[1] / "fixtures/scenarios/reference.yaml"
    base = initial_traffic(load_scenario(path.read_bytes()))
    occupied = state in {S.LINED_UP, S.TAKEOFF_ROLL, S.LANDING_ROLL, S.VACATING}
    aircraft = Aircraft.model_validate(
        base.aircraft[0].model_dump()
        | {
            "state": state,
            "holding_point_id": "hold-a" if state == S.HOLDING else None,
            "occupied_runway_id": "runway-09" if occupied else None,
        }
    )
    runway = RunwayState.model_validate(
        base.aerodrome.runways[0].model_dump()
        | {
            "occupants": ("aircraft-1",) if occupied else (),
        }
    )
    return TrafficState(
        aerodrome=Aerodrome(geometry=base.aerodrome.geometry, runways=(runway,)),
        aircraft=(aircraft,),
    )


def command(action=A.TAXI, *, parameters=None, **kwargs):
    if parameters is None:
        parameters = SimulationParameters(holding_point_id="hold-a" if action == A.HOLD else None)
    return SimulationCommand.model_validate(
        {
            "command_id": "command-1",
            "aircraft_id": "aircraft-1",
            "action": action,
            "parameters": parameters,
            "expected_entity_version": 1,
            "issued_at_sim_time": 0.0,
        }
        | kwargs
    )


class SimulationProviderContract:
    @pytest.mark.parametrize("action,start,target", CASES)
    def test_supported_actions_repeatable_and_immutable(self, provider, action, start, target):
        state, request = traffic(start), command(action)
        original = state.model_dump_json(), request.model_dump_json()
        first = provider.apply(request, state)
        second = provider.apply(request, state)
        assert first == second and first.accepted and first.rejection_code is None
        assert ApplyResult.model_validate_json(first.model_dump_json()) == first
        updated, facts = translate_effects(state, request, first)
        assert updated.aircraft[0].state == target and updated.aircraft[0].version == 2
        assert updated.aircraft[0].position == state.aircraft[0].position
        assert first.resulting_entity_version == 2 and facts
        assert (state.model_dump_json(), request.model_dump_json()) == original
        forbidden = {"event_id", "sequence", "session_id", "wall_time_utc"}
        assert forbidden.isdisjoint(first.model_dump())
        assert all(forbidden.isdisjoint(e.model_dump()) for e in first.effects)

    @pytest.mark.parametrize("expected", [2, 999])
    def test_version_conflict(self, provider, expected):
        result = provider.apply(command(expected_entity_version=expected), traffic())
        assert not result.accepted and result.rejection_code == RejectionCode.VERSION_CONFLICT
        assert result.resulting_entity_version == 1 and result.effects == ()

    def test_unknown_entity(self, provider):
        result = provider.apply(command(aircraft_id="unknown"), traffic())
        assert not result.accepted and result.rejection_code == RejectionCode.UNKNOWN_ENTITY
        assert result.resulting_entity_version is None and not result.effects

    @pytest.mark.parametrize("action", list(A))
    def test_terminal_state_rejects(self, provider, action):
        result = provider.apply(command(action), traffic(S.STOPPED))
        assert result.rejection_code == RejectionCode.ILLEGAL_STATE and not result.effects

    def test_bad_reference_rejects(self, provider):
        result = provider.apply(
            command(A.HOLD, parameters=SimulationParameters(holding_point_id="missing")),
            traffic(S.TAXIING),
        )
        assert result.rejection_code == RejectionCode.INVALID_PARAMETERS and not result.effects

    def test_route_and_state_effects_have_successive_versions(self, provider):
        state = traffic()
        request = command(parameters=SimulationParameters(route=("taxiway-a", "hold-a")))
        result = provider.apply(request, state)
        assert result.accepted and result.resulting_entity_version == 3
        assert [e.effect_type for e in result.effects] == ["ROUTE_ASSIGNED", "STATE_CHANGED"]
        assert [e.structured_payload.expected_entity_version for e in result.effects] == [1, 2]
        updated, facts = translate_effects(state, request, result)
        assert updated.aircraft[0].route == request.parameters.route
        assert updated.aircraft[0].version == 3 and len(facts) == 2

    def test_closed_runway_rejects_entry(self, provider):
        raw = traffic(S.HOLDING).model_dump_json()
        state = TrafficState.model_validate_json(raw.replace('"OPEN"', '"CLOSED"'))
        result = provider.apply(command(A.LINE_UP), state)
        assert result.rejection_code == RejectionCode.RUNWAY_CLOSED and not result.effects
