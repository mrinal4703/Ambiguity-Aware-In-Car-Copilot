import pytest

from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_6_csp import (ChargingPlanner, ChargingProblem, ac_domain, check_direct, solve_setting,
                          window_domain)


@pytest.fixture
def low():
    return CarEnvironment(make_state("low_battery"))


def _solve(env, dest, **kw):
    return ChargingPlanner.from_env(env).solve(ChargingProblem.from_env(env, dest, **kw))


@pytest.fixture
def normal():
    return CarEnvironment(make_state())


def test_near_constraint_keeps_only_stations_close_to_anchor(normal):
    r = _solve(normal, "tech_park", near="tech_park")
    assert r.feasible and r.best.station["id"] == "cs_techpark"
    assert all(s.option.metadata["near_km"] <= 3.0 for s in r.solutions)


def test_tolls_soft_by_default_hard_when_strict(low):
    soft = _solve(low, "cuttack", avoid_tolls=True)
    strict = _solve(low, "cuttack", avoid_tolls_strict=True)
    assert soft.feasible
    assert all(not s.option.metadata["toll"] for s in strict.solutions)


def test_cautious_consumption_tightens_reach(low):
    normal = _solve(low, "cuttack")
    cautious = _solve(low, "cuttack", consumption_factor=1.8)
    assert len(cautious.solutions) <= len(normal.solutions)
    assert not check_direct(low, "tech_park", consumption_factor=10).feasible


def test_station_availability_is_a_soft_penalty(normal):
    base = _solve(normal, "tech_park")
    sid = base.best.station["id"]
    shifted = _solve(normal, "tech_park", availability={sid: 0.05})
    assert shifted.feasible and shifted.best.station["id"] != sid


def test_infeasible_explanation_is_concise(low):
    r = _solve(low, "cuttack", deadline_min=1)
    assert not r.feasible and r.explanation.count(";") < 4 and "station" in r.explanation


def test_setting_csp_finds_closest_safe_value():
    r = solve_setting(100, window_domain(), [("speed_limit", lambda v: v <= 20)])
    assert r.modified and r.value == 20 and r.violated == ["speed_limit"]
    assert not solve_setting(10, window_domain(), [("speed_limit", lambda v: v <= 20)]).modified
    ac = solve_setting(35, ac_domain(), [("supported_range", lambda v: 16 <= v <= 30)])
    assert ac.value == 30
    assert not solve_setting(5, [0, 1], [("never", lambda v: False)]).feasible
